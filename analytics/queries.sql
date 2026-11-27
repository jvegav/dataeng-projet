-- Q1: requests per day
SELECT d.full_date, d.day_name, COUNT(f.calorie_burn_key) AS requests
FROM dw.dim_date d LEFT JOIN dw.fact_calorie_burn f USING (date_key)
WHERE d.full_date BETWEEN (SELECT MIN(requested_at)::date FROM dw.fact_calorie_burn)
                      AND (SELECT MAX(requested_at)::date FROM dw.fact_calorie_burn)
GROUP BY d.full_date, d.day_name ORDER BY d.full_date;

-- Q2: activities most selected
SELECT a.activity_name, COUNT(*) AS requests,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM dw.fact_calorie_burn f JOIN dw.dim_activity a USING (activity_key)
GROUP BY a.activity_name ORDER BY requests DESC;

-- Q3: recipes with most calories
SELECT r.title, r.kcal_per_serving, COUNT(f.*) AS requests
FROM dw.fact_calorie_burn f JOIN dw.dim_recipe r USING (recipe_key)
GROUP BY r.recipe_key ORDER BY r.kcal_per_serving DESC, requests DESC LIMIT 20;

-- Q4: average duration per activity
SELECT a.activity_name, ROUND(AVG(f.duration_min), 1) AS avg_duration_min, COUNT(*) AS requests
FROM dw.fact_calorie_burn f JOIN dw.dim_activity a USING (activity_key)
GROUP BY a.activity_name ORDER BY avg_duration_min DESC;

-- Q5: average duration by weight band
SELECT CASE WHEN u.weight_kg < 60 THEN '<60 kg' WHEN u.weight_kg < 75 THEN '60–74.9 kg'
            WHEN u.weight_kg < 90 THEN '75–89.9 kg' ELSE '90+ kg' END AS weight_band,
       ROUND(AVG(f.duration_min), 1) AS avg_duration_min, COUNT(*) AS requests
FROM dw.fact_calorie_burn f JOIN dw.dim_user u USING (user_key)
GROUP BY weight_band ORDER BY weight_band;

-- Q6: restaurants most associated with requests
SELECT r.restaurant_name, COUNT(*) AS requests
FROM dw.fact_calorie_burn f JOIN dw.dim_restaurant r USING (restaurant_key)
GROUP BY r.restaurant_key ORDER BY requests DESC LIMIT 20;

-- Q7: landmark inclusion rate and most selected landmarks
SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE landmark_key IS NOT NULL) / NULLIF(COUNT(*), 0), 1)
       AS landmark_inclusion_pct FROM dw.fact_calorie_burn;
SELECT l.building_name, COUNT(*) AS requests
FROM dw.fact_calorie_burn f JOIN dw.dim_landmark l USING (landmark_key)
GROUP BY l.landmark_key ORDER BY requests DESC LIMIT 20;

-- Q8: average distance by activity and recipe category
SELECT a.activity_name, COALESCE(r.category, 'unknown') AS recipe_category,
       ROUND(AVG(f.distance_km), 2) AS avg_distance_km, COUNT(*) AS requests
FROM dw.fact_calorie_burn f JOIN dw.dim_activity a USING (activity_key)
JOIN dw.dim_recipe r USING (recipe_key)
GROUP BY a.activity_name, recipe_category ORDER BY avg_distance_km DESC;
