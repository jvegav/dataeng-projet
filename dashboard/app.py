"""Small read-only HTTP API for the DeservEat dashboard.

It uses the same PostgreSQL connection as the Airflow loaders. The browser never
receives database credentials; it only calls /api/dashboard.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg2
from psycopg2.extras import RealDictCursor

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("DASHBOARD_PORT_INTERNAL", "8000"))
DATABASE_URL = os.environ["DW_DATABASE_URL"]


def fetch_dashboard(food="", activity="walk", landmark="yes"):
    activity_pattern = f"%{activity.lower()}%"
    food_filter = """AND (r.title ILIKE %(food)s OR rest.restaurant_name ILIKE %(food)s
                          OR COALESCE(r.category, '') ILIKE %(food)s)""" if food else ""
    params = {"food": f"%{food}%", "activity": activity_pattern, "want_landmark": landmark == "yes"}

    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
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
            -- Prefer the requested landmark state, but do not hide a valid fact
            -- when that exact combination was not generated for this recipe.
            ORDER BY ((f.landmark_key IS NOT NULL) = %(want_landmark)s) DESC,
                     f.requested_at DESC
            LIMIT 1
        """, params)
        route = cur.fetchone()
        if route:
            route = dict(route)
            route["calories"] = int(route["calories"])
            route["landmark_applied"] = route["landmark_name"] is not None
            for key in ("distance_km", "duration_min", "start_lat", "start_lng", "end_lat", "end_lng", "landmark_lat", "landmark_lng"):
                if route.get(key) is not None:
                    route[key] = float(route[key])
        else:
            route = None

        cur.execute("""
            SELECT building_name AS name, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
            FROM dw.dim_landmark ORDER BY building_name LIMIT 150
        """)
        landmarks = [dict(row) for row in cur.fetchall()]
        for row in landmarks:
            row["lat"], row["lng"] = float(row["lat"]), float(row["lng"])

    return {"summary": summary, "route": route, "landmarks": landmarks, "source": "PostgreSQL/PostGIS"}


def search_foods(query, kind="recipe"):
    """Return real recipe or restaurant suggestions for the autocomplete input."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        if kind == "restaurant":
            cur.execute("""
                SELECT rest.restaurant_name AS name,
                       round(avg(rest.overall_rating), 2) AS rating,
                       count(f.calorie_burn_key) AS requests
                FROM dw.dim_restaurant rest
                LEFT JOIN dw.fact_calorie_burn f ON f.restaurant_key = rest.restaurant_key
                WHERE rest.restaurant_name ILIKE %(query)s
                GROUP BY rest.restaurant_key
                ORDER BY requests DESC, rest.restaurant_name
                LIMIT 8
            """, {"query": f"%{query}%"})
        else:
            cur.execute("""
            SELECT r.title AS food, r.kcal_per_serving AS calories,
                   COALESCE(r.category, '') AS category,
                   count(f.calorie_burn_key) AS requests
            FROM dw.dim_recipe r
            LEFT JOIN dw.fact_calorie_burn f ON f.recipe_key = r.recipe_key
            WHERE r.title ILIKE %(query)s OR COALESCE(r.category, '') ILIKE %(query)s
            GROUP BY r.recipe_key
            ORDER BY requests DESC, r.title
            LIMIT 8
            """, {"query": f"%{query}%"})
        return [dict(row) for row in cur.fetchall()]


def calculate_route(recipe, restaurant, activity, visit_landmark, start_mode, start_lat=None, start_lng=None):
    """Resolve a real fact and calculate the selected straight-line itinerary."""
    with psycopg2.connect(DATABASE_URL) as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT r.title AS recipe, r.kcal_per_serving AS calories,
                   rest.restaurant_name AS restaurant, rest.lat AS restaurant_lat, rest.lng AS restaurant_lng,
                   a.activity_name, a.met_value, a.speed_kmh,
                   f.distance_km AS target_distance_km, f.duration_min,
                   u.weight_kg
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
        selected = dict(selected)

        if start_mode == "current" and start_lat is not None and start_lng is not None:
            origin = (float(start_lat), float(start_lng))
        else:
            origin = (float(selected["restaurant_lat"]), float(selected["restaurant_lng"]))

        landmark = None
        if visit_landmark:
            cur.execute("""
                SELECT building_name AS name, ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng
                FROM dw.dim_landmark
                ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                LIMIT 1
            """, (selected["restaurant_lng"], selected["restaurant_lat"]))
            landmark = cur.fetchone()
            if landmark:
                landmark = dict(landmark)

        cur.execute("""
            SELECT ST_Distance(
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
            ) / 1000.0 AS km_to_restaurant
        """, (origin[1], origin[0], selected["restaurant_lng"], selected["restaurant_lat"]))
        route_distance = float(cur.fetchone()["km_to_restaurant"])
        points = [{"lat": origin[0], "lng": origin[1]}]
        if landmark:
            cur.execute("""
                SELECT ST_Distance(
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                ) / 1000.0 AS km
            """, (selected["restaurant_lng"], selected["restaurant_lat"], landmark["lng"], landmark["lat"]))
            route_distance += float(cur.fetchone()["km"])
        points.append({"lat": float(selected["restaurant_lat"]), "lng": float(selected["restaurant_lng"])})
        if landmark:
            points.append({"lat": float(landmark["lat"]), "lng": float(landmark["lng"])})
        else:
            # The warehouse model represents a no-landmark itinerary as a loop.
            route_distance *= 2
            points.append({"lat": origin[0], "lng": origin[1]})

        return {
            "recipe": selected["recipe"], "restaurant": selected["restaurant"],
            "calories": int(selected["calories"]), "weight_kg": float(selected["weight_kg"]),
            "activity_name": selected["activity_name"], "duration_min": float(selected["duration_min"]),
            "target_distance_km": float(selected["target_distance_km"]),
            "route_distance_km": round(route_distance, 2), "points": points,
            "landmark": landmark, "start_mode": start_mode,
        }


class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, payload, status=200):
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            query = parse_qs(parsed.query)
            try:
                payload = fetch_dashboard(
                    food=query.get("food", [""])[0].strip(),
                    activity=query.get("activity", ["walk"])[0],
                    landmark=query.get("landmark", ["yes"])[0],
                )
                self.send_json(payload)
            except Exception as error:  # API returns a useful message to the UI
                self.send_json({"error": str(error)}, status=500)
            return

        if parsed.path == "/api/search":
            query = parse_qs(parsed.query).get("q", [""])[0].strip()
            kind = parse_qs(parsed.query).get("kind", ["recipe"])[0]
            try:
                self.send_json({"results": search_foods(query, kind)})
            except Exception as error:
                self.send_json({"error": str(error)}, status=500)
            return

        if parsed.path == "/api/route":
            query = parse_qs(parsed.query)
            try:
                result = calculate_route(
                    recipe=query.get("recipe", [""])[0],
                    restaurant=query.get("restaurant", [""])[0],
                    activity=query.get("activity", ["walk"])[0],
                    visit_landmark=query.get("landmark", ["yes"])[0] == "yes",
                    start_mode=query.get("start_mode", ["restaurant"])[0],
                    start_lat=float(query["start_lat"][0]) if query.get("start_lat") else None,
                    start_lng=float(query["start_lng"][0]) if query.get("start_lng") else None,
                )
                if result is None:
                    self.send_json({"error": "No matching recipe/activity/restaurant fact found"}, status=404)
                else:
                    self.send_json(result)
            except Exception as error:
                self.send_json({"error": str(error)}, status=500)
            return

        file_path = ROOT / ("index.html" if parsed.path in ("/", "/index.html") else parsed.path.lstrip("/"))
        if file_path.is_file() and ROOT in file_path.parents:
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        print(format % args, flush=True)


if __name__ == "__main__":
    print(f"Dashboard API listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler).serve_forever()
