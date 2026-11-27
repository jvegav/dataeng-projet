"""Issue #11: duration and distance of fact_calorie_burn, checked against values computed by hand.

    duration_min = 60 * kcal_to_burn / (met_value * weight_kg)      (kcal/h ≈ MET * kg)
    distance_km  = speed_kmh * kcal_to_burn / (met_value * weight_kg) = speed_kmh * duration_min / 60
    kcal_to_burn = kcal_per_serving (one serving)

The three cases are requests 1, 2 and 3 of files/02_sample_data.sql (user u001). Request 3 is after
u001's weight change (70 -> 66 kg on 2026-06-01): it also checks that the SCD2 version valid at
requested_at is used.
"""

from decimal import Decimal

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from db_helpers import SAMPLE_DATA, conn, db_url, run_sql_file, scalar  # noqa: E402,F401  (fixtures)

HAND_COMPUTED = {
    # itinerary_key: (weight_kg, activity, kcal, duration_min, distance_km)
    # 1: Moderate Run, MET 9.3, 9.90 km/h, lasagna 520 kcal, 70 kg
    #    60*520/(9.3*70) = 31200/651 = 47.926 -> 47.9 ; 9.90*520/651 = 5148/651 = 7.908 -> 7.91
    1: (Decimal("70.0"), "Moderate Run", 520, Decimal("47.9"), Decimal("7.91")),
    # 2: Slow Walk, MET 3.0, 4.02 km/h, tartiflette 825 kcal, 70 kg
    #    60*825/(3*70) = 49500/210 = 235.714 -> 235.7 ; 4.02*825/210 = 3316.5/210 = 15.793 -> 15.79
    2: (Decimal("70.0"), "Slow Walk", 825, Decimal("235.7"), Decimal("15.79")),
    # 3: Fast Run, MET 12.0, 12.87 km/h, lasagna 520 kcal, 66 kg (version valid from 2026-06-01)
    #    60*520/(12*66) = 31200/792 = 39.394 -> 39.4 ; 12.87*520/792 = 6692.4/792 = 8.450 -> 8.45
    3: (Decimal("66.0"), "Fast Run", 520, Decimal("39.4"), Decimal("8.45")),
}


@pytest.fixture
def sample_conn(conn):
    run_sql_file(conn, SAMPLE_DATA)
    return conn


@pytest.mark.parametrize("itinerary_key", HAND_COMPUTED)
def test_hand_computed_cases(sample_conn, itinerary_key):
    weight, activity, kcal, duration, distance = HAND_COMPUTED[itinerary_key]
    with sample_conn.cursor() as cur:
        cur.execute("""
            SELECT u.weight_kg, a.activity_name, f.kcal_to_burn, f.duration_min, f.distance_km
            FROM dw.fact_calorie_burn f
            JOIN dw.dim_user u USING (user_key)
            JOIN dw.dim_activity a USING (activity_key)
            WHERE f.itinerary_key = %s""", (itinerary_key,))
        assert cur.fetchone() == (weight, activity, kcal, duration, distance)


def test_every_fact_follows_the_formulas(sample_conn):
    """All sample facts: same formulas, one serving, positive values, consistent duration and distance."""
    wrong = scalar(sample_conn, """
        SELECT count(*)
        FROM dw.fact_calorie_burn f
        JOIN dw.dim_user u USING (user_key)
        JOIN dw.dim_activity a USING (activity_key)
        JOIN dw.dim_recipe r USING (recipe_key)
        WHERE f.kcal_to_burn <> r.kcal_per_serving
           OR f.duration_min <> round(60 * f.kcal_to_burn / (a.met_value * u.weight_kg), 1)
           OR f.distance_km  <> round(a.speed_kmh * f.kcal_to_burn / (a.met_value * u.weight_kg), 2)
           -- distance from the stored duration: duration_min is rounded to 0.1 min, so allow
           -- speed * 0.05 min / 60 (+ 0.005 for the rounding of distance_km itself)
           OR abs(f.distance_km - a.speed_kmh * f.duration_min / 60) > a.speed_kmh * 0.05 / 60 + 0.005
           OR f.kcal_to_burn <= 0 OR f.duration_min <= 0 OR f.distance_km < 0""")
    assert wrong == 0


def test_user_version_is_the_one_valid_at_request_time(sample_conn):
    wrong = scalar(sample_conn, """
        SELECT count(*)
        FROM dw.fact_calorie_burn f
        JOIN dw.dim_user u USING (user_key)
        WHERE dw.user_key_at(u.user_id, f.requested_at) IS DISTINCT FROM f.user_key""")
    assert wrong == 0
