"""Load the processed files into the warehouse (issue #9).

Steps, in ONE transaction (if anything fails, the warehouse is left as it was):
  1. staging zone: TRUNCATE + COPY of data/processed/p_*.csv into staging.recipes, staging.restaurants,
     staging.landmarks and staging.activities (same columns as the CSV files)
  2. rejected rows: the rows of p_*_rejected.csv replace the previous ones of the same source in
     staging.rejected_rows (one row per rejected record, its reason and the whole record as JSON)
  3. dw zone: sql/load_dimensions.sql merges staging into the SCD1 and static dimensions

Running it twice with the same files gives the same warehouse (0 inserted, 0 updated the second time).

The folder read is the one of scripts_data_prep/config.py: data/processed/, or data/sample_run/processed/
with SAMPLE=true (DATA_DIR changes the data folder, e.g. /opt/airflow/data in Docker).

Connection: DW_DATABASE_URL (e.g. postgresql://deserveat:pw@localhost:5432/deserveat), otherwise the
standard PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE variables.

Usage:
    python src/loading/load_warehouse.py
    python src/loading/load_warehouse.py --processed-dir path/to/processed

From Airflow:
    from load_warehouse import load
    load(PostgresHook(postgres_conn_id="deserveat_dw").get_conn())
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts_data_prep"))
from config import PROCESSED_DIR  # noqa: E402  (honours SAMPLE and DATA_DIR)

LOAD_DIMENSIONS_SQL = PROJECT_ROOT / "sql" / "load_dimensions.sql"

# staging table <- processed file, rejected file (None: no rejection step), source name in rejected_rows
SOURCES = [
    ("recipes", "p_recipes.csv", "p_recipes_rejected.csv"),
    ("restaurants", "p_restaurants.csv", "p_restaurants_rejected.csv"),
    ("landmarks", "p_landmarks.csv", "p_landmarks_rejected.csv"),
    ("activities", "p_met.csv", None),
]

# Text cells can be very long (ingredients)
csv.field_size_limit(2**31 - 1)


def connect():
    url = os.environ.get("DW_DATABASE_URL")
    return psycopg2.connect(url) if url else psycopg2.connect("")


def copy_into_staging(cur, table, path):
    """TRUNCATE staging.<table>, then COPY the CSV, matching the columns by the CSV header."""
    with open(path, encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))
        f.seek(0)
        cur.execute(sql.SQL("TRUNCATE staging.{}").format(sql.Identifier(table)))
        copy = sql.SQL("COPY staging.{} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
            sql.Identifier(table), sql.SQL(", ").join(map(sql.Identifier, header)))
        cur.copy_expert(copy.as_string(cur), f)
    cur.execute(sql.SQL("SELECT count(*) FROM staging.{}").format(sql.Identifier(table)))
    return cur.fetchone()[0]


def replace_rejected_rows(cur, source, path):
    """Replace the rejected rows of one source by the rows of its p_*_rejected.csv file."""
    cur.execute("DELETE FROM staging.rejected_rows WHERE source = %s", (source,))
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        for record in csv.DictReader(f):
            record = {k: (v if v != "" else None) for k, v in record.items()}
            reason = record.pop("reject_reason")
            rows.append((source, record.get("source_id"), reason, json.dumps(record, ensure_ascii=False)))
    execute_values(
        cur,
        "INSERT INTO staging.rejected_rows (source, source_id, reject_reason, row_data) VALUES %s",
        rows, template="(%s, %s, %s, %s::jsonb)", page_size=5000)
    return len(rows)


def load(conn, processed_dir=PROCESSED_DIR):
    """Run the three steps in one transaction and return a summary {step: counts}."""
    processed_dir = Path(processed_dir)
    missing = [name for _, kept, rejected in SOURCES for name in (kept, rejected)
               if name and not (processed_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing in {processed_dir}: {missing} (run scripts_data_prep/run_pipeline.py first)")

    summary = {"staging": {}, "rejected_rows": {}, "dimensions": {}}
    try:
        with conn.cursor() as cur:
            for table, kept, rejected in SOURCES:
                summary["staging"][table] = copy_into_staging(cur, table, processed_dir / kept)
                if rejected:
                    summary["rejected_rows"][table] = replace_rejected_rows(cur, table, processed_dir / rejected)
            cur.execute(LOAD_DIMENSIONS_SQL.read_text(encoding="utf-8"))
            for dimension, inserted, updated in cur.fetchall():
                summary["dimensions"][dimension] = {"inserted": inserted, "updated": updated}
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return summary


def main():
    parser = argparse.ArgumentParser(description="Load data/processed/p_*.csv into the staging and dw zones.")
    parser.add_argument("--processed-dir", default=PROCESSED_DIR, help=f"default: {PROCESSED_DIR}")
    args = parser.parse_args()

    conn = connect()
    try:
        summary = load(conn, args.processed_dir)
    finally:
        conn.close()

    print("staging rows:      ", summary["staging"])
    print("rejected rows:     ", summary["rejected_rows"])
    print(f"\n{'dimension':<16}{'inserted':>10}{'updated':>10}")
    for dimension, counts in summary["dimensions"].items():
        print(f"{dimension:<16}{counts['inserted']:>10}{counts['updated']:>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
