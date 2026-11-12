# Issues GitHub — DeservEat, Assignment 2 (échéance 01/12/2026)

Comment utiliser ce fichier :
- Créez les issues **dans l'ordre** : le numéro GitHub #N correspond alors à la tâche T-N (T1 = #1, etc.). Sinon, adaptez les références « Dépend de ».
- Copiez le titre dans « Title », le bloc sous le titre dans la description. Les cases `- [ ]` deviennent des cases à cocher GitHub.
- Labels à créer : `kaguir-ingestion`, `Marti820-database`, `jvegav-airflow-analytics`, `docs`, `tests`, `blocker`, `commun`.
- Milestones à créer : `M1 Modèle aligné (15/11)`, `M2 Pipeline échantillon (22/11)`, `M3 Données réelles + analytics (29/11)`, `M4 Rendu (01/12)`.
- Workflow : une branche par issue, une Pull Request par issue, relue par les deux autres membres, fusion dans `main`.
- Commits : `feat:`, `fix:`, `test:`, `docs:`.

Assignés : Personne 1 = `@kaguir`, Personne 2 = `@Marti820`, Personne 3 = `@jvegav`

---

# PERSONNE 1 — Sources et ingestion

## #1 — Préparer les sources de données
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion`, `docs` · **Milestone :** M1 · **Branche :** `feature/issue-01-source-preparation`

**Contexte**
Les quatre sources doivent être disponibles et documentées avant toute ingestion.

**À faire**
- [x] Récupérer `recipes.zip` (GitLab, ~500 000 recettes)
- [x] Récupérer le CSV des monuments historiques (data.gouv.fr)
- [x] Ajouter la copie du CSV restaurants Lyon (Kaggle) dans le dépôt
- [ ] Ajouter le seed MET (voir #5)
- [ ] Créer `data/raw/`, `data/staging/`, `data/processed/` (avec `.gitkeep`, et `.gitignore` pour les gros fichiers)
- [x] Rédiger `docs/sources.md` : lien, licence, date de téléchargement, colonnes conservées, nombre de lignes par fichier

**Livrables** : `data/`, `docs/sources.md`
**Critères d'acceptation**
- [ ] Chaque source a un lien, une licence et un nombre de lignes documentés
- [ ] Les fichiers bruts ne sont jamais modifiés

---

## #2 — Ingestion des recettes
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion` · **Milestone :** M2 · **Branche :** `feature/issue-02-recipes-ingestion` · **Dépend de :** #1

**À faire**
- [ ] `src/ingestion/recipes.py` : lecture du ZIP par blocs (chunks)
- [ ] Extraire `source_id`, `recipe_name`, `total_kcal`, `kcal_per_serving`, `servings`, `category`, `ingredients`, `source_file`
- [ ] Dériver `category` à partir des `tags` (main, dessert, breakfast, appetizer_snack, side_salad, other)
- [ ] Gérer nulls et valeurs invalides (`kcal_per_serving` hors 1–3000, `servings` ≤ 0)
- [ ] Dédupliquer sur `source_id`
- [ ] Écrire les lignes rejetées dans `data/processed/recipes_rejected.csv` avec la règle violée
- [ ] Produire `data/processed/recipes_clean.csv`

**Critères d'acceptation**
- [ ] Les lignes valides respectent les `CHECK` du DDL (`dim_recipe`)
- [ ] Chaque rejet porte un motif
- [ ] Relancer le script ne produit pas de doublons

---

## #3 — Ingestion des restaurants
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion` · **Milestone :** M2 · **Branche :** `feature/issue-03-restaurants-ingestion` · **Dépend de :** #1

**À faire**
- [ ] `src/ingestion/restaurants.py`
- [ ] Conserver `restaurant_name`, `food_type`, `Rating`, `lat`, `lng`
- [ ] `source_id = md5(restaurant_name|lat|lng)` (même formule que `02_sample_data.sql`)
- [ ] Filtrer hors Lyon (lat 45.55–45.95, lon 4.65–5.15)
- [ ] Écrire `data/processed/restaurants_clean.csv` et le fichier de rejets
- [ ] Préparer la colonne géométrie (WKT ou lat/lon pour construction côté SQL)

**Critères d'acceptation**
- [ ] Toutes les coordonnées sont dans la bounding box
- [ ] `source_id` unique

---

## #4 — Ingestion des monuments historiques
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion` · **Milestone :** M2 · **Branche :** `feature/issue-04-landmarks-ingestion` · **Dépend de :** #1

**À faire**
- [ ] `src/ingestion/landmarks.py`
- [ ] Conserver référence Mérimée, nom, adresse, commune, code INSEE, lat, lon
- [ ] Filtrer hors Lyon (INSEE 69381–69389 et bounding box)
- [ ] Gérer les coordonnées manquantes (rejet tracé)
- [ ] Préparer la ligne spéciale `landmark_key = -1` / « No landmark » (à valider avec @Marti820)
- [ ] Écrire `data/processed/landmarks_clean.csv` et le fichier de rejets

**Critères d'acceptation**
- [ ] Aucun monument hors Lyon
- [ ] Référence Mérimée unique

---

## #5 — Données de référence : activités MET et dim_date
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion` · **Milestone :** M2 · **Branche :** `feature/issue-05-reference-data`

**À faire**
- [ ] `data/raw/met_activities.csv` : walking (intensité 1, MET 3.5, 4.8 km/h), running (3, 9.8, 9.7), cycling (2, 8.0, 20.0)
- [ ] Citer les codes du Compendium of Physical Activities dans `docs/sources.md`
- [ ] Script de génération de `dim_date` (plage couvrant toutes les dates de requêtes, par exemple 2026–2027)
- [ ] Colonnes : `date_key` (YYYYMMDD), `full_date`, `day_of_week` (ISO), `day_name`, `month`, `year`, `is_weekend`

**Critères d'acceptation**
- [ ] MET et vitesses > 0
- [ ] Une ligne par jour, sans trou

---

## #6 — Tests d'ingestion
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion`, `tests` · **Milestone :** M2 · **Branche :** `feature/issue-06-ingestion-tests` · **Dépend de :** #2, #3, #4, #5

**À faire** (`tests/ingestion/`)
- [ ] Nombre de lignes minimum par source
- [ ] Unicité des identifiants
- [ ] Calories positives
- [ ] Poids, MET et vitesses positifs
- [ ] Coordonnées valides (WGS84, bounding box)
- [ ] Absence de doublons
- [ ] Colonnes obligatoires présentes

**Critères d'acceptation**
- [ ] `pytest tests/ingestion` passe sur l'échantillon (#19) et sur les données réelles

---

## #19 — Échantillon offline reproductible
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion`, `tests` · **Milestone :** M1 · **Branche :** `feature/issue-19-offline-sample` · **Dépend de :** #1

**À faire**
- [ ] `data/sample/` : quelques centaines de recettes, ~30 monuments de Lyon, ~20 restaurants, seed MET
- [ ] Variable d'environnement `SAMPLE=true` : les scripts lisent `data/sample/` sans accès réseau
- [ ] Test qui prouve l'exécution hors ligne (par exemple réseau désactivé ou téléchargement mocké)
- [ ] Documenter la commande de lancement dans le README

**Critères d'acceptation**
- [ ] Le pipeline complet tourne sur l'échantillon, sans internet, depuis un clone propre

---

## #20 — Journal d'ingestion et protection contre les doubles chargements
**Assigné :** @kaguir · **Labels :** `kaguir-ingestion` · **Milestone :** M2 · **Branche :** `feature/issue-20-ingestion-log` · **Dépend de :** #2

**À faire**
- [ ] Table `landing.ingestion_log` (ou fichier JSON) : source, date, hash du fichier, lignes lues, lignes rejetées
- [ ] Ignorer un fichier déjà chargé (même hash)
- [ ] Zone landing : fichiers bruts conservés sans modification

**Critères d'acceptation**
- [ ] Deux exécutions consécutives produisent le même état et une seule ligne de journal par fichier

---

# PERSONNE 2 — PostgreSQL / PostGIS et modèle

## #7 — Corriger le DDL : fact_calorie_burn et schémas
**Assigné :** @Marti820 · **Labels :** `Marti820-database`, `blocker` · **Milestone :** M1 · **Branche :** `feature/issue-07-new-ddl` · **Dépend de :** #24

**À faire** (`files/01_ddl.sql`)
- [ ] Supprimer `fact_itinerary`
- [ ] Créer `dim_user`, `dim_recipe`, `dim_restaurant`, `dim_landmark`, `dim_activity`, `dim_date`, `dim_itinerary`, `fact_calorie_burn`
- [ ] Ordre : dimensions → `dim_itinerary` → fait
- [ ] Fait : `calorie_burn_key`, `user_key`, `recipe_key`, `restaurant_key`, `activity_key`, `landmark_key` (`NOT NULL DEFAULT -1`), `itinerary_key`, `date_key`, `kcal_to_burn`, `duration_min`, `distance_km`, `requested_at`
- [ ] Créer les schémas `landing`, `staging`, `dw` et `staging.rejected_rows`
- [ ] Qualifier les tables ou documenter le `search_path`

**Critères d'acceptation**
- [ ] Le DDL s'exécute sur une base vide sans erreur
- [ ] Aucune référence à `fact_itinerary`

---

## #8 — Créer dim_itinerary
**Assigné :** @Marti820 · **Labels :** `Marti820-database` · **Milestone :** M1 · **Branche :** `feature/issue-08-dim-itinerary` · **Dépend de :** #24

**À faire**
- [ ] Colonnes `itinerary_key`, `start_type`, `start_point`, `end_point`, `route_steps`
- [ ] `CHECK (start_type IN ('user_location','restaurant'))`
- [ ] Points en `GEOGRAPHY(Point,4326)`, `route_steps JSONB` (NULL ou tableau)
- [ ] Arrondi de `start_point` à ~200 m pour les positions utilisateur (documenter la méthode)
- [ ] Documenter les décisions prises en #24 : relation 1:1 ou 1:N avec le fait, rôle du restaurant, sens de `distance_km`

**Critères d'acceptation**
- [ ] Contraintes testées (une valeur invalide de `start_type` est rejetée)

---

## #9 — Implémenter les dimensions SCD
**Assigné :** @Marti820 · **Labels :** `Marti820-database` · **Milestone :** M2 · **Branche :** `feature/issue-09-scd-dimensions` · **Dépend de :** #7

**À faire**
- [ ] SCD1 : `dim_recipe`, `dim_restaurant`, `dim_landmark` (upsert sur `source_id`)
- [ ] Statiques : `dim_activity`, `dim_date`
- [ ] SCD2 : `dim_user` avec `valid_from`, `valid_to`, `is_current`
- [ ] Contrainte d'exclusion contre les chevauchements (`btree_gist`, `tstzrange`)
- [ ] Cohérence `is_current` = (`valid_to` = `9999-12-31`)
- [ ] Fonction ou requête de recherche de la version utilisateur valide à `requested_at`
- [ ] Ligne `landmark_key = -1`

**Critères d'acceptation**
- [ ] Au plus une version courante par utilisateur, aucun chevauchement
- [ ] Une mise à jour SCD1 n'ajoute pas de ligne

---

## #10 — Mettre à jour les données d'exemple
**Assigné :** @Marti820 · **Labels :** `Marti820-database` · **Milestone :** M1 · **Branche :** `feature/issue-10-sample-data` · **Dépend de :** #7, #8

**À faire** (`files/02_sample_data.sql`)
- [ ] Supprimer les insertions dans `fact_itinerary`
- [ ] Insérer d'abord `dim_itinerary` (clés explicites), puis `fact_calorie_burn`
- [ ] Conserver utilisateurs synthétiques, recettes, restaurants et monuments d'exemple
- [ ] `landmark_key = -1` sans monument
- [ ] `dim_date` couvrant toutes les dates du sample

**Critères d'acceptation**
- [ ] Le DDL puis le sample s'exécutent sans erreur et toutes les FK sont valides

---

## #11 — Calculs métier : durée et distance
**Assigné :** @Marti820 · **Labels :** `Marti820-database` · **Milestone :** M2 · **Branche :** `feature/issue-11-business-calculations` · **Dépend de :** #9

**À faire**
- [ ] `duration_min = 60 × kcal_to_burn / (MET × weight_kg)`
- [ ] `distance_km = speed_kmh × duration_min / 60`
- [ ] Vérifier `kcal_to_burn > 0`, `duration_min > 0`, `distance_km >= 0`, FK valides
- [ ] Documenter les formules et l'hypothèse « une portion » dans le README

**Critères d'acceptation**
- [ ] Tests sur au moins 3 cas calculés à la main

---

## #12 — Contraintes et index
**Assigné :** @Marti820 · **Labels :** `Marti820-database` · **Milestone :** M2 · **Branche :** `feature/issue-12-constraints-indexes` · **Dépend de :** #7

**À faire**
- [ ] PK, FK, `CHECK`
- [ ] Index sur toutes les FK, sur `requested_at` et `date_key`
- [ ] Index GiST sur les colonnes `geography` (dimensions et `dim_itinerary`)
- [ ] `CHECK` sur `insee_code` (69381–69389, hors `-1`)
- [ ] Clé d'unicité d'idempotence sur le fait (par exemple `user_key`, `recipe_key`, `restaurant_key`, `activity_key`, `requested_at`)

**Critères d'acceptation**
- [ ] Insérer deux fois la même demande échoue ou est ignoré (`ON CONFLICT DO NOTHING`)

---

## #21 — Environnement Docker reproductible
**Assigné :** @Marti820 · **Labels :** `Marti820-database`, `blocker` · **Milestone :** M1 · **Branche :** `feature/issue-21-docker`

**À faire**
- [ ] `docker-compose.yml` : PostGIS, Airflow (webserver, scheduler), volumes persistants
- [ ] `.env.example` (aucun mot de passe réel dans le dépôt)
- [ ] Exécution automatique du DDL au premier démarrage
- [ ] Commande de lancement unique documentée dans le README
- [ ] Vérification de santé (healthcheck) de PostgreSQL

**Critères d'acceptation**
- [ ] `docker compose up` depuis un clone propre démarre la base et Airflow
- [ ] Les données survivent à un redémarrage (volumes)

---

## #22 — Génération des utilisateurs et demandes synthétiques
**Assigné :** @Marti820 · **Labels :** `Marti820-database` · **Milestone :** M3 · **Branche :** `feature/issue-22-synthetic-data` · **Dépend de :** #8, #9, #11

**À faire** (`src/generation/`)
- [ ] Générer des utilisateurs avec quelques changements de poids (SCD2)
- [ ] Générer des demandes : choix de recette, restaurant, activité, monument optionnel, horodatage
- [ ] Construire `dim_itinerary` et `fact_calorie_burn` avec les bonnes clés (version utilisateur valide à `requested_at`)
- [ ] Graine fixe (reproductible) et volume paramétrable

**Critères d'acceptation**
- [ ] Deux exécutions avec la même graine donnent les mêmes lignes, sans doublon

---

# PERSONNE 3 — Airflow, qualité et analytics

## #13 — Pipeline Airflow
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics` · **Milestone :** M2 · **Branche :** `feature/issue-13-airflow-dag` · **Dépend de :** #6, #7, #21

**À faire** (`dags/`)
- [ ] Étapes : `download_sources` → `load_raw_data` → `clean_and_validate` → `load_dimensions` → `generate_itineraries` → `load_fact_calorie_burn` → `run_quality_checks`
- [ ] Relançable sans doublons (upserts, `ON CONFLICT`)
- [ ] Paramètre `SAMPLE=true` (mode offline, voir #19)
- [ ] Réessais et journalisation par tâche

**Critères d'acceptation**
- [ ] Le DAG réussit sur l'échantillon, puis une seconde exécution ne change pas les comptages

---

## #14 — Contrôles de qualité
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics`, `tests` · **Milestone :** M3 · **Branche :** `feature/issue-14-quality-checks` · **Dépend de :** #9, #12

**À faire** (`tests/quality/`)
- [ ] Nulls, unicité, plages numériques, coordonnées, clés étrangères
- [ ] Présence de la ligne `-1` dans `dim_landmark`
- [ ] Cohérence des dates et des versions SCD2
- [ ] Contrôles croisés : `distance_km` cohérent avec `ST_Distance(start_point, end_point)`, `end_point` cohérent avec `landmark_key`
- [ ] Le pipeline échoue si un contrôle critique échoue
- [ ] Nombre de lignes par couche enregistré (landing, staging, dw)

**Critères d'acceptation**
- [ ] Une donnée volontairement corrompue fait échouer le DAG (preuve en capture)

---

## #15 — Requêtes KPI
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics` · **Milestone :** M3 · **Branche :** `feature/issue-15-kpi-queries` · **Dépend de :** #10

**À faire** (`analytics/`)
- [ ] Q1 demandes par jour, semaine, mois
- [ ] Q2 activités les plus choisies
- [ ] Q3 recettes avec le plus de calories
- [ ] Q4 durée moyenne par activité
- [ ] Q5 durée par tranche de poids
- [ ] Q6 restaurants les plus associés aux demandes
- [ ] Q7 taux d'inclusion des monuments et monuments les plus choisis
- [ ] Q8 distance moyenne par activité et catégorie de recette
- [ ] Utiliser `fact_calorie_burn` (jamais `fact_itinerary`) et qualifier les tables (`dw.`)

**Critères d'acceptation**
- [ ] Les 8 requêtes s'exécutent sur le sample et retournent des résultats cohérents

---

## #16 — Notebook et dashboard
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics` · **Milestone :** M3 · **Branche :** `feature/issue-16-notebook-dashboard` · **Dépend de :** #15

**À faire**
- [ ] `analytics/notebook.ipynb` : connexion PostgreSQL, exécution des requêtes, graphiques
- [ ] Indicateurs : nombre total de demandes, durée moyenne, activité la plus utilisée, restaurant le plus demandé, % de trajets avec monument, distance moyenne, répartition par jour ou mois
- [ ] Dashboard ou vue analytique (outil au choix) dans `dashboard/`
- [ ] Précision dans le notebook : ce sont des estimations, pas des calories réellement brûlées

**Critères d'acceptation**
- [ ] Le notebook s'exécute de bout en bout après `docker compose up` et le DAG

---

## #17 — Test de bout en bout
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics`, `tests`, `commun` · **Milestone :** M4 · **Branche :** `feature/issue-17-end-to-end-test` · **Dépend de :** #13, #14, #15, #16

**À faire**
- [ ] Depuis un clone propre : démarrage Docker, DDL, chargement des dimensions, chargement des faits
- [ ] Exécution du DAG et des tests
- [ ] Exécution des requêtes
- [ ] Seconde exécution : aucun doublon (comptages identiques)
- [ ] Refaire le test sur les données réelles, puis sur une autre machine
- [ ] Consigner les résultats dans `docs/e2e_test.md` (commandes, comptages, captures)

**Critères d'acceptation**
- [ ] Tout passe sur échantillon (offline) et sur données réelles

---

## #18 — README et démonstration finale
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics`, `docs` · **Milestone :** M4 · **Branche :** `feature/issue-18-readme-demo` · **Dépend de :** #17

**À faire**
- [ ] README : installation, commandes, structure du projet, architecture, modèle relationnel, datasets, choix SCD, requêtes, limites, résultats, répartition du travail
- [ ] Corriger la ligne `dim_itinerary` du tableau SCD (section 5) qui casse le rendu
- [ ] Aligner les mentions du README avec le DDL final
- [ ] Démo de 5 à 10 minutes, captures d'écran, résultats des requêtes principales

**Critères d'acceptation**
- [ ] Un lecteur extérieur peut lancer le projet avec le seul README

---

## #23 — Documentation des règles de nettoyage, validation et intégration
**Assigné :** @jvegav · **Labels :** `jvegav-airflow-analytics`, `docs` · **Milestone :** M3 · **Branche :** `feature/issue-23-rules-doc` · **Dépend de :** #2, #3, #4, #14

**À faire**
- [ ] `docs/data_quality_rules.md` : pour chaque règle, la condition, l'action (rejet, normalisation, échec du pipeline), la table concernée
- [ ] Couvrir nettoyage, validation, intégration (clés, SCD, ligne `-1`)
- [ ] Demander à @kaguir et @Marti820 de compléter leurs parties

**Critères d'acceptation**
- [ ] Chaque contrôle du code correspond à une règle documentée

---

# TÂCHES COMMUNES

## #24 — Alignement du modèle (phase 1)
**Assigné :** @Marti820 (pilote), @kaguir, @jvegav · **Labels :** `commun`, `blocker`, `docs` · **Milestone :** M1 · **Branche :** `feature/issue-24-model-alignment`

**À décider et consigner**
- [ ] Grain de `fact_calorie_burn`
- [ ] Rôle de `dim_itinerary` : relation 1:1 ou 1:N avec le fait
- [ ] Rôle du restaurant quand `start_type = user_location`
- [ ] Sens de `distance_km` (aller simple ou aller-retour)
- [ ] Sort de `route_steps` (rempli ou NULL)

**À faire**
- [ ] Refaire `star_schema.jpeg` (fait renommé, `dim_itinerary`, 7 dimensions, `itinerary_key`)
- [ ] Refaire `architecture_diagram.jpeg` (retirer `fact_itinerary`, restaurants obligatoires, retirer « chained landmarks » ou le marquer hors périmètre)
- [ ] Corriger le README (sections 5 et 9)

**Critères d'acceptation**
- [ ] README, DDL et diagrammes décrivent le même modèle

---

## #25 — Bilan des déficiences de l'Assignment 1
**Assigné :** @jvegav (relecture @kaguir, @Marti820) · **Labels :** `commun`, `docs` · **Milestone :** M4 · **Branche :** `feature/issue-25-assignment1-review`

**À faire**
- [ ] `docs/assignment1_review.md` : tableau « point du feedback / statut (corrigé, reporté, invalidé) / preuve (commit, fichier, capture) »
- [ ] Justifier chaque point reporté ou invalidé

**Critères d'acceptation**
- [ ] Chaque remarque du feedback de l'Assignment 1 est traitée

---

## #26 — Preuves de fonctionnement
**Assigné :** @kaguir, @Marti820, @jvegav (assemblage : @jvegav) · **Labels :** `commun`, `docs` · **Milestone :** M4 · **Branche :** `feature/issue-26-evidence`

**À faire**
- [ ] Captures du DAG en succès (Airflow)
- [ ] Journaux d'exécution, résultats des contrôles de qualité
- [ ] Comptage de lignes par couche (landing, staging, dw)
- [ ] Résultats des 8 requêtes
- [ ] Preuve de l'exécution sur l'échantillon offline
- [ ] Rassembler dans `docs/evidence/`

**Critères d'acceptation**
- [ ] Chaque exigence de l'énoncé de l'Assignment 2 a une preuve référencée dans le README

---

## #27 — Revue croisée et préparation du rendu
**Assigné :** @kaguir, @Marti820, @jvegav · **Labels :** `commun` · **Milestone :** M4 · **Branche :** `feature/issue-27-final-review`

**À faire**
- [ ] Relecture des Pull Requests restantes
- [ ] Vérification de la checklist de l'énoncé (Docker, DAGs, ingestion, staging et production persistants, règles documentées, étoile peuplée, requêtes, notebook, échantillon offline, bilan Assignment 1)
- [ ] Gel de `main` avant le 01/12/2026
- [ ] Vérifier qu'aucun secret ni gros fichier n'est dans le dépôt

**Critères d'acceptation**
- [ ] Tag `assignment-2` sur `main`
