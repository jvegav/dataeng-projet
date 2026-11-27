"""Issue #22: synthetic users and requests (src/generation/generate_requests.py) on the offline sample."""

import sys
from datetime import date, timedelta

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from db_helpers import PROJECT_ROOT, conn, db_url, scalar  # noqa: E402,F401  (fixtures)

sys.path.insert(0, str(PROJECT_ROOT / "src" / "generation"))
from generate_requests import generate  # noqa: E402
from load_warehouse import load  # noqa: E402

START, END = date(2026, 3, 1), date(2026, 4, 30)       # two months keep the tests fast

# One row per request, described by natural keys only (surrogate keys may differ between databases)
SNAPSHOT = """
    SELECT u.user_id, r.source_id, rs.source_id, f.activity_key, l.source_id, f.requested_at,
           f.kcal_to_burn, f.duration_min, f.distance_km,
           i.start_type, ST_AsText(i.start_point), ST_AsText(i.end_point)
    FROM dw.fact_calorie_burn f
    JOIN dw.dim_user u USING (user_key)
    JOIN dw.dim_recipe r USING (recipe_key)
    JOIN dw.dim_restaurant rs USING (restaurant_key)
    JOIN dw.dim_itinerary i USING (itinerary_key)
    LEFT JOIN dw.dim_landmark l USING (landmark_key)
    WHERE u.user_id LIKE 'g42-%%'
    ORDER BY f.requested_at, u.user_id, r.source_id, rs.source_id, f.activity_key
"""


def snapshot(conn):
    with conn.cursor() as cur:
        cur.execute(SNAPSHOT)
        return cur.fetchall()


def delete_generated_requests(conn):
    with conn.cursor() as cur:
        cur.execute("""
            WITH gone AS (
                DELETE FROM dw.fact_calorie_burn f USING dw.dim_user u
                WHERE f.user_key = u.user_key AND u.user_id LIKE 'g%'
                RETURNING f.itinerary_key)
            DELETE FROM dw.dim_itinerary WHERE itinerary_key IN (SELECT itinerary_key FROM gone)""")
    conn.commit()


@pytest.fixture
def loaded(conn, dirs):
    """Dimensions loaded from the sample, no generated request yet."""
    load(conn, dirs["processed"])
    delete_generated_requests(conn)
    return conn


def test_second_run_adds_nothing(loaded):
    first = generate(loaded, START, END)
    assert first["facts_inserted"] > 0
    before = snapshot(loaded)
    second = generate(loaded, START, END)
    assert second["facts_inserted"] == 0
    assert second["already_present"] == second["requests_drawn"]
    assert snapshot(loaded) == before


def test_same_seed_gives_the_same_rows_day_by_day(loaded):
    generate(loaded, START, END)
    whole_period = snapshot(loaded)
    delete_generated_requests(loaded)
    day = START
    while day <= END:                                  # as a daily scheduled run would do
        generate(loaded, day, day)
        day += timedelta(days=1)
    assert snapshot(loaded) == whole_period


def test_other_seed_gives_other_rows(loaded):
    generate(loaded, START, START + timedelta(days=6))
    first = snapshot(loaded)
    delete_generated_requests(loaded)
    generate(loaded, START, START + timedelta(days=6), seed=7)
    assert scalar(loaded, "SELECT count(DISTINCT user_id) FROM dw.dim_user WHERE user_id LIKE 'g7-%'") == 50
    with loaded.cursor() as cur:       # same query, on the users of seed 7
        cur.execute(SNAPSHOT.replace("'g42-%%'", "'g7-%%'"))
        other = cur.fetchall()
    assert other and other != first


def test_users_have_an_scd2_history(loaded):
    generate(loaded, START, END)
    assert scalar(loaded, "SELECT count(DISTINCT user_id) FROM dw.dim_user WHERE user_id LIKE 'g42-%'") == 50
    assert scalar(loaded, "SELECT count(DISTINCT user_id) FROM dw.dim_user WHERE user_id LIKE 'g42-%' AND NOT is_current") > 0
    assert scalar(loaded, """
        SELECT count(*) FROM dw.fact_calorie_burn f JOIN dw.dim_user u USING (user_key)
        WHERE dw.user_key_at(u.user_id, f.requested_at) IS DISTINCT FROM f.user_key""") == 0


def test_itineraries_are_consistent(loaded):
    generate(loaded, START, END)
    # 1:1, no itinerary without its request
    assert scalar(loaded, """SELECT count(*) FROM dw.dim_itinerary i
                             WHERE NOT EXISTS (SELECT 1 FROM dw.fact_calorie_burn f WHERE f.itinerary_key = i.itinerary_key)""") == 0
    # end point = the landmark, or the start point for a loop
    assert scalar(loaded, """
        SELECT count(*) FROM dw.fact_calorie_burn f JOIN dw.dim_itinerary i USING (itinerary_key)
        LEFT JOIN dw.dim_landmark l USING (landmark_key)
        WHERE NOT ST_Equals(i.end_point::geometry, COALESCE(l.geom, i.start_point)::geometry)""") == 0
    # the straight-line legs start -> restaurant -> end fit in the distance to cover
    assert scalar(loaded, """
        SELECT count(*) FROM dw.fact_calorie_burn f JOIN dw.dim_itinerary i USING (itinerary_key)
        JOIN dw.dim_restaurant r USING (restaurant_key)
        WHERE (ST_Distance(i.start_point, r.geom) + ST_Distance(r.geom, i.end_point)) / 1000 > f.distance_km + 0.001""") == 0
    # both kinds of start and requests with and without landmark are generated
    assert scalar(loaded, "SELECT count(DISTINCT start_type) FROM dw.dim_itinerary") == 2
    assert scalar(loaded, "SELECT count(*) FILTER (WHERE landmark_key IS NULL) * count(*) FILTER (WHERE landmark_key IS NOT NULL) "
                          "FROM dw.fact_calorie_burn") > 0
    # requested between 08:00 and 22:59, Lyon time
    assert scalar(loaded, """SELECT count(*) FROM dw.fact_calorie_burn
                             WHERE extract(hour FROM requested_at AT TIME ZONE 'Europe/Paris') NOT BETWEEN 8 AND 22""") == 0
