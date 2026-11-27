"""Issue #9: loading of the staging zone and of the SCD1 / static dimensions, on the offline sample."""

import csv
import shutil

import pytest

pytest.importorskip("psycopg2")

from db_helpers import conn, db_url, scalar  # noqa: E402,F401  (fixtures)
from load_warehouse import load  # noqa: E402


def counts(conn):
    tables = ["dw.dim_activity", "dw.dim_recipe", "dw.dim_restaurant", "dw.dim_landmark", "staging.rejected_rows"]
    return {t: scalar(conn, f"SELECT count(*) FROM {t}") for t in tables}


def kept_rows(path):
    with open(path, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def test_first_load_inserts_every_processed_row(conn, dirs):
    processed = dirs["processed"]
    summary = load(conn, processed)
    for table, name in [("recipes", "p_recipes.csv"), ("restaurants", "p_restaurants.csv"),
                        ("landmarks", "p_landmarks.csv"), ("activities", "p_met.csv")]:
        assert summary["staging"][table] == kept_rows(processed / name), table
    # every staged row is in its dimension (the tests share one database: compare on the natural key)
    for table, dimension, key in [("recipes", "dim_recipe", "source_id"), ("restaurants", "dim_restaurant", "source_id"),
                                  ("landmarks", "dim_landmark", "source_id"), ("activities", "dim_activity", "activity_key")]:
        missing = scalar(conn, f"SELECT count(*) FROM staging.{table} s "
                               f"WHERE NOT EXISTS (SELECT 1 FROM dw.{dimension} d WHERE d.{key} = s.{key})")
        assert missing == 0, f"{missing} staging.{table} rows not in dw.{dimension}"
    rejected = sum(kept_rows(processed / f"p_{s}_rejected.csv") for s in ("recipes", "restaurants", "landmarks"))
    assert counts(conn)["staging.rejected_rows"] == rejected


def test_second_load_changes_nothing(conn, dirs):
    load(conn, dirs["processed"])
    before = counts(conn)
    summary = load(conn, dirs["processed"])
    assert all(c == {"inserted": 0, "updated": 0} for c in summary["dimensions"].values()), summary["dimensions"]
    assert counts(conn) == before            # rejected rows are replaced, not added again


def test_scd1_update_overwrites_without_new_row(conn, dirs, tmp_path):
    load(conn, dirs["processed"])
    changed = tmp_path / "processed"
    shutil.copytree(dirs["processed"], changed)
    path = changed / "p_recipes.csv"
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    title, source_id = rows[0].index("title"), rows[1][0]
    rows[1][title] = "Corrected title"
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)

    key_before = scalar(conn, "SELECT recipe_key FROM dw.dim_recipe WHERE source_id = %s", (source_id,))
    before = counts(conn)["dw.dim_recipe"]
    summary = load(conn, changed)

    assert summary["dimensions"]["dim_recipe"] == {"inserted": 0, "updated": 1}
    assert counts(conn)["dw.dim_recipe"] == before
    assert scalar(conn, "SELECT title FROM dw.dim_recipe WHERE source_id = %s", (source_id,)) == "Corrected title"
    assert scalar(conn, "SELECT recipe_key FROM dw.dim_recipe WHERE source_id = %s", (source_id,)) == key_before


def test_rejected_rows_keep_reason_and_record(conn, dirs):
    load(conn, dirs["processed"])
    assert scalar(conn, "SELECT count(*) FROM staging.rejected_rows WHERE reject_reason IS NULL OR row_data = '{}'") == 0
    assert scalar(conn, "SELECT count(*) FROM staging.rejected_rows WHERE row_data ? 'reject_reason'") == 0
