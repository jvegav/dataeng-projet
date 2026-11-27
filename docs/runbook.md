# DeservEat: guía de ejecución y demo

## 1. Arranque

Desde la raíz del proyecto:

```bash
cp .env.example .env
# Linux: usa el UID de tu usuario para poder escribir en data/sample_run
sed -i "s/^AIRFLOW_UID=.*/AIRFLOW_UID=$(id -u)/" .env
docker compose up -d --build
docker compose ps
```

Si usas Windows/Docker Desktop, normalmente puedes conservar el valor de
`.env.example`. En Linux, el `AIRFLOW_UID` debe coincidir con `id -u`; de lo
contrario el scheduler puede leer los datos montados, pero no escribir los
ficheros temporales de `data/sample_run/`.

Airflow queda en `http://localhost:8080`; las credenciales son las de `.env`.
El almacén queda en PostgreSQL/PostGIS en `localhost:5432`.

## 2. Validar la instalación

En Airflow activa y ejecuta primero `deserveat_smoke_test`. Sus tres tareas deben
terminar en verde. Después activa `deserveat_pipeline` y pulsa **Trigger DAG**.

El DAG ejecuta, en este orden:

1. `ingest_and_clean`: raw → staging/processed; las fuentes sin cambios se omiten.
2. `load_dimensions`: COPY transaccional + dimensiones SCD1/SCD2.
3. `generate_requests`: usuarios, itinerarios y hechos del día lógico del DAG.
4. `run_quality_checks`: controles cruzados; un resultado distinto de cero falla el DAG.

Para el sample offline no hace falta descargar nada: `.env` usa `SAMPLE=true`.

## 3. Poblar todo 2026 de una vez

El DAG diario está pensado para operar día a día. Para llenar el año completo en
una primera demo, ejecuta dentro del scheduler:

```bash
docker compose exec airflow-scheduler python /opt/airflow/scripts_data_prep/run_pipeline.py
docker compose exec airflow-scheduler python /opt/airflow/src/loading/load_warehouse.py
docker compose exec airflow-scheduler python /opt/airflow/src/generation/generate_requests.py --start 2026-01-01 --end 2026-12-31
```

Luego ejecuta el DAG: la carga y la generación son idempotentes, por lo que no
deben aparecer duplicados.

## 4. Comprobar resultados

```bash
docker compose exec postgres psql -U deserveat -d deserveat \
  -c "SELECT count(*) AS facts FROM dw.fact_calorie_burn;"
docker compose exec postgres psql -U deserveat -d deserveat \
  -c "SELECT * FROM dw.dim_activity ORDER BY activity_key;"
```

Las consultas Q1–Q8 están en [`analytics/queries.sql`](../analytics/queries.sql).
Se pueden ejecutar con `psql` o copiar a DBeaver/pgAdmin.

## 5. Dashboard conectado a PostgreSQL

```bash
docker compose up -d dashboard
docker compose logs -f dashboard
```

Abre `http://localhost:8000`. La página consulta `/api/dashboard`; la API usa el
mismo `DW_DATABASE_URL` que Airflow y lee las tablas `dw.fact_calorie_burn`,
`dw.dim_recipe`, `dw.dim_restaurant`, `dw.dim_activity`, `dw.dim_landmark` y
`dw.dim_itinerary`. No hay credenciales de PostgreSQL en el navegador.

Flujo de uso:

1. Busca y selecciona una receta real.
2. Opcionalmente busca y selecciona un restaurante real.
3. Elige comenzar en el restaurante o permite la geolocalización del navegador.
4. Elige actividad, landmark y pulsa **Calculate route**.
5. La API devuelve calorías, duración, distancia objetivo y la geometría de la ruta.

La geometría se calcula con distancias geográficas de PostGIS en línea recta; el
enrutamiento por calles sigue siendo una limitación documentada del proyecto.

Si no hay resultados para una búsqueda, utiliza un título de receta o restaurante
que exista realmente en la base de datos. Puedes comprobarlos con:

```bash
docker compose exec postgres psql -U deserveat -d deserveat \
  -c "SELECT title FROM dw.dim_recipe LIMIT 20;"
```

## 6. Evidencia de idempotencia

Anota el conteo de `dw.fact_calorie_burn`, ejecuta de nuevo el DAG y verifica que
el conteo no aumente por duplicados. Para datos reales, coloca los tres ficheros
descritos en `data/raw/` y usa `SAMPLE=false` en `.env` antes de lanzar el pipeline.
