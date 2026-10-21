-- =====================================================================
-- DeservEat – Synthetic sample data (for demo queries only)
-- Recipes, restaurants and users are FICTIONAL sample rows; landmark
-- coordinates are approximate real locations with placeholder IDs.
-- Real loads come from the Airflow staging -> production step.
-- =====================================================================
SET search_path = dw, public;

-- dim_date: generated calendar for 2026
INSERT INTO dim_date (date_key, full_date, day_of_week, day_name, month, year, is_weekend)
SELECT to_char(d, 'YYYYMMDD')::INT,
       d::DATE,
       EXTRACT(ISODOW FROM d)::INT,
       trim(to_char(d, 'Day')),
       EXTRACT(MONTH FROM d)::INT,
       EXTRACT(YEAR FROM d)::INT,
       EXTRACT(ISODOW FROM d) IN (6, 7)
FROM generate_series('2026-01-01'::DATE, '2026-12-31'::DATE, INTERVAL '1 day') AS d;

-- dim_activity: MET seed (2011 Compendium of Physical Activities, codes 17190, 12050, 01040)
INSERT INTO dim_activity (activity_key, activity_name, intensity, met_value, speed_kmh) VALUES
    (1, 'walking', 1, 3.50,  4.80),   -- walking 3.0 mph, level, moderate pace
    (2, 'running', 3, 9.80,  9.70),   -- running 6 mph (10 min/mile)
    (3, 'cycling', 2, 8.00, 20.00);   -- leisure cycling 12-13.9 mph, moderate effort

-- dim_recipe (fictional sample rows)
INSERT INTO dim_recipe (source_id, recipe_name, total_kcal, kcal_per_serving, category, ingredients, source_file, servings) VALUES
    ('sample-001', 'Classic Beef Lasagna',   4160, 520, 'main',       'lasagna noodles, ground beef, ricotta, mozzarella, tomato sauce', 'recipes.zip/pp_recipes.csv', 8),
    ('sample-002', 'Chocolate Chip Cookies', 4320, 180, 'dessert',    'flour, butter, sugar, eggs, chocolate chips',                     'recipes.zip/pp_recipes.csv', 24),
    ('sample-003', 'Greek Salad',             840, 210, 'side_salad', 'tomato, cucumber, feta, olives, olive oil',                       'recipes.zip/pp_recipes.csv', 4),
    ('sample-004', 'Tartiflette',            3300, 825, 'main',       'potatoes, reblochon, lardons, onion, cream',                     'recipes.zip/pp_recipes.csv', 4);

-- dim_restaurant (fictional sample rows, Lyon coordinates)
INSERT INTO dim_restaurant (source_id, name, cuisine, rating, lat, lon, geom) VALUES
    (md5('Bouchon Sample A|45.7640|4.8357'), 'Bouchon Sample A', 'French',  4.5, 45.7640, 4.8357, ST_SetSRID(ST_MakePoint(4.8357, 45.7640), 4326)::GEOGRAPHY),
    (md5('Trattoria Sample B|45.7578|4.8320'), 'Trattoria Sample B', 'Italian', 4.0, 45.7578, 4.8320, ST_SetSRID(ST_MakePoint(4.8320, 45.7578), 4326)::GEOGRAPHY),
    (md5('Brasserie Sample C|45.7485|4.8467'), 'Brasserie Sample C', 'Brasserie', 3.5, 45.7485, 4.8467, ST_SetSRID(ST_MakePoint(4.8467, 45.7485), 4326)::GEOGRAPHY);

-- dim_landmark: "No landmark" member + sample monuments (placeholder Mérimée IDs)
INSERT INTO dim_landmark (landmark_key, source_id, name, address, commune, insee_code, lat, lon, geom) VALUES
    (-1, 'N/A', 'No landmark', NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO dim_landmark (source_id, name, address, commune, insee_code, lat, lon, geom) VALUES
    ('PA_SAMPLE_1', 'Basilique Notre-Dame de Fourvière', 'Place de Fourvière', 'Lyon 5e Arrondissement', '69385', 45.7623, 4.8225, ST_SetSRID(ST_MakePoint(4.8225, 45.7623), 4326)::GEOGRAPHY),
    ('PA_SAMPLE_2', 'Cathédrale Saint-Jean',             'Place Saint-Jean',   'Lyon 5e Arrondissement', '69385', 45.7608, 4.8274, ST_SetSRID(ST_MakePoint(4.8274, 45.7608), 4326)::GEOGRAPHY),
    ('PA_SAMPLE_3', 'Hôtel de Ville de Lyon',            'Place des Terreaux', 'Lyon 1er Arrondissement', '69381', 45.7676, 4.8363, ST_SetSRID(ST_MakePoint(4.8363, 45.7676), 4326)::GEOGRAPHY);

-- dim_user (synthetic). u001 shows SCD Type 2: weight changed on 2026-06-01
INSERT INTO dim_user (user_id, weight_kg, valid_from, valid_to, is_current) VALUES
    ('u001', 70.0, '2026-01-01 00:00+01', '2026-06-01 00:00+02', FALSE),
    ('u001', 66.0, '2026-06-01 00:00+02', '9999-12-31 00:00+00', TRUE),
    ('u002', 55.0, '2026-01-01 00:00+01', '9999-12-31 00:00+00', TRUE),
    ('u003', 82.0, '2026-01-01 00:00+01', '9999-12-31 00:00+00', TRUE),
    ('u004', 95.0, '2026-01-01 00:00+01', '9999-12-31 00:00+00', TRUE);

-- fact_itinerary: built the same way the production step would build it.
--   duration_h  = kcal / (MET * weight_kg)        (kcal/h ≈ MET * kg)
--   distance_km = speed_kmh * duration_h
--   user_key    = dim_user version valid at requested_at (SCD2 lookup)
--   landmark    = -1 when none requested
INSERT INTO fact_itinerary (recipe_key, activity_key, landmark_key, user_key, restaurant_key, date_key,
                            start_point, end_point, kcal_to_burn, distance_km, duration_min, requested_at)
SELECT r.recipe_key,
       a.activity_key,
       COALESCE(l.landmark_key, -1),
       u.user_key,
       rs.restaurant_key,
       to_char(v.requested_at AT TIME ZONE 'Europe/Paris', 'YYYYMMDD')::INT,
       rs.geom,
       COALESCE(l.geom, rs.geom),
       r.kcal_per_serving,                                                     -- 1 serving
       ROUND(a.speed_kmh * r.kcal_per_serving / (a.met_value * u.weight_kg), 2),
       ROUND(60 * r.kcal_per_serving / (a.met_value * u.weight_kg), 1),
       v.requested_at
FROM (VALUES
    ('u001', 'sample-001', 'running', 'Bouchon Sample A',   'PA_SAMPLE_1', TIMESTAMPTZ '2026-03-14 12:10+01'),
    ('u001', 'sample-004', 'walking', 'Bouchon Sample A',   NULL,          TIMESTAMPTZ '2026-03-19 19:45+01'),
    ('u001', 'sample-001', 'running', 'Trattoria Sample B', 'PA_SAMPLE_2', TIMESTAMPTZ '2026-07-07 13:00+02'),
    ('u002', 'sample-002', 'walking', 'Trattoria Sample B', 'PA_SAMPLE_2', TIMESTAMPTZ '2026-07-05 16:20+02'),
    ('u002', 'sample-003', 'cycling', 'Brasserie Sample C', NULL,          TIMESTAMPTZ '2026-07-11 12:30+02'),
    ('u003', 'sample-004', 'cycling', 'Bouchon Sample A',   'PA_SAMPLE_3', TIMESTAMPTZ '2026-08-02 20:15+02'),
    ('u003', 'sample-001', 'walking', 'Brasserie Sample C', NULL,          TIMESTAMPTZ '2026-08-12 13:05+02'),
    ('u004', 'sample-004', 'running', 'Bouchon Sample A',   'PA_SAMPLE_1', TIMESTAMPTZ '2026-09-06 19:30+02'),
    ('u004', 'sample-002', 'cycling', 'Trattoria Sample B', 'PA_SAMPLE_3', TIMESTAMPTZ '2026-09-12 15:40+02'),
    ('u002', 'sample-001', 'running', 'Bouchon Sample A',   'PA_SAMPLE_1', TIMESTAMPTZ '2026-10-03 12:45+02'),
    ('u003', 'sample-003', 'walking', 'Trattoria Sample B', 'PA_SAMPLE_2', TIMESTAMPTZ '2026-10-14 18:00+02'),
    ('u001', 'sample-002', 'walking', 'Brasserie Sample C', NULL,          TIMESTAMPTZ '2026-10-17 11:30+02')
) AS v (user_id, recipe_src, activity, restaurant, landmark_src, requested_at)
JOIN dim_recipe     r  ON r.source_id = v.recipe_src
JOIN dim_activity   a  ON a.activity_name = v.activity
JOIN dim_restaurant rs ON rs.name = v.restaurant
JOIN dim_user       u  ON u.user_id = v.user_id
                      AND v.requested_at >= u.valid_from
                      AND v.requested_at <  u.valid_to
LEFT JOIN dim_landmark l ON l.source_id = v.landmark_src;
