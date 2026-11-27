"""Generate synthetic users and calorie-burning requests (issue #22).

Needs the dimensions already loaded (src/loading/load_warehouse.py). Writes, in ONE transaction:
  - dim_user        synthetic users g<seed>-0001, g<seed>-0002, ... with an SCD2 weight history
                    (dw.apply_user_version); the seed is in the id, so populations of different seeds coexist
  - dim_itinerary   one itinerary per request (1:1)
  - fact_calorie_burn

Reproducibility and idempotence
  - Same seed + same dimensions -> same rows. Users come from the seed; the requests of each day come
    from a generator seeded with (seed, day), so generating a whole period at once or day by day
    (e.g. a daily Airflow run with --start = --end = the day) gives the same requests.
  - A request already in fact_calorie_burn (uq_fact_request) is skipped, together with its itinerary:
    running the generator twice adds nothing the second time.

How a request is built
  - user, recipe, restaurant and activity drawn uniformly; requested_at between 08:00 and 22:59 (Lyon time)
  - kcal_to_burn = kcal_per_serving; duration and distance from MET, speed and the weight valid at requested_at
  - start: the restaurant, or (START_FROM_USER of the requests) a user position drawn within 1.5 km of
    the restaurant and stored rounded to the ~200 m grid of dim_itinerary
  - landmark (WITH_LANDMARK of the requests): one of the 5 landmarks nearest to the restaurant
  - feasibility: the straight-line legs (start -> restaurant -> landmark, or the loop back to the start)
    must fit in distance_km; otherwise the landmark is dropped (closest feasible one first), and a user
    start that does not fit falls back to the restaurant. So distance_km >= the length of the legs.

Usage:
    python src/generation/generate_requests.py                                  # 2026, seed 42, 50 users
    python src/generation/generate_requests.py --start 2026-11-27 --end 2026-11-27  # one day
    python src/generation/generate_requests.py --seed 7 --users 200 --min-per-day 5 --max-per-day 20

Connection: DW_DATABASE_URL, otherwise the standard PG* variables.
From Airflow: generate(PostgresHook(postgres_conn_id="deserveat_dw").get_conn(), start=..., end=...)
"""

import argparse
import math
import os
import random
import sys
from datetime import date, timedelta

import psycopg2
from psycopg2.extras import execute_values

DEFAULT_SEED = 42
DEFAULT_USERS = 50
USER_HISTORY_START = "2026-01-01 00:00:00"      # first version of every synthetic user (Lyon time)
WEIGHT_CHANGE_WINDOW = (date(2026, 2, 1), date(2027, 11, 30))
CHANGING_USERS = 0.30                            # share of users whose weight changes (1 or 2 times)
START_FROM_USER = 0.30                           # share of requests that start from the user's position
WITH_LANDMARK = 0.40                             # share of requests that ask for a landmark
NEAREST_LANDMARKS = 5
USER_RADIUS_KM = 1.5


def connect():
    url = os.environ.get("DW_DATABASE_URL")
    return psycopg2.connect(url) if url else psycopg2.connect("")


# ---------------------------------------------------------------------------------------------------
# Users (SCD2)
# ---------------------------------------------------------------------------------------------------

def user_histories(seed, n_users):
    """[(user_id, [(weight_kg, valid_from_local), ...])] in chronological order, from the seed only."""
    rng = random.Random(f"{seed}:users")
    users = []
    for i in range(1, n_users + 1):
        weight = round(min(140.0, max(45.0, rng.gauss(72, 13))), 1)
        history = [(weight, USER_HISTORY_START)]
        if rng.random() < CHANGING_USERS:
            span = (WEIGHT_CHANGE_WINDOW[1] - WEIGHT_CHANGE_WINDOW[0]).days
            days = sorted(rng.sample(range(span), rng.choice([1, 2])))
            for d in days:
                weight = round(min(140.0, max(45.0, weight + rng.choice([-1, 1]) * rng.uniform(1, 6))), 1)
                history.append((weight, f"{WEIGHT_CHANGE_WINDOW[0] + timedelta(days=d)} 00:00:00"))
        users.append((f"g{seed}-{i:04d}", history))
    return users


def apply_users(cur, users):
    versions = 0
    for user_id, history in users:
        for weight, valid_from in history:
            cur.execute("SELECT dw.apply_user_version(%s, %s, (%s::timestamp AT TIME ZONE 'Europe/Paris'))",
                        (user_id, weight, valid_from))
            versions += 1
    return versions


# ---------------------------------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------------------------------

def requests_for_day(seed, day, user_ids, recipes, restaurants, activities, min_per_day, max_per_day):
    """The requests of one day, drawn with a generator seeded by (seed, day)."""
    rng = random.Random(f"{seed}:{day.isoformat()}")
    rows = []
    for _ in range(rng.randint(min_per_day, max_per_day)):
        seconds = rng.randrange(8 * 3600, 23 * 3600)
        local_time = f"{day.isoformat()} {seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
        from_user = rng.random() < START_FROM_USER
        rows.append((
            rng.choice(user_ids),
            rng.choice(recipes),
            rng.choice(restaurants),
            rng.choice(activities),
            local_time,
            rng.randrange(NEAREST_LANDMARKS) if rng.random() < WITH_LANDMARK else None,
            USER_RADIUS_KM * math.sqrt(rng.random()) if from_user else None,   # uniform in the disc
            rng.uniform(0, 360) if from_user else None,
        ))
    return rows


BUILD_SQL = """
-- 1. resolve the keys and compute duration / distance; drop requests already in the fact table
CREATE TEMP TABLE gen_resolved ON COMMIT DROP AS
SELECT g.request_no, g.landmark_rank, g.start_offset_km, g.start_bearing_deg,
       g.requested_at, u.user_key, r.recipe_key, r.kcal_per_serving AS kcal,
       rs.restaurant_key, rs.geom AS restaurant_geom, rs.lat, rs.lng, a.activity_key,
       to_char(g.requested_at AT TIME ZONE 'Europe/Paris', 'YYYYMMDD')::INT AS date_key,
       ROUND(60 * r.kcal_per_serving / (a.met_value * u.weight_kg), 1)          AS duration_min,
       ROUND(a.speed_kmh * r.kcal_per_serving / (a.met_value * u.weight_kg), 2) AS distance_km
FROM gen_request g
JOIN dw.dim_user       u  ON u.user_key = dw.user_key_at(g.user_id, g.requested_at)
JOIN dw.dim_recipe     r  ON r.source_id = g.recipe_source_id
JOIN dw.dim_restaurant rs ON rs.source_id = g.restaurant_source_id
JOIN dw.dim_activity   a  ON a.activity_key = g.activity_key
WHERE NOT EXISTS (
    SELECT 1 FROM dw.fact_calorie_burn f
    WHERE (f.user_key, f.recipe_key, f.restaurant_key, f.activity_key, f.requested_at)
        = (u.user_key, r.recipe_key, rs.restaurant_key, a.activity_key, g.requested_at));

-- 2. start point: the rounded user position if the loop start -> restaurant -> start fits, else the restaurant
CREATE TEMP TABLE gen_start ON COMMIT DROP AS
SELECT q.request_no,
       CASE WHEN p.user_point IS NOT NULL AND 2 * ST_Distance(p.user_point, q.restaurant_geom) / 1000 <= q.distance_km
            THEN 'user_location' ELSE 'restaurant' END AS start_type,
       CASE WHEN p.user_point IS NOT NULL AND 2 * ST_Distance(p.user_point, q.restaurant_geom) / 1000 <= q.distance_km
            THEN p.user_point ELSE q.restaurant_geom END AS start_point
FROM gen_resolved q
LEFT JOIN LATERAL (
    SELECT ST_SnapToGrid(ST_SetSRID(ST_MakePoint(
               q.lng + q.start_offset_km * sin(radians(q.start_bearing_deg)) / (111.32 * cos(radians(q.lat))),
               q.lat + q.start_offset_km * cos(radians(q.start_bearing_deg)) / 111.32), 4326),
           0.0026, 0.0018)::GEOGRAPHY AS user_point
    WHERE q.start_offset_km IS NOT NULL
) p ON TRUE;

-- 3. landmark: among the 5 nearest to the restaurant, the drawn rank if its legs fit in distance_km,
--    otherwise the closest rank that fits; none if no candidate fits
CREATE TEMP TABLE gen_landmark ON COMMIT DROP AS
SELECT q.request_no, c.landmark_key, c.geom
FROM gen_resolved q
JOIN gen_start s USING (request_no)
JOIN LATERAL (
    SELECT n.landmark_key, n.geom
    FROM (SELECT l.landmark_key, l.geom,
                 row_number() OVER (ORDER BY l.geom <-> q.restaurant_geom, l.landmark_key) - 1 AS rank
          FROM (SELECT landmark_key, geom FROM dw.dim_landmark
                ORDER BY geom <-> q.restaurant_geom, landmark_key LIMIT %(nearest)s) l) n
    WHERE (ST_Distance(s.start_point, q.restaurant_geom) + ST_Distance(q.restaurant_geom, n.geom)) / 1000
          <= q.distance_km
    ORDER BY abs(n.rank - q.landmark_rank), n.rank
    LIMIT 1
) c ON TRUE
WHERE q.landmark_rank IS NOT NULL;

-- 4. one itinerary key per request, taken from the identity sequence of dim_itinerary
ALTER TABLE gen_resolved ADD COLUMN itinerary_key INT;
UPDATE gen_resolved SET itinerary_key = nextval(pg_get_serial_sequence('dw.dim_itinerary', 'itinerary_key'));

INSERT INTO dw.dim_itinerary (itinerary_key, start_type, start_point, end_point, route_steps)
SELECT q.itinerary_key, s.start_type, s.start_point, COALESCE(l.geom, s.start_point), NULL
FROM gen_resolved q
JOIN gen_start s USING (request_no)
LEFT JOIN gen_landmark l USING (request_no);

INSERT INTO dw.fact_calorie_burn (recipe_key, activity_key, landmark_key, user_key, restaurant_key, date_key,
                                  itinerary_key, kcal_to_burn, distance_km, duration_min, requested_at)
SELECT q.recipe_key, q.activity_key, l.landmark_key, q.user_key, q.restaurant_key, q.date_key,
       q.itinerary_key, q.kcal, q.distance_km, q.duration_min, q.requested_at
FROM gen_resolved q
LEFT JOIN gen_landmark l USING (request_no)
ON CONFLICT DO NOTHING;
"""


def generate(conn, start=date(2026, 1, 1), end=date(2026, 12, 31), seed=DEFAULT_SEED, n_users=DEFAULT_USERS,
             min_per_day=0, max_per_day=6):
    """Generate users and the requests of [start, end] in one transaction; return a summary."""
    if end < start:
        raise ValueError("end is before start")
    try:
        with conn.cursor() as cur:
            users = user_histories(seed, n_users)
            versions = apply_users(cur, users)

            # Draw lists in a fixed order (natural keys), so the same dimensions give the same draws
            cur.execute("SELECT source_id FROM dw.dim_recipe ORDER BY source_id")
            recipes = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT source_id FROM dw.dim_restaurant ORDER BY source_id")
            restaurants = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT activity_key FROM dw.dim_activity ORDER BY activity_key")
            activities = [r[0] for r in cur.fetchall()]
            if not (recipes and restaurants and activities):
                raise RuntimeError("dim_recipe, dim_restaurant and dim_activity must be loaded first "
                                   "(src/loading/load_warehouse.py)")

            user_ids = [u for u, _ in users]
            requests = []
            day = start
            while day <= end:
                requests += requests_for_day(seed, day, user_ids, recipes, restaurants, activities,
                                             min_per_day, max_per_day)
                day += timedelta(days=1)

            cur.execute("""
                CREATE TEMP TABLE gen_request (
                    request_no            INT PRIMARY KEY,
                    user_id               TEXT,
                    recipe_source_id      INT,
                    restaurant_source_id  BIGINT,
                    activity_key          INT,
                    requested_at          TIMESTAMPTZ,
                    landmark_rank         INT,
                    start_offset_km       DOUBLE PRECISION,
                    start_bearing_deg     DOUBLE PRECISION
                ) ON COMMIT DROP""")
            execute_values(
                cur,
                "INSERT INTO gen_request VALUES %s ON CONFLICT DO NOTHING",
                [(i, *row) for i, row in enumerate(requests, 1)],
                template="(%s, %s, %s, %s, %s, (%s::timestamp AT TIME ZONE 'Europe/Paris'), %s, %s, %s)",
                page_size=5000)
            # Two identical draws (same user, recipe, restaurant, activity and second) count as one request
            cur.execute("""
                DELETE FROM gen_request g USING gen_request h
                WHERE (g.user_id, g.recipe_source_id, g.restaurant_source_id, g.activity_key, g.requested_at)
                    = (h.user_id, h.recipe_source_id, h.restaurant_source_id, h.activity_key, h.requested_at)
                  AND g.request_no > h.request_no""")

            cur.execute(BUILD_SQL, {"nearest": NEAREST_LANDMARKS})
            cur.execute("""
                SELECT count(*), count(*) FILTER (WHERE l.request_no IS NOT NULL),
                       count(*) FILTER (WHERE s.start_type = 'user_location')
                FROM gen_resolved q JOIN gen_start s USING (request_no)
                LEFT JOIN gen_landmark l USING (request_no)""")
            inserted, with_landmark, from_user = cur.fetchone()
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"users": n_users, "user_versions_applied": versions, "requests_drawn": len(requests),
            "facts_inserted": inserted, "already_present": len(requests) - inserted,
            "with_landmark": with_landmark, "from_user_location": from_user}


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic users and requests into dw.")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 12, 31))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--users", type=int, default=DEFAULT_USERS)
    parser.add_argument("--min-per-day", type=int, default=0)
    parser.add_argument("--max-per-day", type=int, default=6)
    args = parser.parse_args()

    conn = connect()
    try:
        summary = generate(conn, args.start, args.end, args.seed, args.users, args.min_per_day, args.max_per_day)
    finally:
        conn.close()
    for key, value in summary.items():
        print(f"{key:<22}{value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
