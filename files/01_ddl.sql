-- =====================================================================
-- DeservEat - Database layout (PostgreSQL 15+ / PostGIS 3+)
--
-- Three persistent zones (in Docker they live in the Postgres volume):
--   landing  raw files are kept unchanged on disk (data/raw/); this schema is
--            reserved for the ingestion metadata of the Airflow DAG
--   staging  the processed CSV files (data/processed/p_*.csv) loaded as is,
--            plus every rejected row with its reason (staging.rejected_rows)
--   dw       production star schema: 7 dimensions + fact_calorie_burn
--
-- Grain of dw.fact_calorie_burn: ONE ROW PER DISH WHOSE CALORIES ARE TO BE BURNED,
--   for one user at one moment, with one restaurant, one activity,
--   one itinerary (1:1) and 0..1 landmark.
--
-- The script can be run several times (IF NOT EXISTS everywhere): a second run changes nothing.
-- Tables are qualified with their schema; the database search_path is also set to dw, public
-- so that the demo queries of the README can use unqualified names.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- '=' on TEXT inside the SCD2 exclusion constraint

CREATE SCHEMA IF NOT EXISTS landing;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;

SET search_path = dw, public;
DO $$ BEGIN
    EXECUTE format('ALTER DATABASE %I SET search_path = dw, public', current_database());
END $$;


-- =====================================================================
-- STAGING ZONE - one table per processed file, same columns as the CSV
-- (filled by the DAG with COPY, then merged into dw by sql/load_dimensions.sql)
-- =====================================================================

CREATE TABLE IF NOT EXISTS staging.recipes (
    source_id         INT,
    title             TEXT,
    ingredients       TEXT,
    recipe_url        TEXT,
    servings          INT,
    kcal_per_serving  INT,
    category          TEXT,
    total_kcal        INT
);

CREATE TABLE IF NOT EXISTS staging.restaurants (
    source_id        BIGINT,
    restaurant_name  TEXT,
    food_type        TEXT,
    lat              DOUBLE PRECISION,
    lng              DOUBLE PRECISION,
    overall_rating   NUMERIC(3,2),
    district         TEXT
);

CREATE TABLE IF NOT EXISTS staging.landmarks (
    source_id      TEXT,
    commune        TEXT,
    insee_code     TEXT,
    building_name  TEXT,
    lat            DOUBLE PRECISION,
    lon            DOUBLE PRECISION,
    address        TEXT
);

CREATE TABLE IF NOT EXISTS staging.activities (
    activity_key   INT,
    activity_name  TEXT,
    speed_kmh      NUMERIC(5,2),
    met_value      NUMERIC(4,2),
    intensity      INT
);

-- Every row rejected by the processing scripts (p_*_rejected.csv) or by a load step,
-- with the rule it violated. row_data keeps the whole original row.
CREATE TABLE IF NOT EXISTS staging.rejected_rows (
    rejected_row_id  BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source           TEXT         NOT NULL CHECK (source IN ('recipes', 'restaurants', 'landmarks', 'activities', 'requests')),
    source_id        TEXT,                                   -- identifier of the row in its source, when known
    reject_reason    TEXT         NOT NULL,                  -- e.g. calories_out_of_range, outside_lyon_scope
    row_data         JSONB        NOT NULL,
    rejected_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_source_reason ON staging.rejected_rows (source, reject_reason);


-- =====================================================================
-- PRODUCTION ZONE (dw) - star schema
-- =====================================================================

-- ---------------------------------------------------------------------
-- dim_date  (Static) - one row per calendar day, 2026-01-01 to 2027-12-31
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key     INT      PRIMARY KEY,                -- YYYYMMDD, e.g. 20261020
    full_date    DATE     NOT NULL UNIQUE,
    day_of_week  INT      NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),  -- ISO: 1 = Monday
    day_name     TEXT     NOT NULL,
    month        INT      NOT NULL CHECK (month BETWEEN 1 AND 12),
    year         INT      NOT NULL,
    is_weekend   BOOLEAN  NOT NULL,
    CONSTRAINT chk_date_key CHECK (date_key = to_char(full_date, 'YYYYMMDD')::INT)
);

INSERT INTO dw.dim_date (date_key, full_date, day_of_week, day_name, month, year, is_weekend)
SELECT to_char(d, 'YYYYMMDD')::INT,
       d::DATE,
       EXTRACT(ISODOW FROM d)::INT,
       trim(to_char(d, 'Day')),
       EXTRACT(MONTH FROM d)::INT,
       EXTRACT(YEAR FROM d)::INT,
       EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series('2026-01-01'::DATE, '2027-12-31'::DATE, INTERVAL '1 day') AS d
ON CONFLICT (date_key) DO NOTHING;

-- ---------------------------------------------------------------------
-- dim_activity  (Static) - p_met.csv (Compendium of Physical Activities)
-- 9 rows: 3 speeds (slow, moderate, fast) for each of walking, running and cycling.
-- activity_key is the Compendium code of the row.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_activity (
    activity_key   INT           PRIMARY KEY,
    activity_name  TEXT          NOT NULL UNIQUE,            -- e.g. 'Moderate Walk'
    intensity      INT           NOT NULL CHECK (intensity BETWEEN 1 AND 3),  -- from the MET: 1 light, 2 moderate, 3 vigorous
    met_value      NUMERIC(4,2)  NOT NULL CHECK (met_value > 0),
    speed_kmh      NUMERIC(5,2)  NOT NULL CHECK (speed_kmh > 0)
);

-- ---------------------------------------------------------------------
-- dim_recipe  (SCD Type 1) - recipes (p_recipes.csv)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_recipe (
    recipe_key        INT   GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_id         INT   NOT NULL UNIQUE,                 -- recipe_id from the source
    title             TEXT  NOT NULL,
    total_kcal        INT   CHECK (total_kcal >= 0),         -- kcal_per_serving * servings (NULL if servings unknown)
    kcal_per_serving  INT   NOT NULL CHECK (kcal_per_serving BETWEEN 1 AND 3000),
    category          TEXT,                                  -- food.com tags of the recipe
    ingredients       TEXT,
    recipe_url        TEXT,
    servings          INT   CHECK (servings > 0)
);

-- ---------------------------------------------------------------------
-- dim_restaurant  (SCD Type 1) - Kaggle "Lyon Restaurant Reviews" (p_restaurants.csv)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_restaurant (
    restaurant_key   INT               GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_id        BIGINT            NOT NULL UNIQUE,      -- first 15 hex digits of md5(restaurant_name|lat|lng), read as a number
    restaurant_name  TEXT              NOT NULL,
    food_type        TEXT,
    lat              DOUBLE PRECISION  NOT NULL,
    lng              DOUBLE PRECISION  NOT NULL,
    geom             GEOGRAPHY(Point, 4326) NOT NULL,        -- ST_MakePoint(lng, lat)
    overall_rating   NUMERIC(3,2)      CHECK (overall_rating BETWEEN 0 AND 5),
    district         TEXT,
    -- DQ: same loose bounding box as processing_restaurants.py
    CONSTRAINT chk_restaurant_bbox CHECK (lat BETWEEN 45.4 AND 46.1 AND lng BETWEEN 4.5 AND 5.3),
    CONSTRAINT chk_restaurant_geom CHECK (ST_Y(geom::geometry) = lat AND ST_X(geom::geometry) = lng)
);
CREATE INDEX IF NOT EXISTS gix_restaurant_geom ON dw.dim_restaurant USING gist (geom);

-- ---------------------------------------------------------------------
-- dim_landmark  (SCD Type 1) - Monuments Historiques (p_landmarks.csv)
-- No "No landmark" row: a fact without landmark has landmark_key NULL.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_landmark (
    landmark_key  INT               GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_id     TEXT              NOT NULL UNIQUE CHECK (source_id ~ '^PA[0-9]+$'),  -- Merimee reference, e.g. PA00117123
    building_name TEXT              NOT NULL,
    address       TEXT,
    commune       TEXT,
    insee_code    CHAR(5)           NOT NULL,
    lat           DOUBLE PRECISION  NOT NULL,
    lon           DOUBLE PRECISION  NOT NULL,
    geom          GEOGRAPHY(Point, 4326) NOT NULL,
    -- DQ: same loose bounding box as processing_landmarks.py
    CONSTRAINT chk_landmark_coords CHECK (lat BETWEEN 45.4 AND 46.1 AND lon BETWEEN 4.5 AND 5.3),
    CONSTRAINT chk_landmark_geom CHECK (ST_Y(geom::geometry) = lat AND ST_X(geom::geometry) = lon),
    -- DQ: the 58 INSEE codes of the Métropole de Lyon (same list as processing_landmarks.py)
    CONSTRAINT chk_landmark_insee CHECK (insee_code IN (
        '69003','69029','69033','69034','69040','69044','69046','69271','69063','69273',
        '69068','69069','69071','69072','69275','69081','69276','69085','69087','69088',
        '69089','69278','69091','69096','69100','69279','69116','69117','69123','69127',
        '69282','69283','69284','69142','69143','69149','69153','69163','69286','69168',
        '69191','69194','69199','69204','69205','69207','69290','69233','69202','69292',
        '69293','69296','69244','69250','69256','69260','69266','69259'))
);
CREATE INDEX IF NOT EXISTS gix_landmark_geom ON dw.dim_landmark USING gist (geom);

-- ---------------------------------------------------------------------
-- dim_user  (SCD Type 2) - synthetic users; a new version when the weight changes
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_user (
    user_key    INT           GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    user_id     TEXT          NOT NULL,                      -- natural/business key
    weight_kg   NUMERIC(5,1)  NOT NULL CHECK (weight_kg BETWEEN 30 AND 250),
    valid_from  TIMESTAMPTZ   NOT NULL,
    valid_to    TIMESTAMPTZ   NOT NULL DEFAULT '9999-12-31 00:00:00+00',
    is_current  BOOLEAN       NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_user_validity CHECK (valid_to > valid_from),
    -- DQ: the current version is exactly the open-ended one
    CONSTRAINT chk_user_is_current CHECK (is_current = (valid_to = '9999-12-31 00:00:00+00')),
    -- DQ: the versions of one user never overlap (half-open periods [valid_from, valid_to))
    CONSTRAINT ex_user_no_overlap EXCLUDE USING gist (user_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
);
-- DQ: at most one current version per user
CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_user_current ON dw.dim_user (user_id) WHERE is_current;

-- SCD2 lookup: the version of a user that was valid at a given moment (NULL if none)
CREATE OR REPLACE FUNCTION dw.user_key_at(p_user_id TEXT, p_at TIMESTAMPTZ)
RETURNS INT LANGUAGE sql STABLE AS $$
    SELECT user_key
    FROM dw.dim_user
    WHERE user_id = p_user_id
      AND p_at >= valid_from
      AND p_at <  valid_to
$$;

-- SCD2 change: record that p_user_id weighs p_weight_kg from p_from on. Returns the user_key of that version.
--   the version valid at p_from already has this weight -> nothing changes, that version is returned
--                                 (same weight again, or the same history replayed: idempotent)
--   no version yet               -> first version, open-ended
--   new weight, after the current version starts -> the current version is closed at p_from,
--                                 a new current version starts
--   new weight, earlier date     -> error: history is only appended at the end
CREATE OR REPLACE FUNCTION dw.apply_user_version(p_user_id TEXT, p_weight_kg NUMERIC, p_from TIMESTAMPTZ)
RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
    v_current  dw.dim_user%ROWTYPE;
    v_key      INT;
BEGIN
    SELECT user_key INTO v_key
    FROM dw.dim_user
    WHERE user_id = p_user_id AND weight_kg = p_weight_kg
      AND p_from >= valid_from AND p_from < valid_to;
    IF FOUND THEN
        RETURN v_key;
    END IF;

    SELECT * INTO v_current FROM dw.dim_user WHERE user_id = p_user_id AND is_current FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO dw.dim_user (user_id, weight_kg, valid_from)
        VALUES (p_user_id, p_weight_kg, p_from)
        RETURNING user_key INTO v_key;
        RETURN v_key;
    END IF;

    IF p_from <= v_current.valid_from THEN
        RAISE EXCEPTION 'dim_user: change for % at % is not after the current version (valid from %)',
                        p_user_id, p_from, v_current.valid_from;
    END IF;

    UPDATE dw.dim_user SET valid_to = p_from, is_current = FALSE WHERE user_key = v_current.user_key;
    INSERT INTO dw.dim_user (user_id, weight_kg, valid_from)
    VALUES (p_user_id, p_weight_kg, p_from)
    RETURNING user_key INTO v_key;
    RETURN v_key;
END
$$;

-- ---------------------------------------------------------------------
-- dim_itinerary  (entity, 1:1 with the fact) - start and end of the generated route
--   start_type = 'restaurant'    : start_point = the restaurant
--   start_type = 'user_location' : start_point = the user's position snapped to a grid of
--                                  0.0026° lon x 0.0018° lat (about 200 m x 200 m in Lyon),
--                                  so the exact position is never stored; the route goes
--                                  start -> restaurant -> landmark (or back to the start)
--   end_point   = the landmark when one is chosen, otherwise start_point (loop)
--   route_steps = turn-by-turn steps, NULL for now (distances are straight-line, see README §9)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.dim_itinerary (
    itinerary_key  INT                     GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    start_type     TEXT                    NOT NULL CHECK (start_type IN ('user_location', 'restaurant')),
    start_point    GEOGRAPHY(Point, 4326)  NOT NULL,
    end_point      GEOGRAPHY(Point, 4326)  NOT NULL,
    route_steps    JSONB,
    CONSTRAINT chk_route_steps CHECK (route_steps IS NULL OR jsonb_typeof(route_steps) = 'array'),
    -- DQ: a user position is stored rounded (about 200 m), never exact
    CONSTRAINT chk_user_location_rounded CHECK (
        start_type <> 'user_location'
        OR ST_Equals(start_point::geometry, ST_SnapToGrid(start_point::geometry, 0.0026, 0.0018))),
    -- DQ: both points in the Lyon area (same bounding box as the dimensions)
    CONSTRAINT chk_itinerary_bbox CHECK (
            ST_Y(start_point::geometry) BETWEEN 45.4 AND 46.1 AND ST_X(start_point::geometry) BETWEEN 4.5 AND 5.3
        AND ST_Y(end_point::geometry)   BETWEEN 45.4 AND 46.1 AND ST_X(end_point::geometry)   BETWEEN 4.5 AND 5.3)
);
CREATE INDEX IF NOT EXISTS gix_itinerary_start ON dw.dim_itinerary USING gist (start_point);
CREATE INDEX IF NOT EXISTS gix_itinerary_end   ON dw.dim_itinerary USING gist (end_point);

-- ---------------------------------------------------------------------
-- fact_calorie_burn - one row per dish whose calories are to be burned
--   duration_min = 60 * kcal_to_burn / (met_value * weight_kg)     (kcal/h ≈ MET * kg)
--   distance_km  = speed_kmh * duration_min / 60                    total distance to cover,
--                  always >= the straight-line distance between start_point and end_point
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw.fact_calorie_burn (
    calorie_burn_key  INT           GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipe_key        INT           NOT NULL REFERENCES dw.dim_recipe (recipe_key),
    activity_key      INT           NOT NULL REFERENCES dw.dim_activity (activity_key),
    landmark_key      INT           REFERENCES dw.dim_landmark (landmark_key),   -- NULL = no landmark
    user_key          INT           NOT NULL REFERENCES dw.dim_user (user_key),  -- version valid at requested_at
    restaurant_key    INT           NOT NULL REFERENCES dw.dim_restaurant (restaurant_key),
    date_key          INT           NOT NULL REFERENCES dw.dim_date (date_key),
    itinerary_key     INT           NOT NULL REFERENCES dw.dim_itinerary (itinerary_key),
    kcal_to_burn      INT           NOT NULL CHECK (kcal_to_burn > 0),           -- 1 serving, snapshot
    distance_km       NUMERIC(7,2)  NOT NULL CHECK (distance_km >= 0),
    duration_min      NUMERIC(7,1)  NOT NULL CHECK (duration_min > 0),
    requested_at      TIMESTAMPTZ   NOT NULL,
    -- one itinerary per request (1:1)
    CONSTRAINT uq_fact_itinerary UNIQUE (itinerary_key),
    -- idempotence: the same request cannot be loaded twice (ON CONFLICT DO NOTHING in the loaders)
    CONSTRAINT uq_fact_request UNIQUE (user_key, recipe_key, restaurant_key, activity_key, requested_at),
    -- DQ: the date dimension is the day of the request, in Lyon time
    CONSTRAINT chk_fact_date CHECK (date_key = to_char(requested_at AT TIME ZONE 'Europe/Paris', 'YYYYMMDD')::INT)
);

CREATE INDEX IF NOT EXISTS ix_fact_recipe     ON dw.fact_calorie_burn (recipe_key);
CREATE INDEX IF NOT EXISTS ix_fact_activity   ON dw.fact_calorie_burn (activity_key);
CREATE INDEX IF NOT EXISTS ix_fact_landmark   ON dw.fact_calorie_burn (landmark_key);
CREATE INDEX IF NOT EXISTS ix_fact_user       ON dw.fact_calorie_burn (user_key);
CREATE INDEX IF NOT EXISTS ix_fact_restaurant ON dw.fact_calorie_burn (restaurant_key);
CREATE INDEX IF NOT EXISTS ix_fact_date       ON dw.fact_calorie_burn (date_key);
CREATE INDEX IF NOT EXISTS ix_fact_requested  ON dw.fact_calorie_burn (requested_at);
-- itinerary_key is already indexed by uq_fact_itinerary
