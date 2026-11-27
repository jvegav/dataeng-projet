"""Production DAG for the DeservEat pipeline."""

import sys
from datetime import datetime

from airflow.decorators import dag, task
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

sys.path[:0] = ["/opt/airflow/src/loading", "/opt/airflow/src/generation"]
DW_CONN_ID = "deserveat_dw"


@dag(
    dag_id="deserveat_pipeline",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1},
    tags=["deserveat", "etl", "analytics"],
)
def deserveat_pipeline():
    ingest = BashOperator(
        task_id="ingest_and_clean",
        bash_command="python /opt/airflow/scripts_data_prep/run_pipeline.py",
    )

    @task
    def load_dimensions():
        from load_warehouse import load
        hook = PostgresHook(postgres_conn_id=DW_CONN_ID)
        with hook.get_conn() as conn:
            result = load(conn)
        print(result)
        return result

    @task
    def generate_requests(ds=None):
        from datetime import date
        from generate_requests import generate
        day = date.fromisoformat(ds)
        hook = PostgresHook(postgres_conn_id=DW_CONN_ID)
        with hook.get_conn() as conn:
            result = generate(conn, start=day, end=day)
        print(result)
        return result

    @task
    def run_quality_checks():
        """Fail the DAG if a cross-table invariant is broken."""
        hook = PostgresHook(postgres_conn_id=DW_CONN_ID)
        checks = {
            "wrong_user_version": """
                SELECT count(*) FROM dw.fact_calorie_burn f
                JOIN dw.dim_user u ON u.user_key = f.user_key
                WHERE f.user_key <> dw.user_key_at(u.user_id, f.requested_at)
            """,
            "wrong_duration_or_distance": """
                SELECT count(*) FROM dw.fact_calorie_burn f
                JOIN dw.dim_user u ON u.user_key = f.user_key
                JOIN dw.dim_activity a ON a.activity_key = f.activity_key
                WHERE abs(f.duration_min - round(60 * f.kcal_to_burn / (a.met_value * u.weight_kg), 1)) > 0.11
                   OR abs(f.distance_km - round(a.speed_kmh * f.kcal_to_burn / (a.met_value * u.weight_kg), 2)) > 0.011
            """,
            "legs_longer_than_distance": """
                SELECT count(*) FROM dw.fact_calorie_burn f
                JOIN dw.dim_itinerary i USING (itinerary_key)
                JOIN dw.dim_restaurant r USING (restaurant_key)
                WHERE (ST_Distance(i.start_point, r.geom) + ST_Distance(r.geom, i.end_point)) / 1000
                      > f.distance_km + 0.001
            """,
            "wrong_end_point": """
                SELECT count(*) FROM dw.fact_calorie_burn f
                JOIN dw.dim_itinerary i USING (itinerary_key)
                LEFT JOIN dw.dim_landmark l USING (landmark_key)
                WHERE (l.geom IS NOT NULL AND ST_Distance(i.end_point, l.geom) > 1)
                   OR (l.geom IS NULL AND ST_Distance(i.end_point, i.start_point) > 1)
            """,
            "orphan_itineraries": """
                SELECT count(*) FROM dw.dim_itinerary i
                LEFT JOIN dw.fact_calorie_burn f USING (itinerary_key)
                WHERE f.itinerary_key IS NULL
            """,
        }
        results = {name: hook.get_first(query)[0] for name, query in checks.items()}
        if any(value != 0 for value in results.values()):
            raise ValueError(f"DeservEat quality gate failed: {results}")
        counts = {
            "facts": hook.get_first("SELECT count(*) FROM dw.fact_calorie_burn")[0],
            "users": hook.get_first("SELECT count(*) FROM dw.dim_user")[0],
            "rejected_rows": hook.get_first("SELECT count(*) FROM staging.rejected_rows")[0],
        }
        print({"checks": results, "counts": counts})
        return {"checks": results, "counts": counts}

    ingest >> load_dimensions() >> generate_requests() >> run_quality_checks()


deserveat_pipeline()
