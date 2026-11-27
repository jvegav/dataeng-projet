"""Smoke test of the Docker environment (issue #21), not the data pipeline (issue #13).

Checks that Airflow reaches the warehouse, that 01_ddl.sql ran at the first start
(schemas and dim_date filled) and that the offline sample is mounted.
Trigger it by hand from the UI; every task must be green.
"""

from datetime import datetime
from pathlib import Path
import os

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook

DW_CONN_ID = "deserveat_dw"


@dag(
    dag_id="deserveat_smoke_test",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["deserveat", "setup"],
)
def deserveat_smoke_test():

    @task
    def warehouse_reachable():
        hook = PostgresHook(postgres_conn_id=DW_CONN_ID)
        version = hook.get_first("SELECT postgis_full_version()")[0]
        print(version)
        return version.split()[0]

    @task
    def ddl_applied():
        hook = PostgresHook(postgres_conn_id=DW_CONN_ID)
        schemas = {r[0] for r in hook.get_records(
            "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('landing','staging','dw')")}
        missing = {"landing", "staging", "dw"} - schemas
        assert not missing, f"missing schemas: {sorted(missing)}"
        days = hook.get_first("SELECT count(*) FROM dw.dim_date")[0]
        assert days == 730, f"dw.dim_date has {days} rows, expected 730"
        tables = hook.get_first(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'dw' AND table_type = 'BASE TABLE'")[0]
        assert tables == 8, f"dw has {tables} tables, expected 8 (7 dimensions + fact)"
        return {"schemas": sorted(schemas), "dim_date_rows": days, "dw_tables": tables}

    @task
    def sample_mounted():
        sample = Path(os.environ.get("DATA_DIR", "/opt/airflow/data")) / "sample"
        expected = ["r_recipes.zip", "r_landmarks.csv", "r_restaurant_data_kaggles.csv", "r_met.csv"]
        missing = [f for f in expected if not (sample / f).exists()]
        assert not missing, f"missing in {sample}: {missing}"
        return expected

    [warehouse_reachable(), ddl_applied(), sample_mounted()]


deserveat_smoke_test()
