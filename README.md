# Deserveat — Food Calories to Physical Activities and Routes in Lyon

## 1. Business Brief

### Objective

Deserveat helps people in Lyon translate the calories of a chosen dish into an estimated amount of physical activity by generating a personalised itinerary that includes the selected restaurant and, optionally, a local heritage landmark.

### Data artefact

The main artefact is a PostgreSQL/PostGIS data warehouse organised as a star schema. Its central fact table, `fact_calorie_burn`, stores one row for each dish whose calories are to be burned for one user at one moment, with one restaurant, one activity, one itinerary and zero or one landmark. The fact table is linked to dimensions describing the user, recipe, restaurant, physical activity, itinerary, date and optional heritage landmark. Recipe calorie data, restaurant information, heritage landmark coordinates, route information and physical-activity MET values are integrated into the warehouse. Synthetic users and calorie-burning requests are generated for demonstration purposes.

The estimated activity duration and distance are calculated from the recipe calories per serving, the user's weight, the selected activity's MET value and the activity's estimated speed. These values are estimates for analytical and demonstration purposes; they do not represent measured calories burned, completed exercise or turn-by-turn road routes.

### Stakeholders

- **Primary users:** Students, runners and amateur athletes in Lyon.
- **Secondary users:** Visitors interested in discovering Lyon's heritage through food and outdoor activities.
- **Project team and data engineers:** Responsible for source integration, data quality, orchestration and warehouse maintenance.
- **Potential business partners:** Restaurants and local tourism organisations interested in food-related and active tourism.

### Key performance indicators (KPIs)

| KPI | Definition | Business meaning |
|---|---|---|
| Calorie-burning request volume | `COUNT(*)` from `fact_calorie_burn` | Measures product usage and adoption. |
| Average estimated activity duration | `AVG(duration_min)` | Measures the estimated time commitment associated with users' food choices. |
| Landmark inclusion rate | Percentage of facts with a selected landmark (`landmark_key` is not NULL) | Measures the use of the heritage-discovery feature. |

These KPIs measure generated calorie-burning requests and estimated activity. They do not measure actual calories burned or completed exercise.

### Business questions

1. How many calorie-burning requests are generated per day, week and month?
2. Which activities (walking, running or cycling) are selected most frequently?
3. Which recipes have the highest average estimated calorie content per itinerary?
4. What is the average estimated duration required for each activity type?
5. How does estimated activity duration vary across user weight ranges?
6. Which restaurants are associated with the greatest number of calorie-burning requests?
7. What proportion of requests includes a landmark, and which landmarks are selected most often?
8. How does estimated distance vary by activity type and recipe category?

## 2. Datasets

The project uses file-based batch ingestion. Raw files are retained unchanged in a landing layer so that ingestion and transformation can be replayed.

| Dataset | Source and link | Role | Expected size and columns | Refresh |
|---|---|---|---|---|
| Recipes | [Connected Recipe Data Set on GitLab](https://gitlab.com/felix134/connected-recipe-data-set/-/raw/eb672598cc4891da0eb436daefcd25b412dad641/data/hummus_data/preprocessed/pp_recipes.zip) | Recipe name, ingredients, calories and serving information | Approximately 500,000 recipes. The source contains substantially more than 1,000 rows; the final selected schema contains at least eight useful attributes, including source ID, title, calories per serving, total calories, category, ingredients, recipe URL and servings. | One-off download |
| Protected historical monuments | [French open-data dataset on data.gouv.fr](https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2) | Heritage landmark names, addresses and WGS84 coordinates | The source is a large open-government CSV with many columns and more than 1,000 records. The warehouse retains the fields needed for title, address, commune, INSEE code, latitude, longitude and geometry. | Monthly |
| Lyon restaurant reviews | Lyon Restaurant Reviews dataset (Kaggle; project copy/source URL: **[kaggle]**(https://www.kaggle.com/datasets/launay10christian/lyon-restaurant-reviews-dataset)) | Restaurant names, cuisines, ratings and coordinates used as route origins | The warehouse keeps `restaurant_name`, `food_type`, `overallRating`, `district`, `lat` and `lng`. The file is downloaded manually from Kaggle (login required) and is not versioned in the repository. | One-off download or manual refresh |
| Physical activity MET seed | Manually curated CSV based on the [Compendium of Physical Activities](https://pacompendium.com/) | MET values and estimated speeds for walking, running and cycling | Small reference seed; it is not intended to satisfy the two large-dataset requirement. The seed has 9 rows (3 speeds for each activity); its schema contains the Compendium code, activity name, intensity, MET value and speed. | Static |

The recipes and monuments datasets are the two primary qualifying datasets for this project. Their exact post-download row counts and the final source-column inventories should be recorded during ingestion validation.

The architecture diagram also shows an offline sample of a few hundred recipes and approximately 30 landmarks for reproducibility. The repository currently contains a small illustrative sample (`files/02_sample_data.sql`) used to test the schema and demo queries.

## 3. Tooling and data-engineering lifecycle

| Lifecycle stage | Tools | Purpose |
|---|---|---|
| Source ingestion | Python, `requests`, CSV/ZIP readers | Download the recipe ZIP and monuments CSV, handle chunked reading, and record ingestion metadata. |
| Landing storage | PostgreSQL and Docker volumes | Preserve raw, unchanged files and support replayable ingestion. |
| Cleaning and validation | Apache Airflow tasks, Python and SQL | Select columns, normalise names and ingredients, handle invalid records, validate coordinates, deduplicate data and enforce referential integrity. |
| Staging | PostgreSQL staging schemas | Store typed, cleaned tables before warehouse loading. |
| Production warehouse | PostgreSQL/PostGIS | Build the star schema, surrogate keys, geography columns and analytical measures. |
| Orchestration | Apache Airflow and Docker Compose | Schedule ingestion, quality gates and production transformations. |
| Analytics and reporting | SQL and Dashboard | Answer business questions and expose KPIs. |
| Version control and reproducibility | Git, Docker Compose | Version pipeline code and run the local environment consistently. |

## 4. Data Architecture

![Deserveat data architecture](architecture_diagram.jpeg)

*Figure 1 — End-to-end architecture. The source, landing, staging, production and analytics layers are shown in [architecture_diagram.jpeg](architecture_diagram.jpeg).*

### Data flow

`Raw sources → Python ingestion → Landing/raw layer → Airflow cleaning and validation → Staging tables → PostgreSQL/PostGIS production star schema → SQL analytics/reporting`

### Ingestion and update strategy

- **Recipes:** file-based batch download of `recipes.zip`; one-off load.
- **Protected monuments:** direct CSV download; monthly refresh.
- **Restaurants:** file-based load; one-off or manual refresh.
- **MET reference data:** manually maintained seed CSV; static.
- **Generated calorie-burning requests:** daily batch.
- **Landing policy:** original files are preserved unchanged, with ingestion metadata and duplicate-load protection.

### Example data-quality checks

The pipeline should fail its quality gate when a required check fails and report the failure explicitly. Examples include:

- **Null check:** recipe name, calories per serving, activity name, itinerary key and request date must not be null.
- **Uniqueness check:** source IDs must be unique within each dimension; `calorie_burn_key` must be unique in `fact_calorie_burn`; `itinerary_key` must be unique in `dim_itinerary`.
- **Range check:** calories, user weight, MET values and estimated speed must be positive.
- **Geospatial check:** monument and restaurant coordinates must be valid WGS84 points inside the Lyon bounding box (lat 45.4–46.1, lon 4.5–5.3); monuments outside the Métropole de Lyon (58 INSEE codes) and points outside the box are rejected in processing.
- **Referential-integrity check:** every fact foreign key must resolve to its corresponding dimension; facts without a landmark have a NULL `landmark_key`.

## 5. Data Model

### Grain

The grain of `fact_calorie_burn` is **one row per dish whose calories are to be burned, for one user at one moment, with one restaurant, one activity, one itinerary and zero or one landmark**. An itinerary is a reusable entity in `dim_itinerary`; the fact table references it through `itinerary_key`.

![Deserveat star schema](star_schema.jpeg)

*Figure 2 — Production star schema. The complete model is shown in [star_schema.jpeg](star_schema.jpeg).*

### Tables

#### Fact table

- **`fact_calorie_burn`** — One calorie-burning request, with foreign keys to the user, recipe, restaurant, activity, landmark, itinerary and date dimensions. It stores the calories to burn, estimated duration and distance, and the request timestamp.
- **`dim_itinerary`** — One itinerary entity referenced by the fact table. It stores the start and end geography points of the route.

#### Dimension tables and SCD choices

| Dimension | SCD type | Justification |
|---|---|---|
| `dim_recipe` | **Type 1** | Recipe corrections and normalisation should update the current descriptive value. Historical recipe versions are not a business requirement for this demonstration. |
| `dim_activity` | **Static** | Walking, running and cycling (3 speeds each) are a small controlled reference list whose MET values and speeds are maintained as a curated seed. |
| `dim_date` | **Static** | Calendar attributes are deterministic and do not change. |
| `dim_restaurant` | **Type 1** | The current restaurant name, cuisine, rating and coordinates are sufficient for the demonstration; historical restaurant changes are not currently required. |
| `dim_landmark` | **Type 1** | The current official title, address and coordinates are used. A historical preservation-status requirement has not been specified. |
| `dim_user` | **Type 2** | Weight can change over time and affects calorie-burn estimates. Effective timestamps and `is_current` preserve the user context used by each itinerary. |
| `dim_itinerary` | **Entity / static per itinerary** | Route geometry and route steps belong to the itinerary entity rather than to the calorie-burning event. An itinerary can therefore be referenced explicitly by the fact row. |

The diagram labels `dim_recipe` and `dim_restaurant` as SCD1, `dim_activity` and `dim_date` as static, and `dim_user` as SCD2. `dim_landmark` is also treated as SCD1. `dim_itinerary` is an entity dimension whose route attributes belong to the itinerary record.

## 6. Data Dictionary


Sources: **[R]** Connected Recipe Data Set `recipes.zip` (GitLab) · **[M]** data.gouv.fr Monuments Historiques CSV · **[K]** Kaggle Lyon Restaurant Reviews · **[S]** MET seed CSV (Compendium of Physical Activities) · **[G]** generated / synthetic. 

**fact_calorie_burn**: one row per dish whose calories are to be burned [G]
| Column | Type | Description |
|---|---|---|
| calorie_burn_key | INT | PK |
| user_key, recipe_key, restaurant_key, activity_key | INT | FKs to dimensions (user = version valid at request time) |
| landmark_key | INT | FK, NULL = no landmark |
| itinerary_key | INT | FK to `dim_itinerary` |
| date_key | INT | FK to `dim_date` |
| kcal_to_burn | INT | Calories to be burned for the selected dish |
| duration_min | NUMERIC(7,1) | 60 × kcal / (MET × weight) |
| distance_km | NUMERIC(7,2) | `speed_kmh × duration_min / 60` |
| requested_at | TIMESTAMPTZ | Request timestamp |

**dim_itinerary** (entity)
| Column | Type | Description |
|---|---|---|
| itinerary_key | INT | PK |
| start_point | GEOGRAPHY(Point,4326) | Route origin; rounded to approximately 200 m when based on a user location |
| end_point | GEOGRAPHY(Point,4326) | Computed route destination |

**dim_recipe** (SCD1) [R]
| Column | Type | Description |
|---|---|---|
| source_id | INT | `recipe_id` |
| title | TEXT | `title` |
| kcal_per_serving | INT | `calories [cal]` (values are already kcal, 1–3000) |
| servings | INT | `servingsPerRecipe` (NULL if missing or ≤ 0) |
| total_kcal | INT | kcal_per_serving × servings (NULL if servings is NULL) |
| category | TEXT | `tags` (food.com) |
| ingredients | TEXT | `ingredients` |
| recipe_url | TEXT | `recipe_url` |

**dim_restaurant** (SCD1) [K]
| Column | Type | Description |
|---|---|---|
| source_id | BIGINT | First 15 hex digits of md5(restaurant_name, lat, lng), read as a number |
| restaurant_name | TEXT | `restaurant_name` |
| food_type | TEXT | `food_type` |
| lat, lng | DOUBLE PRECISION | `lat`, `lng` (WGS84) |
| geom | GEOGRAPHY(Point,4326) | Built from lat/lng |
| overall_rating | NUMERIC(3,2) | `overallRating` (0–5) |
| district | TEXT | `district` |

**dim_landmark** (SCD1) [M]
| Column | Type | Description |
|---|---|---|
| source_id | TEXT | Mérimée reference (`Reference`) |
| building_name | TEXT | Monument title (`Denomination_de_l_edifice`) |
| address, commune | TEXT | Location |
| insee_code | CHAR(5) | One of the 58 INSEE codes of the Métropole de Lyon |
| lat, lon | DOUBLE PRECISION | WGS84 coordinates |
| geom | GEOGRAPHY(Point,4326) | Built from lat/lon |

**dim_activity** (Static) [S]
| Column | Type | Description |
|---|---|---|
| activity_key | INT | Compendium code |
| activity_name | TEXT | Activity and speed shown to the user, e.g. Moderate Walk |
| intensity | INT | 1 light – 3 vigorous (computed from the MET value) |
| met_value | NUMERIC(4,2) | Metabolic equivalent |
| speed_kmh | NUMERIC(5,2) | Assumed average speed |

**dim_user** (SCD2) [G]
| Column | Type | Description |
|---|---|---|
| user_id | TEXT | Business key |
| weight_kg | NUMERIC(5,1) | Weight during validity period |
| valid_from / valid_to | TIMESTAMPTZ | Validity period (`9999-12-31` if current) |
| is_current | BOOLEAN | Latest version |

**dim_date** (Static) [G]
| Column | Type | Description |
|---|---|---|
| date_key | INT | YYYYMMDD |
| full_date | DATE | Calendar date |
| day_of_week / day_name | INT / TEXT | ISO weekday (1 = Mon) / name |
| month, year | INT | Calendar parts |
| is_weekend | BOOLEAN | Sat/Sun |

## 7. Demo Queries

**-- Q1. Usage trends: calorie-burning requests per day / week / month**

```sql
SELECT d.full_date, d.day_name, COUNT(f.calorie_burn_key) AS calorie_burn_requests
FROM dim_date d
LEFT JOIN fact_calorie_burn f USING (date_key)
WHERE d.full_date BETWEEN (SELECT MIN(requested_at)::DATE FROM fact_calorie_burn)
                      AND (SELECT MAX(requested_at)::DATE FROM fact_calorie_burn)
GROUP BY d.full_date, d.day_name
ORDER BY d.full_date;
```

```sql
SELECT date_trunc('week', d.full_date)::DATE AS week_start,
       COUNT(*) AS calorie_burn_requests
FROM fact_calorie_burn f
JOIN dim_date d USING (date_key)
GROUP BY week_start
ORDER BY week_start;
```

```sql
SELECT d.year, d.month,
       COUNT(*) AS calorie_burn_requests,
       COUNT(*) FILTER (WHERE d.is_weekend) AS weekend_requests,
       COUNT(*) FILTER (WHERE NOT d.is_weekend) AS weekday_requests
FROM fact_calorie_burn f
JOIN dim_date d USING (date_key)
GROUP BY d.year, d.month
ORDER BY d.year, d.month;
```

**-- Q2. Activity preferences**

```sql
SELECT a.activity_name,
       COUNT(*) AS calorie_burn_requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM fact_calorie_burn f
JOIN dim_activity a USING (activity_key)
GROUP BY a.activity_name
ORDER BY calorie_burn_requests DESC;
```

**-- Q3. Recipes with the highest average calories to burn**

```sql
SELECT r.title, r.category,
       COUNT(*) AS calorie_burn_requests,
       ROUND(AVG(f.kcal_to_burn), 0) AS avg_kcal_to_burn
FROM fact_calorie_burn f
JOIN dim_recipe r USING (recipe_key)
GROUP BY r.recipe_key, r.title, r.category
ORDER BY avg_kcal_to_burn DESC
LIMIT 10;
```

**-- Q4. Average estimated duration by activity**

```sql
SELECT a.activity_name, a.met_value,
       COUNT(*) AS calorie_burn_requests,
       ROUND(AVG(f.duration_min), 1) AS avg_duration_min,
       ROUND(percentile_cont(0.5) WITHIN GROUP (ORDER BY f.duration_min)::NUMERIC, 1) AS median_duration_min
FROM fact_calorie_burn f
JOIN dim_activity a USING (activity_key)
GROUP BY a.activity_name, a.met_value
ORDER BY avg_duration_min DESC;
```

**-- Q5. Estimated duration by user weight range**

```sql
WITH bucketed AS (
    SELECT f.duration_min, a.activity_name,
           CASE WHEN u.weight_kg < 60 THEN 1 WHEN u.weight_kg < 75 THEN 2
                WHEN u.weight_kg < 90 THEN 3 ELSE 4 END AS bucket_order,
           CASE WHEN u.weight_kg < 60 THEN '< 60 kg' WHEN u.weight_kg < 75 THEN '60-75 kg'
                WHEN u.weight_kg < 90 THEN '75-90 kg' ELSE '90+ kg' END AS weight_range
    FROM fact_calorie_burn f
    JOIN dim_user u USING (user_key)
    JOIN dim_activity a USING (activity_key)
)
SELECT weight_range, activity_name, COUNT(*) AS calorie_burn_requests,
       ROUND(AVG(duration_min), 1) AS avg_duration_min
FROM bucketed
GROUP BY bucket_order, weight_range, activity_name
ORDER BY bucket_order, activity_name;
```

**-- Q6. Restaurant popularity**

```sql
SELECT rs.restaurant_name, rs.food_type, rs.overall_rating,
       COUNT(*) AS calorie_burn_requests,
       ROUND(AVG(f.kcal_to_burn), 0) AS avg_kcal_to_burn
FROM fact_calorie_burn f
JOIN dim_restaurant rs USING (restaurant_key)
GROUP BY rs.restaurant_key, rs.restaurant_name, rs.food_type, rs.overall_rating
ORDER BY calorie_burn_requests DESC, rs.overall_rating DESC
LIMIT 10;
```

**-- Q7. Heritage discovery**

```sql
SELECT COUNT(*) AS total_requests,
       COUNT(*) FILTER (WHERE landmark_key IS NOT NULL) AS with_landmark,
       ROUND(100.0 * COUNT(*) FILTER (WHERE landmark_key IS NOT NULL)
             / NULLIF(COUNT(*), 0), 1) AS landmark_inclusion_rate_pct
FROM fact_calorie_burn;
```

```sql
SELECT l.building_name, l.commune, COUNT(*) AS calorie_burn_requests
FROM fact_calorie_burn f
JOIN dim_landmark l USING (landmark_key)
GROUP BY l.landmark_key, l.building_name, l.commune
ORDER BY calorie_burn_requests DESC
LIMIT 10;
```

**-- Q8. Estimated distance by activity and recipe category**

```sql
SELECT a.activity_name, r.category,
       COUNT(*) AS calorie_burn_requests,
       ROUND(AVG(f.distance_km), 2) AS avg_distance_km,
       MIN(f.distance_km) AS min_distance_km,
       MAX(f.distance_km) AS max_distance_km
FROM fact_calorie_burn f
JOIN dim_activity a USING (activity_key)
JOIN dim_recipe r USING (recipe_key)
GROUP BY a.activity_name, r.category
ORDER BY a.activity_name, avg_distance_km DESC;
```

## 8. Expected Product View

![Expected product view](final_demo.jpeg)

## 9. Limitations and assumptions

- Distances are straight-line (PostGIS `ST_Distance`), not road-network routes. Chained landmarks are future work; long targets require several round trips.
- Each itinerary assumes **one serving** of the recipe (`kcal_to_burn = kcal_per_serving`).
- An itinerary without a landmark is a loop starting and ending at the restaurant.
- Calorie expenditure is estimated from MET, user weight and duration; it is not a physiological measurement.
- The project uses synthetic users and itinerary events for demonstration.

## 10. References and AI disclosure

### Data and methodology references

- [Connected Recipe Data Set](https://gitlab.com/felix134/connected-recipe-data-set/-/blob/master/data/hummus_data/raw/recipes.zip?ref_type=heads)
- [Protected historical monuments dataset — data.gouv.fr](https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2)
- [Compendium of Physical Activities](https://pacompendium.com/)
- Lyon Restaurant Reviews dataset — [restaurants](https://www.kaggle.com/datasets/launay10christian/lyon-restaurant-reviews-dataset)

### AI disclosure

Here is the link to the AI chat used during this project:
- https://claude.ai/share/d6ea6715-199d-4653-8246-9acb3b7d6132


## 11. Group Contribution

- AGUIR Kawthar 33%
- VASQUEZ Juan Martin 31%
- VEGA Josue 36%