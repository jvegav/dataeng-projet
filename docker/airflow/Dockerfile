# Airflow 2.10 (LocalExecutor) with the Python packages used by the pipeline.
# pandas, psycopg2 and the Postgres provider are already in the official image.
FROM apache/airflow:2.10.5-python3.11

COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt
