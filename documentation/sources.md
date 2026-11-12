# Data Sources — DeservEat

Last updated: `10/11/2026` by: @kaguir

---

## 1. Overview

| Source | Role in the project | Dimension fed | File in repository | Rows | Size | Status |
|---|---|---|---|---|---|---|---|
| Recipe Data Set (GitLab) | Calories, servings, ingredients | `dim_recipe` | `data/raw/pp_recipes.zip` | 507335 | 302 Mo | Downloaded |
| Historical monuments (data.gouv.fr) | Optional route destinations | `dim_landmark` | `data/raw/landmarks.csv` | 46761 | 95.5 Mo | Downloaded |
| Lyon restaurants (Kaggle) | Route starting points | `dim_restaurant` | `data/raw/restaurant_data_kaggles.csv` | 3059 | 493 Ko | Downloaded |
| MET (Compendium) | MET values and speeds | `dim_activity` | `data/raw/met_activities.csv` | TO FILL | TO FILL | Not Started |

---

## 2. Source sheets

### 2.1 Recipes — Recipe Data Set

**Identification**
- Exact dataset name: `HUMMUS data set`
- Provider / authors: `felix134`
- Page URL: https://gitlab.com/felix134/connected-recipe-data-set
- Direct download URL: https://gitlab.com/felix134/connected-recipe-data-set/-/blob/eb672598cc4891da0eb436daefcd25b412dad641/data/hummus_data/preprocessed/pp_recipes.zip
- Version / commit / publication date: `init commit, July 20, 2023`

**Access**
- Method: `Manual download from the Gitlab repo` 
- Download date and time: `10/11/2026 17:28`
- Update frequency: `no update since 2023`
- Command or script used: `none`

**Licence and terms of use**
- Dataset usage restrictions: `The data was collected from Food.com and may only be used for educational or scientific purposes, as stated in the dataset repository's README.`
- Code license: `GNU General Public License v3.0 (GPLv3)`
- Copyright notice (Food.com): `© 2026 Warner Bros. Discovery, Inc. or its subsidiaries and affiliates. All rights reserved.L`
- Licence text: https://www.gnu.org/licenses/gpl-3.0.en.html
- Terms of use reference: `Dataset README`

**File**
- Name and path: `data/raw/pp_recipes.zip`
- Format / encoding / delimiter: `csv in zip / utf-8 / ,`
- Compressed / uncompressed size: `302 Mo / 1.05 Go`
- ZIP contents : `pp_recipes.csv`
- Row count (after decompression, excluding header): `507335`

**Columns kept**
- `recipe_id`: An unique ID identifying each recipe
- `title`: The title of the recipe
- `ingredients`: A json-object including all recipes and possibly their category
- `recipe_url`: An url pointing to the recipes' food.com site
- `servingsPerRecipe`: Extracted from the `nutrition` feature. A number describing the number of servings when cooking the recipe as instructed
- `calories [cal]`: Extracted from the `nutrition` feature. The calories of one serving in cal

**Data quality observations**
- Null values per column: `TO FILL`
- Duplicate `recipe_id` values: `TO FILL`
- Calories equal to 0, negative or outliers (> 3000): `TO FILL` (count and examples)
- Servings equal to 0 or null: `2238`
- Encoding or format problems: `3 inconsistent missing-value placeholders (no information, no informations, no_information); 3 names with leading/trailing whitespace; ingredients stored as serialized text with inconsistent spacing`

**Planned processing** (see tasks #2 and #23): `TO FILL`

---

### 2.2 Landmarks — data.gouv.fr

**Identification**
- Exact dataset name: `Immeubles protégés au titre des Monuments Historiques`
- Producer: `Ministry of Culture`
- Page URL: https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2
- Direct download URL (CSV resource): https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2?resource_id=3a52af4a-f9da-4dcc-8110-b07774dfb3bc
- Date of the resource's last update: `05/11/2026`

**Access**
- Method: `Manual download from the data.gouv.fr dataset pagem no authentification needed`
- Download date and time: `10/11/2026 20:10`
- Update frequency of the source / of our reload: monthly
- Script used: `none`

**Licence**
- Dataset usage restrictions: `Free reuse for commercial and non-commercial purposes, including reproduction, modification, redistribution and publication, subject to attribution requirements`
- Data license: `Open Licence 2.0`
- Copyright notice: `Data provided by the French Ministry of Culture (Ministère de la Culture), under the Open Licence 2.0 (Etalab)`
- Licence text: https://github.com/etalab/licence-ouverte/blob/master/LO.md#licence-ouverte-20open-licence-20
- Terms of use reference: https://www.data.gouv.fr/pages/legal/licences/etalab-2-0

**File**
- Name and path: `data/raw/landmarks.csv`
- Format / encoding / delimiter: `csv / TO FILL / |`
- Size: `95.5 Mo`
- Row count, **whole of France**: `46761`
- Row count **after the Metrople of Lyon filter**: `324`
- Total number of columns: `78`

**Columns kept**
- `Denomination_de_l_edifice`
- `Adresse_forme_editoriale`
- `Commune_forme_index`
- `COG_Insee_lors_de_la_protection`
- `coordonnees_au_format_WGS84`

**Data quality observations**
- Monuments without coordinates: `64`
- Coordinates outside the Lyon bounding box although the commune is in Lyon: `0`
- Duplicate Mérimée references: `0`
- One monument spread over several rows (several protected parts): `1 record with leading/trailing whitespace in Denomination_de_l_edifice`
- Additional observation: 2,257 records across the French dataset have missing coordinates, compared with 64 in the Métropole de Lyon

**Special row**: `landmark_key = -1` / "No landmark", created at load time, not from the source.

---

### 2.3 Lyon restaurants — Kaggle

**Identification**
- Exact dataset name: `Lyon Restaurant Reviews dataset`
- Owner: `Launay Christian`
- Page URL: https://www.kaggle.com/datasets/launay10christian/lyon-restaurant-reviews-dataset
- Direct download URL (CSV resource): 
- Date of the resource's last update: `8 years ago`

**Access**
- Method: `Manual download from the kaggle dataset page, authentification needed`
- Download date and time: `12/11/2026 13:10`
- Update frequency of the source / of our reload: `none`
- Script used: `none`

**Licence**
- Licence stated on Kaggle: `unknown`
- Redistribution of the file in the GitHub repository allowed? `not mentionned`

**File**
- Name and path: `data/raw/restaurant_data_kaggles.csv`
- Format / encoding / delimiter: `csv / utf-8 / ,`
- Size: `493 Ko`
- Row count: `3059`

**Columns kept**
- `restaurant_name`: the restaurant name
- `food_type`: list of food types served in the restaurant
- `lat`: latitude of the restaurant
- `lng`: longitude of the restaurant
- `overallRating`: overall rating on TripAdvisor

**Data quality observations**
- Coordinates: `32 restaurants missing coordinates or outside Lyon (29 missing, 3 outside bbox). Only 195 distinct coordinate pairs for 3,029 valid rows -> low spatial precision`
- District: `Inconsistent values: 46 rows with only Lyon, 12 invalid/non-Rhône postcodes, 1 malformed value, and some restaurants outside the Métropole`
- Duplicates: `22 rows involved (11 surplus rows), including 8 exact duplicate rows. Same-name restaurants at different locations are generally chains`
- Ratings: `253 missing (8.3%). No invalid values; observed ratings range from 1.0 to 5.0`
- Cuisine types: `1084 missing placeholders (35.5%). 478 raw values reduce to 85 normalized values; field mixes cuisines, dietary tags and venue types`
- Other issues: `Three spellings of the missing-value placeholder; 250 no_information values in ranking; 3 restaurant names with leading/trailing whitespace`

---

### 2.4 Physical activities — MET seed

**Identification**
- Reference: Compendium of Physical Activities — https://pacompendium.com/
- Edition used: `TO FILL` *(the sample cites the 2011 edition)*
- File: `data/raw/met_activities.csv` (created by hand)

**Licence / citation**
- Terms of use of the Compendium: `TO FILL`
- Full bibliographic reference to cite: `TO FILL`

**Content**

| Activity | Intensity | MET | Speed (km/h) | Compendium code | Exact description in the Compendium |
|---|---|---|---|---|---|
| walking | 1 | 3.5 | 4.8 | `TO FILL` | `TO FILL` |
| running | 3 | 9.8 | 9.7 | `TO FILL` | `TO FILL` |
| cycling | 2 | 8.0 | 20.0 | `TO FILL` | `TO FILL` |

- Justification for each value (pace, effort level): `TO FILL`
- Origin of the speed (the Compendium gives speeds per activity, to be confirmed): `TO FILL`
- Row count: 3 (small reference dataset, not counted as one of the large datasets)

---

## 3. File organisation

```
data/
├── raw/        source files, never modified
├── staging/    typed intermediate files
├── processed/  cleaned files + rejected-rows files
└── sample/     offline sample (task #19)
```

- Large files versioned or not? `TO FILL` (decision: `.gitignore`, Git LFS, or download by script)
- Procedure to retrieve the non-versioned files: `TO FILL`

## 4. Reproducibility

| Source | Retrieval command | SHA-256 | Date |
|---|---|---|---|
| Recipes | `TO FILL` | `TO FILL` | `TO FILL` |
| Monuments | `TO FILL` | `TO FILL` | `TO FILL` |
| Restaurants | `TO FILL` | `TO FILL` | `TO FILL` |
| MET | (versioned file) | `TO FILL` | `TO FILL` |

## 5. Issues and decisions log

| Date | Source | Issue found | Decision | Owner |
|---|---|---|---|---|
| `TO FILL` | | | | |

## 6. Task #1 checklist

- [ ] The 4 sources are downloaded and stored in `data/raw/`
- [ ] Row count recorded for each file (recipes and monuments > 1,000 rows demonstrated)
- [ ] Licence recorded and link noted for each source
- [ ] Redistribution permission checked for the restaurants CSV
- [ ] Columns documented with mapping to the target columns
- [ ] Checksum (SHA-256) computed for each file
- [ ] Data quality issues spotted and listed
- [ ] `data/` structure created in the repository
- [ ] Links verified (the GitLab "blob" link must be replaced by the download URL)
