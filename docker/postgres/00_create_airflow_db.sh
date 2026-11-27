#!/bin/bash
# Runs once, when the Postgres volume is empty (docker-entrypoint-initdb.d), before 10_ddl.sql.
# Creates the Airflow metadata database next to the warehouse, with its own user.
# No `set -u` here: on Windows the file may be mounted without the executable bit, and the
# entrypoint then *sources* it; errors still stop the start (ON_ERROR_STOP + the entrypoint's set -e).

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v airflow_user="$AIRFLOW_DB_USER" -v airflow_password="$AIRFLOW_DB_PASSWORD" -v airflow_db="$AIRFLOW_DB_NAME" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'airflow_user', :'airflow_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'airflow_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'airflow_db', :'airflow_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'airflow_db') \gexec
SQL

echo "Airflow metadata database '$AIRFLOW_DB_NAME' ready (owner '$AIRFLOW_DB_USER')."
