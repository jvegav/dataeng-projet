"""Issues #8 and #12: the constraints of dim_itinerary, dim_landmark, dim_restaurant and fact_calorie_burn.

Each statement must be refused by the database with the expected kind of error.
"""

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from db_helpers import SAMPLE_DATA, conn, db_url, run_sql_file, scalar  # noqa: F401  (fixtures)

LYON = "POINT(4.83 45.76)"

REFUSED = {
    "invalid start_type": (
        psycopg2.errors.CheckViolation,
        f"INSERT INTO dw.dim_itinerary (start_type, start_point, end_point) VALUES ('car', '{LYON}', '{LYON}')"),
    "exact (not rounded) user position": (
        psycopg2.errors.CheckViolation,
        f"INSERT INTO dw.dim_itinerary (start_type, start_point, end_point) "
        f"VALUES ('user_location', 'POINT(4.8418 45.7531)', '{LYON}')"),
    "route_steps not a JSON array": (
        psycopg2.errors.CheckViolation,
        f"INSERT INTO dw.dim_itinerary (start_type, start_point, end_point, route_steps) "
        f"VALUES ('restaurant', '{LYON}', '{LYON}', '{{\"a\": 1}}')"),
    "itinerary point outside Lyon": (
        psycopg2.errors.CheckViolation,
        f"INSERT INTO dw.dim_itinerary (start_type, start_point, end_point) VALUES ('restaurant', 'POINT(2.35 48.85)', '{LYON}')"),
    "INSEE code outside the Metropole": (
        psycopg2.errors.CheckViolation,
        f"INSERT INTO dw.dim_landmark (source_id, building_name, insee_code, lat, lon, geom) "
        f"VALUES ('PA1', 'x', '75056', 45.76, 4.83, '{LYON}')"),
    "geom not matching lat/lng": (
        psycopg2.errors.CheckViolation,
        "INSERT INTO dw.dim_restaurant (source_id, restaurant_name, lat, lng, geom) "
        "VALUES (1, 'x', 45.76, 4.83, 'POINT(4.90 45.70)')"),
    "second fact on the same itinerary (1:1)": (
        psycopg2.errors.UniqueViolation,
        "INSERT INTO dw.fact_calorie_burn (recipe_key, activity_key, user_key, restaurant_key, date_key, itinerary_key, "
        "kcal_to_burn, distance_km, duration_min, requested_at) "
        "SELECT recipe_key, activity_key, user_key, restaurant_key, date_key, itinerary_key, kcal_to_burn, distance_km, "
        "duration_min, requested_at + interval '1 minute' FROM dw.fact_calorie_burn WHERE itinerary_key = 1"),
    "date_key not the day of requested_at": (
        psycopg2.errors.CheckViolation,
        "INSERT INTO dw.fact_calorie_burn (recipe_key, activity_key, user_key, restaurant_key, date_key, itinerary_key, "
        "kcal_to_burn, distance_km, duration_min, requested_at) "
        "SELECT recipe_key, activity_key, user_key, restaurant_key, 20260101, 13, kcal_to_burn, distance_km, "
        "duration_min, requested_at FROM dw.fact_calorie_burn WHERE itinerary_key = 1"),
}


@pytest.fixture
def sample_conn(conn):
    """The test database with files/02_sample_data.sql loaded (committed: the sample is idempotent)."""
    run_sql_file(conn, SAMPLE_DATA)
    return conn


@pytest.mark.parametrize("case", REFUSED)
def test_refused(sample_conn, case):
    error, statement = REFUSED[case]
    with pytest.raises(error):
        with sample_conn.cursor() as cur:
            cur.execute(statement)


def test_same_request_twice_is_ignored(sample_conn):
    before = scalar(sample_conn, "SELECT count(*) FROM dw.fact_calorie_burn")
    with sample_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dw.fact_calorie_burn (recipe_key, activity_key, user_key, restaurant_key, date_key, itinerary_key, "
            "kcal_to_burn, distance_km, duration_min, requested_at) "
            "SELECT recipe_key, activity_key, user_key, restaurant_key, date_key, itinerary_key, kcal_to_burn, distance_km, "
            "duration_min, requested_at FROM dw.fact_calorie_burn WHERE itinerary_key = 1 ON CONFLICT DO NOTHING")
    assert scalar(sample_conn, "SELECT count(*) FROM dw.fact_calorie_burn") == before


def test_sample_runs_twice_and_rounds_user_positions(sample_conn):
    run_sql_file(sample_conn, SAMPLE_DATA)
    assert scalar(sample_conn, "SELECT count(*) FROM dw.fact_calorie_burn") == 12
    assert scalar(sample_conn, "SELECT count(*) FROM dw.dim_itinerary WHERE start_type = 'user_location'") == 4
    # the total distance to cover is never shorter than the straight line between start and end
    assert scalar(sample_conn, "SELECT count(*) FROM dw.fact_calorie_burn f JOIN dw.dim_itinerary i USING (itinerary_key) "
                               "WHERE f.distance_km < ST_Distance(i.start_point, i.end_point) / 1000") == 0
