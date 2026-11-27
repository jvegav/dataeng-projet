"""Issue #9: SCD Type 2 of dim_user (dw.apply_user_version, dw.user_key_at, overlap protection)."""

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from db_helpers import conn, db_url, scalar  # noqa: F401  (fixtures)

HISTORY = [  # user t1: 70 kg, same weight again (no change), then 66 kg from June
    ("t1", 70.0, "2026-01-01 00:00+01"),
    ("t1", 70.0, "2026-03-01 00:00+01"),
    ("t1", 66.0, "2026-06-01 00:00+02"),
]


def apply(conn, user_id, weight, at):
    return scalar(conn, "SELECT dw.apply_user_version(%s, %s, %s)", (user_id, weight, at))


def versions(conn, user_id):
    with conn.cursor() as cur:
        cur.execute("SELECT weight_kg, valid_from, valid_to, is_current FROM dw.dim_user "
                    "WHERE user_id = %s ORDER BY valid_from", (user_id,))
        return cur.fetchall()


def test_weight_change_closes_the_current_version(conn):
    for row in HISTORY:
        apply(conn, *row)
    rows = versions(conn, "t1")
    assert [(float(w), current) for w, _, _, current in rows] == [(70.0, False), (66.0, True)]
    assert rows[0][2] == rows[1][1]                      # old valid_to = new valid_from: no gap, no overlap


def test_replaying_the_history_changes_nothing(conn):
    keys = [apply(conn, *row) for row in HISTORY]
    assert [apply(conn, *row) for row in HISTORY] == keys
    assert len(versions(conn, "t1")) == 2


def test_version_valid_at_request_time(conn):
    first, _, second = [apply(conn, *row) for row in HISTORY]
    assert scalar(conn, "SELECT dw.user_key_at('t1', '2026-03-14 12:10+01')") == first
    assert scalar(conn, "SELECT dw.user_key_at('t1', '2026-06-01 00:00+02')") == second   # valid_from is included
    assert scalar(conn, "SELECT dw.user_key_at('t1', '2025-12-31 23:59+01')") is None


def test_change_before_the_current_version_is_refused(conn):
    for row in HISTORY:
        apply(conn, *row)
    with pytest.raises(psycopg2.errors.RaiseException):
        apply(conn, "t1", 80.0, "2026-04-01 00:00+02")


def test_overlapping_versions_are_refused(conn):
    apply(conn, "t2", 60.0, "2026-01-01 00:00+01")
    with pytest.raises(psycopg2.errors.ExclusionViolation):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO dw.dim_user (user_id, weight_kg, valid_from, valid_to, is_current) "
                        "VALUES ('t2', 61, '2026-02-01', '2026-03-01', FALSE)")


def test_is_current_must_match_valid_to(conn):
    with pytest.raises(psycopg2.errors.CheckViolation):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO dw.dim_user (user_id, weight_kg, valid_from, valid_to, is_current) "
                        "VALUES ('t3', 61, '2026-02-01', '2026-03-01', TRUE)")
