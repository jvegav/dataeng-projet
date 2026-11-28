"""HTTP API and static server of the DeservEat dashboard.

It uses the same PostgreSQL connection as the Airflow loaders (DW_DATABASE_URL); the browser never
receives database credentials.

Read endpoints
    GET  /api/dashboard   KPI summary (+ legacy route preview)
    GET  /api/search      recipe or restaurant autocomplete (?q=..&kind=recipe|restaurant)
    GET  /api/options     activities and known users for the planner form
    GET  /api/insights    answers to the 8 business questions of the README (one block per question)
    GET  /api/recent      latest facts written to dw.fact_calorie_burn
    GET  /api/fact?id=N   route of one fact (route_steps, or start / restaurant / end when not stored)
    GET  /api/route       legacy preview from an existing fact (kept for compatibility)

Write endpoint
    POST /api/requests    one calorie-burning request from the UI = one new row in dw.fact_calorie_burn
                          (+ its dw.dim_itinerary row, + a new dw.dim_user SCD2 version if the weight changed)

How a request is turned into a fact (POST /api/requests), in one transaction:
  1. user: dw.apply_user_version(user_id, weight_kg, now()) - same SCD2 function as the generator;
     without a weight, the version valid now (dw.user_key_at) is used
  2. kcal_to_burn = kcal_per_serving; duration_min and distance_km with the same formulas as the pipeline
  3. start: the restaurant, or the user's position snapped to the ~200 m grid of dim_itinerary
  4. route: start -> restaurant -> landmark -> landmark -> ... (restaurants are used as waypoints when no
     landmark is reachable). Each hop aims at an even share of the distance left; the chain stops when
     ROUTE_BUDGET of distance_km is used. The route ends on its last landmark (landmark_key); without a
     landmark it is a loop back to the start. The whole chain is stored in dim_itinerary.route_steps.
     Legs are straight lines (road routing is a documented limitation), so distance_km >= route length.
"""

import json
import math
import os
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("DASHBOARD_PORT_INTERNAL", "8000"))
DATABASE_URL = os.environ["DW_DATABASE_URL"]

LYON_CENTER = (45.7578, 4.8320)          # place Bellecour: default reference point
LYON_BBOX = (45.4, 46.1, 4.5, 5.3)       # same bounding box as the DDL checks
ROUTE_BUDGET = 0.97                      # share of distance_km the chain may use (straight lines, rounding)
MIN_LEG_KM = 0.3                         # no hop shorter than this (avoids 50 m hops in the old town)
MAX_STOPS = 8                            # waypoints after the restaurant
IDEAL_LEG_KM = 1.5                       # target hop length when the distance to burn is long
RESTAURANT_PENALTY = 0.5                 # a restaurant waypoint must be clearly better than a landmark


@contextmanager
def connect():
    """A connection that commits (or rolls back on error) and is always closed."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def floats(row, *keys):
    for key in keys:
        if row.get(key) is not None:
            row[key] = float(row[key])
    return row


# ---------------------------------------------------------------------------------------------------
# Read endpoints (Josue's originals, ids added to the search results)
# ---------------------------------------------------------------------------------------------------

def fetch_dashboard(food="", activity="walk", landmark="yes"):
    activity_pattern = f"%{activity.lower()}%"
    food_filter = """AND (r.title ILIKE %(food)s OR rest.restaurant_name ILIKE %(food)s
                          OR COALESCE(r.category, '') ILIKE %(food)s)""" if food else ""
    params = {"food": f"%{food}%", "activity": activity_pattern, "want_landmark": landmark == "yes"}

    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT count(*) AS total_requests,
                   round(avg(duration_min), 1) AS avg_duration_min,
                   round(avg(distance_km), 2) AS avg_distance_km,
                   round(100.0 * count(*) FILTER (WHERE landmark_key IS NOT NULL) / NULLIF(count(*), 0), 1)
                       AS landmark_inclusion_pct
            FROM dw.fact_calorie_burn
        """)
        summary = dict(cur.fetchone())

        cur.execute(f"""
            SELECT r.title AS food, r.kcal_per_serving AS calories,
                   rest.restaurant_name AS restaurant, a.activity_name,
                   f.distance_km, f.duration_min,
                   ST_Y(i.start_point::geometry) AS start_lat,
                   ST_X(i.start_point::geometry) AS start_lng,
                   ST_Y(i.end_point::geometry) AS end_lat,
                   ST_X(i.end_point::geometry) AS end_lng,
                   l.building_name AS landmark_name,
                   ST_Y(l.geom::geometry) AS landmark_lat,
                   ST_X(l.geom::geometry) AS landmark_lng
            FROM dw.fact_calorie_burn f
            JOIN dw.dim_recipe r ON r.recipe_key = f.recipe_key
            JOIN dw.dim_restaurant rest ON rest.restaurant_key = f.restaurant_key
            JOIN dw.dim_activity a ON a.activity_key = f.activity_key
            JOIN dw.dim_itinerary i ON i.itinerary_key = f.itinerary_key
            LEFT JOIN dw.dim_landmark l ON l.landmark_key = f.landmark_key
            WHERE lower(a.activity_name) LIKE %(activity)s
              {food_filter}
            ORDER BY ((f.landmark_key IS NOT NULL) = %(want_landmark)s) DESC,
                     f.requested_at DESC
            LIMIT 1
        """, params)
        route = cur.fetchone()
        if route:
            route = floats(dict(route), "distance_km", "duration_min", "start_lat", "start_lng",
                           "end_lat", "end_lng", "landmark_lat", "landmark_lng")
            route["calories"] = int(route["calories"])
            route["landmark_applied"] = route["landmark_name"] is not None

        cur.execute("""
            SELECT building_name AS name, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
            FROM dw.dim_landmark ORDER BY building_name LIMIT 300
        """)
        landmarks = [floats(dict(row), "lat", "lng") for row in cur.fetchall()]

    return {"summary": summary, "route": route, "landmarks": landmarks, "source": "PostgreSQL/PostGIS"}


def search_foods(query, kind="recipe"):
    """Recipe or restaurant suggestions for the autocomplete inputs (with their source_id)."""
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        if kind == "restaurant":
            cur.execute("""
                SELECT rest.source_id::text AS source_id, rest.restaurant_name AS name,
                       rest.food_type, rest.district, rest.overall_rating AS rating,
                       ST_Y(rest.geom::geometry) AS lat, ST_X(rest.geom::geometry) AS lng,
                       (SELECT count(*) FROM dw.fact_calorie_burn f WHERE f.restaurant_key = rest.restaurant_key) AS requests
                FROM dw.dim_restaurant rest
                WHERE rest.restaurant_name ILIKE %(query)s OR COALESCE(rest.food_type, '') ILIKE %(query)s
                ORDER BY requests DESC, rest.overall_rating DESC NULLS LAST, rest.restaurant_name
                LIMIT 8
            """, {"query": f"%{query}%"})
            return [floats(dict(row), "rating", "lat", "lng") for row in cur.fetchall()]
        cur.execute("""
            WITH match AS (
                SELECT recipe_key, source_id, title, kcal_per_serving
                FROM dw.dim_recipe
                WHERE title ILIKE %(query)s
                ORDER BY (title ILIKE %(prefix)s) DESC, length(title), title
                LIMIT 8
            )
            SELECT m.source_id, m.title AS food, m.kcal_per_serving AS calories,
                   (SELECT count(*) FROM dw.fact_calorie_burn f WHERE f.recipe_key = m.recipe_key) AS requests
            FROM match m
            ORDER BY (m.title ILIKE %(prefix)s) DESC, length(m.title), m.title
        """, {"query": f"%{query}%", "prefix": f"{query}%"})
        return [dict(row) for row in cur.fetchall()]


def fetch_options():
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""SELECT activity_key, activity_name, met_value, speed_kmh, intensity
                       FROM dw.dim_activity ORDER BY speed_kmh""")
        activities = [floats(dict(r), "met_value", "speed_kmh") for r in cur.fetchall()]
        cur.execute("""SELECT user_id, weight_kg FROM dw.dim_user WHERE is_current
                       ORDER BY (user_id LIKE 'g%%') , user_id LIMIT 300""")
        users = [floats(dict(r), "weight_kg") for r in cur.fetchall()]
    return {"activities": activities, "users": users}


# ---------------------------------------------------------------------------------------------------
# Route builder
# ---------------------------------------------------------------------------------------------------

def km(a, b):
    """Great-circle distance in km between two {lat, lng} points."""
    lat1, lng1, lat2, lng2 = map(math.radians, (a["lat"], a["lng"], b["lat"], b["lng"]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def plan_route(start, restaurant, target_km, candidates, visit_landmarks):
    """Chain start -> restaurant -> waypoints within ROUTE_BUDGET * target_km.

    start / restaurant: {"lat", "lng", "name", "kind"}; start is restaurant when the walk starts there.
    candidates: [{"kind": "landmark" | "restaurant", "key", "name", "lat", "lng"}].
    Returns (steps, landmark_key_of_the_end or None, notes).
    """
    budget = target_km * ROUTE_BUDGET
    notes = []
    steps = [dict(start, seq=0, leg_km=0.0, cum_km=0.0)]
    cum = 0.0
    if start["kind"] != "restaurant":
        to_restaurant = km(start, restaurant)
        cum = to_restaurant
        steps.append(dict(restaurant, seq=1, leg_km=round(to_restaurant, 3), cum_km=round(cum, 3)))

    chain = []
    if visit_landmarks and budget - cum >= MIN_LEG_KM:
        position, visited = restaurant, set()
        wanted = max(1, min(MAX_STOPS, math.ceil((budget - cum) / IDEAL_LEG_KM)))
        while len(chain) < MAX_STOPS:
            left = budget - cum
            if left < MIN_LEG_KM:
                break
            ideal = left / max(1, wanted - len(chain))
            options = []
            for c in candidates:
                if (c["kind"], c["key"]) in visited:
                    continue
                leg = km(position, c)
                if MIN_LEG_KM <= leg <= left:
                    score = abs(leg - ideal) + (RESTAURANT_PENALTY * ideal if c["kind"] == "restaurant" else 0)
                    options.append((score, leg, c))
            if not options:
                break
            _, leg, best = min(options, key=lambda o: (o[0], o[1]))
            visited.add((best["kind"], best["key"]))
            cum += leg
            chain.append((best, leg, cum))
            position = best
        # The route must end on a landmark: drop trailing restaurant waypoints
        while chain and chain[-1][0]["kind"] != "landmark":
            chain.pop()
        cum = chain[-1][2] if chain else (km(start, restaurant) if start["kind"] != "restaurant" else 0.0)
        if not chain:
            notes.append("No landmark could be reached within the distance to burn: the route is a loop.")

    for best, leg, total in chain:
        steps.append(dict(best, seq=len(steps), leg_km=round(leg, 3), cum_km=round(total, 3)))

    end_landmark = chain[-1][0]["key"] if chain else None
    if end_landmark is None and start["kind"] != "restaurant":
        back = km(restaurant, start)
        cum += back
        steps.append(dict(start, seq=len(steps), name="Back to start", leg_km=round(back, 3), cum_km=round(cum, 3)))
    if not visit_landmarks:
        notes.append("Landmarks not requested: the route is a loop.")
    return steps, end_landmark, notes


def create_request(body):
    """Write one calorie-burning request: SCD2 user version, dim_itinerary row and fact row."""
    user_id = str(body.get("user_id", "")).strip()
    if not user_id or len(user_id) > 40:
        raise ValueError("Give a user id (1-40 characters).")
    weight = body.get("weight_kg")
    weight = float(weight) if weight not in (None, "") else None
    if weight is not None and not 30 <= weight <= 250:
        raise ValueError("The weight must be between 30 and 250 kg.")
    recipe_id = int(body["recipe_source_id"])
    activity_key = int(body["activity_key"])
    restaurant_id = str(body.get("restaurant_source_id") or "").strip()
    start_mode = body.get("start_mode", "restaurant")
    visit_landmarks = bool(body.get("visit_landmarks", True))
    notes = []

    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT now() AS at")
        requested_at = cur.fetchone()["at"]

        # 1. user version valid now (SCD2)
        if weight is not None:
            cur.execute("SELECT dw.apply_user_version(%s, %s, %s) AS user_key", (user_id, weight, requested_at))
        else:
            cur.execute("SELECT dw.user_key_at(%s, %s) AS user_key", (user_id, requested_at))
        user_key = cur.fetchone()["user_key"]
        if user_key is None:
            raise ValueError(f"Unknown user '{user_id}': give a weight to create it.")
        cur.execute("""SELECT user_key, user_id, weight_kg, valid_from,
                              (SELECT count(*) FROM dw.dim_user v WHERE v.user_id = u.user_id) AS versions
                       FROM dw.dim_user u WHERE user_key = %s""", (user_key,))
        user = floats(dict(cur.fetchone()), "weight_kg")

        # 2. recipe, activity, start point, restaurant
        cur.execute("SELECT recipe_key, title, kcal_per_serving FROM dw.dim_recipe WHERE source_id = %s", (recipe_id,))
        recipe = cur.fetchone()
        if not recipe:
            raise ValueError("Unknown recipe: pick one from the suggestions.")
        cur.execute("SELECT activity_key, activity_name, met_value, speed_kmh FROM dw.dim_activity WHERE activity_key = %s",
                    (activity_key,))
        activity = cur.fetchone()
        if not activity:
            raise ValueError("Unknown activity.")

        start_point = None
        if start_mode == "user_location":
            lat, lng = float(body["start_lat"]), float(body["start_lng"])
            if LYON_BBOX[0] <= lat <= LYON_BBOX[1] and LYON_BBOX[2] <= lng <= LYON_BBOX[3]:
                cur.execute("""SELECT ST_Y(p) AS lat, ST_X(p) AS lng
                               FROM (SELECT ST_SnapToGrid(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 0.0026, 0.0018) AS p) s""",
                            (lng, lat))
                start_point = floats(dict(cur.fetchone()), "lat", "lng")
            else:
                notes.append("Your position is outside the Lyon area: the route starts at the restaurant.")

        reference = start_point or {"lat": LYON_CENTER[0], "lng": LYON_CENTER[1]}
        if restaurant_id:
            cur.execute("""SELECT restaurant_key, restaurant_name, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
                           FROM dw.dim_restaurant WHERE source_id = %s""", (int(restaurant_id),))
        else:
            cur.execute("""SELECT restaurant_key, restaurant_name, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
                           FROM dw.dim_restaurant
                           ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography LIMIT 1""",
                        (reference["lng"], reference["lat"]))
            notes.append("No restaurant chosen: the nearest one was used.")
        restaurant = cur.fetchone()
        if not restaurant:
            raise ValueError("Unknown restaurant.")
        restaurant = floats(dict(restaurant), "lat", "lng")

        # 3. duration and distance: same formulas (and rounding) as the pipeline
        cur.execute("""SELECT ROUND(60 * %(kcal)s / (%(met)s * %(w)s), 1) AS duration_min,
                              ROUND(%(speed)s * %(kcal)s / (%(met)s * %(w)s), 2) AS distance_km""",
                    {"kcal": recipe["kcal_per_serving"], "met": activity["met_value"],
                     "speed": activity["speed_kmh"], "w": user["weight_kg"]})
        calc = floats(dict(cur.fetchone()), "duration_min", "distance_km")
        target = calc["distance_km"]

        rest_point = {"kind": "restaurant", "key": restaurant["restaurant_key"], "name": restaurant["restaurant_name"],
                      "lat": restaurant["lat"], "lng": restaurant["lng"]}
        if start_point and 2 * km(start_point, rest_point) > target * ROUTE_BUDGET:
            notes.append("Your position is too far from the restaurant for this dish: the route starts at the restaurant.")
            start_point = None
        start = ({"kind": "user_location", "key": None, "name": "Your position (rounded ~200 m)", **start_point}
                 if start_point else dict(rest_point))

        # 4. candidate waypoints: landmarks and other restaurants reachable from the restaurant
        cur.execute("""
            SELECT 'landmark' AS kind, landmark_key AS key, building_name || ' · ' || COALESCE(address, commune, '') AS name,
                   ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
            FROM dw.dim_landmark
            WHERE ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography, %(radius)s)
            UNION ALL
            (SELECT 'restaurant', restaurant_key, restaurant_name, ST_Y(geom::geometry), ST_X(geom::geometry)
             FROM dw.dim_restaurant
             WHERE restaurant_key <> %(rkey)s
               AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography, %(radius)s)
             ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography
             LIMIT 300)
        """, {"lng": restaurant["lng"], "lat": restaurant["lat"], "radius": target * 1000, "rkey": restaurant["restaurant_key"]})
        candidates = [floats(dict(r), "lat", "lng") for r in cur.fetchall()]
        steps, end_landmark, route_notes = plan_route(start, rest_point, target, candidates, visit_landmarks)
        notes += route_notes
        route_km = steps[-1]["cum_km"]

        # 5. itinerary, then fact
        route_steps = [{"seq": s["seq"], "kind": s["kind"], "name": s["name"],
                        "lat": round(s["lat"], 6), "lng": round(s["lng"], 6),
                        "leg_km": s["leg_km"], "cum_km": s["cum_km"]} for s in steps]
        start_sql = ("ST_SnapToGrid(ST_SetSRID(ST_MakePoint(%(slng)s, %(slat)s), 4326), 0.0026, 0.0018)::geography"
                     if start["kind"] == "user_location" else
                     "(SELECT geom FROM dw.dim_restaurant WHERE restaurant_key = %(rkey)s)")
        cur.execute(f"""
            WITH s AS (SELECT {start_sql} AS start_point)
            INSERT INTO dw.dim_itinerary (start_type, start_point, end_point, route_steps)
            SELECT %(stype)s, s.start_point,
                   COALESCE((SELECT geom FROM dw.dim_landmark WHERE landmark_key = %(lkey)s), s.start_point),
                   %(steps)s::jsonb
            FROM s
            RETURNING itinerary_key
        """, {"slng": start["lng"], "slat": start["lat"], "rkey": restaurant["restaurant_key"],
              "stype": "user_location" if start["kind"] == "user_location" else "restaurant",
              "lkey": end_landmark, "steps": json.dumps(route_steps)})
        itinerary_key = cur.fetchone()["itinerary_key"]

        cur.execute("""
            INSERT INTO dw.fact_calorie_burn (recipe_key, activity_key, landmark_key, user_key, restaurant_key, date_key,
                                              itinerary_key, kcal_to_burn, distance_km, duration_min, requested_at)
            VALUES (%(recipe)s, %(activity)s, %(landmark)s, %(user)s, %(restaurant)s,
                    to_char(%(at)s AT TIME ZONE 'Europe/Paris', 'YYYYMMDD')::INT,
                    %(itinerary)s, %(kcal)s, %(distance)s, %(duration)s, %(at)s)
            RETURNING calorie_burn_key
        """, {"recipe": recipe["recipe_key"], "activity": activity_key, "landmark": end_landmark,
              "user": user_key, "restaurant": restaurant["restaurant_key"], "at": requested_at,
              "itinerary": itinerary_key, "kcal": recipe["kcal_per_serving"],
              "distance": calc["distance_km"], "duration": calc["duration_min"]})
        fact_key = cur.fetchone()["calorie_burn_key"]

    return {
        "calorie_burn_key": fact_key, "itinerary_key": itinerary_key, "requested_at": requested_at,
        "user": user, "recipe": recipe["title"], "calories": int(recipe["kcal_per_serving"]),
        "restaurant": restaurant["restaurant_name"], "activity_name": activity["activity_name"],
        "duration_min": calc["duration_min"], "distance_km": target,
        "route_km": route_km, "free_km": round(max(0.0, target - route_km), 2),
        "landmarks_visited": sum(1 for s in steps if s["kind"] == "landmark"),
        "steps": route_steps, "notes": notes,
    }


# ---------------------------------------------------------------------------------------------------
# Facts already in the warehouse
# ---------------------------------------------------------------------------------------------------

def fetch_recent(limit=12):
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT f.calorie_burn_key, f.requested_at, u.user_id, u.weight_kg, r.title AS recipe,
                   rest.restaurant_name AS restaurant, a.activity_name, f.kcal_to_burn,
                   f.duration_min, f.distance_km, l.building_name AS landmark, i.start_type,
                   COALESCE(jsonb_array_length(i.route_steps), 0) AS stops
            FROM dw.fact_calorie_burn f
            JOIN dw.dim_user u USING (user_key)
            JOIN dw.dim_recipe r USING (recipe_key)
            JOIN dw.dim_restaurant rest USING (restaurant_key)
            JOIN dw.dim_activity a USING (activity_key)
            JOIN dw.dim_itinerary i USING (itinerary_key)
            LEFT JOIN dw.dim_landmark l USING (landmark_key)
            ORDER BY f.calorie_burn_key DESC
            LIMIT %s
        """, (limit,))
        return [floats(dict(r), "weight_kg", "duration_min", "distance_km") for r in cur.fetchall()]


def fetch_fact(fact_key):
    """Route of a fact: its stored route_steps, or start -> restaurant -> end for generated facts."""
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT f.calorie_burn_key, r.title AS recipe, r.kcal_per_serving AS calories,
                   rest.restaurant_name AS restaurant, a.activity_name, f.duration_min, f.distance_km,
                   u.user_id, u.weight_kg, i.start_type, i.route_steps, l.building_name AS landmark,
                   ST_Y(i.start_point::geometry) AS start_lat, ST_X(i.start_point::geometry) AS start_lng,
                   ST_Y(rest.geom::geometry) AS rest_lat, ST_X(rest.geom::geometry) AS rest_lng,
                   ST_Y(i.end_point::geometry) AS end_lat, ST_X(i.end_point::geometry) AS end_lng
            FROM dw.fact_calorie_burn f
            JOIN dw.dim_user u USING (user_key)
            JOIN dw.dim_recipe r USING (recipe_key)
            JOIN dw.dim_restaurant rest USING (restaurant_key)
            JOIN dw.dim_activity a USING (activity_key)
            JOIN dw.dim_itinerary i USING (itinerary_key)
            LEFT JOIN dw.dim_landmark l USING (landmark_key)
            WHERE f.calorie_burn_key = %s
        """, (fact_key,))
        row = cur.fetchone()
    if not row:
        return None
    row = floats(dict(row), "duration_min", "distance_km", "weight_kg", "start_lat", "start_lng",
                 "rest_lat", "rest_lng", "end_lat", "end_lng")
    steps = row.pop("route_steps")
    if not steps:                                   # generated facts: no stored chain
        start = {"lat": row["start_lat"], "lng": row["start_lng"]}
        rest = {"lat": row["rest_lat"], "lng": row["rest_lng"]}
        end = {"lat": row["end_lat"], "lng": row["end_lng"]}
        steps = [dict(start, seq=0, kind=row["start_type"], name="Start")]
        if row["start_type"] != "restaurant":
            steps.append(dict(rest, seq=1, kind="restaurant", name=row["restaurant"]))
        steps[0 if row["start_type"] == "restaurant" else 1]["name"] = row["restaurant"]
        if row["landmark"]:
            steps.append(dict(end, seq=len(steps), kind="landmark", name=row["landmark"]))
        elif row["start_type"] != "restaurant":
            steps.append(dict(end, seq=len(steps), kind="user_location", name="Back to start"))
        total = 0.0
        for previous, step in zip(steps, steps[1:]):
            step["leg_km"] = round(km(previous, step), 3)
            total += step["leg_km"]
            step["cum_km"] = round(total, 3)
        steps[0].update(leg_km=0.0, cum_km=0.0)
    row["steps"] = steps
    row["route_km"] = steps[-1]["cum_km"]
    row["calories"] = int(row["calories"])
    return row


# ---------------------------------------------------------------------------------------------------
# Business questions (README §1) - one block per question, answered from dw
# ---------------------------------------------------------------------------------------------------

ACTIVITY_TYPE = """CASE WHEN a.activity_name ILIKE '%%walk%%' THEN 'Walk'
                        WHEN a.activity_name ILIKE '%%run%%' THEN 'Run' ELSE 'Cycle' END"""

# The food.com tags of category are a list; the course is the first matching tag, in this order
COURSE = """CASE WHEN r.category ILIKE '%%''desserts''%%' THEN 'Dessert'
                 WHEN r.category ILIKE '%%''main-dish''%%' THEN 'Main dish'
                 WHEN r.category ILIKE '%%''appetizers''%%' THEN 'Appetizer'
                 WHEN r.category ILIKE '%%''side-dishes''%%' THEN 'Side dish'
                 WHEN r.category ILIKE '%%''salads''%%' THEN 'Salad'
                 WHEN r.category ILIKE '%%''soups-stews''%%' THEN 'Soup'
                 WHEN r.category ILIKE '%%''breakfast''%%' OR r.category ILIKE '%%''brunch''%%' THEN 'Breakfast'
                 WHEN r.category ILIKE '%%''beverages''%%' THEN 'Drink'
                 WHEN r.category ILIKE '%%''breads''%%' THEN 'Bread'
                 WHEN r.category IS NULL OR r.category = '' THEN 'Untagged'
                 ELSE 'Other' END"""

INSIGHT_QUERIES = {
    "kpis": """
        SELECT count(*) AS requests, round(avg(duration_min), 1) AS avg_duration_min,
               round(avg(distance_km), 2) AS avg_distance_km,
               round(100.0 * count(*) FILTER (WHERE landmark_key IS NOT NULL) / NULLIF(count(*), 0), 1) AS landmark_pct,
               count(DISTINCT user_key) AS user_versions, min(requested_at)::date AS first_day,
               max(requested_at)::date AS last_day
        FROM dw.fact_calorie_burn""",
    "q1_month": """
        SELECT to_char(make_date(d.year, d.month, 1), 'YYYY-MM') AS period, count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_date d USING (date_key)
        GROUP BY d.year, d.month ORDER BY d.year, d.month""",
    "q1_week": """
        SELECT to_char(date_trunc('week', d.full_date), 'YYYY-MM-DD') AS period, count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_date d USING (date_key)
        GROUP BY 1 ORDER BY 1""",
    "q1_day": """
        WITH days AS (
            SELECT d.full_date, d.is_weekend, count(f.calorie_burn_key) AS requests
            FROM dw.dim_date d LEFT JOIN dw.fact_calorie_burn f USING (date_key)
            WHERE d.full_date BETWEEN (SELECT min(requested_at)::date FROM dw.fact_calorie_burn)
                                  AND (SELECT max(requested_at)::date FROM dw.fact_calorie_burn)
            GROUP BY d.full_date, d.is_weekend)
        SELECT round(avg(requests), 2) AS avg_per_day, max(requests) AS max_per_day,
               count(*) FILTER (WHERE requests = 0) AS days_without,
               round(avg(requests) FILTER (WHERE is_weekend), 2) AS avg_weekend,
               round(avg(requests) FILTER (WHERE NOT is_weekend), 2) AS avg_weekday,
               (SELECT to_char(full_date, 'YYYY-MM-DD') FROM days ORDER BY requests DESC, full_date LIMIT 1) AS busiest_day
        FROM days""",
    "q2": f"""
        SELECT a.activity_name AS label, {ACTIVITY_TYPE} AS type, count(*) AS requests,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
        FROM dw.fact_calorie_burn f JOIN dw.dim_activity a USING (activity_key)
        GROUP BY a.activity_name, a.speed_kmh ORDER BY requests DESC, a.speed_kmh""",
    "q3": """
        SELECT r.title AS label, round(avg(f.kcal_to_burn)) AS avg_kcal, count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_recipe r USING (recipe_key)
        GROUP BY r.recipe_key, r.title ORDER BY avg_kcal DESC, requests DESC LIMIT 10""",
    "q4": f"""
        SELECT a.activity_name AS label, {ACTIVITY_TYPE} AS type, round(avg(f.duration_min), 1) AS avg_min,
               round((percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_min))::numeric, 1) AS median_min,
               count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_activity a USING (activity_key)
        GROUP BY a.activity_name, a.met_value ORDER BY avg_min DESC""",
    "q5": f"""
        SELECT CASE WHEN u.weight_kg < 60 THEN '< 60 kg' WHEN u.weight_kg < 75 THEN '60-75 kg'
                    WHEN u.weight_kg < 90 THEN '75-90 kg' ELSE '90+ kg' END AS band,
               CASE WHEN u.weight_kg < 60 THEN 1 WHEN u.weight_kg < 75 THEN 2 WHEN u.weight_kg < 90 THEN 3 ELSE 4 END AS ord,
               {ACTIVITY_TYPE} AS type, round(avg(f.duration_min), 1) AS avg_min, count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_user u USING (user_key) JOIN dw.dim_activity a USING (activity_key)
        GROUP BY 1, 2, 3 ORDER BY 2, 3""",
    "q6": """
        SELECT rest.restaurant_name AS label, rest.food_type, rest.overall_rating AS rating, count(*) AS requests,
               round(avg(f.kcal_to_burn)) AS avg_kcal
        FROM dw.fact_calorie_burn f JOIN dw.dim_restaurant rest USING (restaurant_key)
        GROUP BY rest.restaurant_key ORDER BY requests DESC, rest.overall_rating DESC NULLS LAST LIMIT 10""",
    "q7_rate": """
        SELECT count(*) FILTER (WHERE landmark_key IS NOT NULL) AS with_landmark,
               count(*) FILTER (WHERE landmark_key IS NULL) AS without_landmark,
               round(100.0 * count(*) FILTER (WHERE landmark_key IS NOT NULL) / NULLIF(count(*), 0), 1) AS pct
        FROM dw.fact_calorie_burn""",
    "q7_top": """
        SELECT l.building_name || ' · ' || COALESCE(l.address, l.commune, '') AS label, count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_landmark l USING (landmark_key)
        GROUP BY l.landmark_key, l.building_name, l.commune ORDER BY requests DESC LIMIT 10""",
    "q8": f"""
        SELECT {ACTIVITY_TYPE} AS type, {COURSE} AS course, round(avg(f.distance_km), 2) AS avg_km,
               min(f.distance_km) AS min_km, max(f.distance_km) AS max_km, count(*) AS requests
        FROM dw.fact_calorie_burn f JOIN dw.dim_activity a USING (activity_key) JOIN dw.dim_recipe r USING (recipe_key)
        GROUP BY 1, 2 ORDER BY 1, avg_km DESC""",
}


def fetch_insights():
    result = {}
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        for name, query in INSIGHT_QUERIES.items():
            cur.execute(query)
            rows = [dict(r) for r in cur.fetchall()]
            for row in rows:
                for key, value in row.items():
                    if hasattr(value, "is_finite") or isinstance(value, float):   # Decimal / float -> float
                        row[key] = float(value)
            result[name] = rows
    return result


# ---------------------------------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------------------------------

STATIC_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}


class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api(self, handler):
        try:
            self.send_json(handler())
        except (ValueError, KeyError, TypeError) as error:       # bad input from the form
            self.send_json({"error": str(error)}, status=400)
        except psycopg2.Error as error:                          # a constraint refused the row, or DB down
            message = (error.pgerror or str(error)).strip().splitlines()[0]
            self.send_json({"error": f"Database: {message}"}, status=500)
        except Exception as error:  # noqa: BLE001  the UI shows the message
            self.send_json({"error": str(error)}, status=500)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        arg = lambda name, default="": query.get(name, [default])[0]  # noqa: E731
        routes = {
            "/api/dashboard": lambda: fetch_dashboard(arg("food").strip(), arg("activity", "walk"), arg("landmark", "yes")),
            "/api/search": lambda: {"results": search_foods(arg("q").strip(), arg("kind", "recipe"))},
            "/api/options": fetch_options,
            "/api/insights": fetch_insights,
            "/api/recent": lambda: {"facts": fetch_recent(min(50, int(arg("limit", "12"))))},
            "/api/fact": lambda: fetch_fact(int(arg("id"))) or {"error": "not found"},
            "/api/route": lambda: calculate_route(arg("recipe"), arg("restaurant"), arg("activity", "walk"),
                                                  arg("landmark", "yes") == "yes", arg("start_mode", "restaurant"),
                                                  float(arg("start_lat")) if arg("start_lat") else None,
                                                  float(arg("start_lng")) if arg("start_lng") else None)
                                  or {"error": "No matching recipe/activity/restaurant fact found"},
        }
        if parsed.path in routes:
            self.api(routes[parsed.path])
            return

        file_path = (ROOT / ("index.html" if parsed.path in ("/", "/index.html") else parsed.path.lstrip("/"))).resolve()
        if file_path.is_file() and ROOT in file_path.parents and file_path.suffix in STATIC_TYPES:
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", STATIC_TYPES[file_path.suffix])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path != "/api/requests":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 20_000:
            self.send_json({"error": "request too large"}, status=413)
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_json({"error": "invalid JSON"}, status=400)
            return
        self.api(lambda: create_request(body))

    def log_message(self, format, *args):
        print(format % args, flush=True)


# ---------------------------------------------------------------------------------------------------
# Legacy preview kept from the first version of the dashboard (GET /api/route)
# ---------------------------------------------------------------------------------------------------

def calculate_route(recipe, restaurant, activity, visit_landmark, start_mode, start_lat=None, start_lng=None):
    """Preview a route from an EXISTING fact (read-only); the planner now uses POST /api/requests."""
    with connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT r.title AS recipe, r.kcal_per_serving AS calories,
                   rest.restaurant_name AS restaurant, rest.lat AS restaurant_lat, rest.lng AS restaurant_lng,
                   a.activity_name, f.distance_km AS target_distance_km, f.duration_min, u.weight_kg
            FROM dw.fact_calorie_burn f
            JOIN dw.dim_recipe r ON r.recipe_key = f.recipe_key
            JOIN dw.dim_restaurant rest ON rest.restaurant_key = f.restaurant_key
            JOIN dw.dim_activity a ON a.activity_key = f.activity_key
            JOIN dw.dim_user u ON u.user_key = f.user_key
            WHERE r.title = %(recipe)s
              AND (%(restaurant)s = '' OR rest.restaurant_name = %(restaurant)s)
              AND lower(a.activity_name) LIKE %(activity)s
            ORDER BY (rest.restaurant_name = %(restaurant)s) DESC, f.requested_at DESC
            LIMIT 1
        """, {"recipe": recipe, "restaurant": restaurant, "activity": f"%{activity.lower()}%"})
        selected = cur.fetchone()
    if not selected:
        return None
    selected = floats(dict(selected), "restaurant_lat", "restaurant_lng", "target_distance_km", "duration_min", "weight_kg")
    origin = ({"lat": float(start_lat), "lng": float(start_lng)} if start_mode == "current" and start_lat is not None
              else {"lat": selected["restaurant_lat"], "lng": selected["restaurant_lng"]})
    rest = {"lat": selected["restaurant_lat"], "lng": selected["restaurant_lng"]}
    return {"recipe": selected["recipe"], "restaurant": selected["restaurant"], "calories": int(selected["calories"]),
            "weight_kg": selected["weight_kg"], "activity_name": selected["activity_name"],
            "duration_min": selected["duration_min"], "target_distance_km": selected["target_distance_km"],
            "route_distance_km": round(2 * km(origin, rest), 2), "points": [origin, rest, origin],
            "landmark": None, "start_mode": start_mode}


if __name__ == "__main__":
    print(f"Dashboard API listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler).serve_forever()
