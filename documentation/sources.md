# Data Sources — DeservEat

Last updated: `13/11/2026` by: @kaguir

---

## 1. Overview

| Source | Role in the project | Dimension fed | File in repository | Rows | Size |
|---|---|---|---|---|---|
| Recipe Data Set (GitLab) | Calories, servings, ingredients | `dim_recipe` | `data/raw/r_recipes.zip` | 507335 | 302 Mo |
| Historical monuments (data.gouv.fr) | Optional route destinations | `dim_landmark` | `data/raw/r_landmarks.csv` | 46761 | 95.5 Mo |
| Lyon restaurants (Kaggle) | Route starting points | `dim_restaurant` | `data/raw/r_restaurant_data_kaggles.csv` | 3058 | 493 Ko |
| MET (Compendium) | MET values and speeds | `dim_activity` | `data/raw/r_met.csv` | 9 | 460 o |

---

## 2. Source sheets

### 2.1 Recipes — Recipe Data Set

**Identification**
- Exact dataset name: `HUMMUS data set`
- Provider / authors: `felix134`
- Page URL: https://gitlab.com/felix134/connected-recipe-data-set
- Direct download URL: https://gitlab.com/felix134/connected-recipe-data-set/-/raw/eb672598cc4891da0eb436daefcd25b412dad641/data/hummus_data/preprocessed/pp_recipes.zip
- Version / commit / publication date: `init commit, July 20, 2023`

**Access**
- Method: `Manual download from the GitLab repo (can be reproduced with the command given in section 3)`
- Download date and time: `10/11/2026 17:28`
- Update frequency: `no update since 2023`
- Command or script used: `none (see section 3 for the curl command)`

**Licence and terms of use**
- Dataset usage restrictions: `The data was collected from Food.com and may only be used for educational or scientific purposes, as stated in the dataset repository's README.`
- Code license: `GNU General Public License v3.0 (GPLv3)`
- Copyright notice (Food.com): `© 2026 Warner Bros. Discovery, Inc. or its subsidiaries and affiliates. All rights reserved.`
- Licence text: https://www.gnu.org/licenses/gpl-3.0.en.html
- Terms of use reference: `Dataset README`

**File**
- Name and path: `data/raw/r_recipes.zip`
- Format / encoding / delimiter: `csv in zip / utf-8 / ,`
- Compressed / uncompressed size: `302 Mo / 1.05 Go`
- ZIP contents : `pp_recipes.csv`
- Row count (after decompression, excluding header): `507335`

**Columns kept**
- `recipe_id`: A unique ID identifying each recipe
- `title`: The title of the recipe
- `ingredients`: A json-object including all ingredients
- `recipe_url`: A URL pointing to the recipes' food.com site
- `servingsPerRecipe`: Extracted from the `nutrition` feature. A number describing the number of servings when cooking the recipe as instructed
- `calories [cal]`: Extracted from the `nutrition` feature. The calories of one serving in cal
- `tags`: A list of tags for the current recipes collected from food.com

**Data quality observations**
- Null values per column: `TO FILL`
- Duplicate `recipe_id` values: `TO FILL`
- Calories equal to 0, negative or outliers (> 3000): `TO FILL` (count and examples)
- Servings equal to 0 or null: `2238`
- Encoding or format problems: `3 inconsistent missing-value placeholders (no information, no informations, no_information); 3 names with leading/trailing whitespace; ingredients stored as serialized text with inconsistent spacing`


---

### 2.2 Landmarks — data.gouv.fr

**Identification**
- Exact dataset name: `Immeubles protégés au titre des Monuments Historiques`
- Producer: `Ministry of Culture`
- Page URL: https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2
- Direct download URL (CSV resource): https://www.data.gouv.fr/datasets/immeubles-proteges-au-titre-des-monuments-historiques-2?resource_id=3a52af4a-f9da-4dcc-8110-b07774dfb3bc
- Date of the resource's last update: `05/11/2026`

**Access**
- Method: `Manual download from the data.gouv.fr dataset page, no authentication needed (the Airflow ingestion DAG downloads it automatically, see section 3)`
- Download date and time: `10/11/2026 20:10`
- Update frequency of the source / of our reload: monthly
- Script used: `none for the initial download`

**Licence**
- Dataset usage restrictions: `Free reuse for commercial and non-commercial purposes, including reproduction, modification, redistribution and publication, subject to attribution requirements`
- Data license: `Open Licence 2.0`
- Copyright notice: `Data provided by the French Ministry of Culture (Ministère de la Culture), under the Open Licence 2.0 (Etalab)`
- Licence text: https://github.com/etalab/licence-ouverte/blob/master/LO.md#licence-ouverte-20open-licence-20
- Terms of use reference: https://www.data.gouv.fr/pages/legal/licences/etalab-2-0

**File**
- Name and path: `data/raw/r_landmarks.csv`
- Format / encoding / delimiter: `csv / utf-8 / |`
- Size: `95.5 Mo`
- Row count, **whole of France**: `46761`
- Row count **after the Métropole of Lyon filter**: `324`
- Total number of columns: `78`

**Columns kept**
- `Reference`
- `Denomination_de_l_edifice`
- `Adresse_forme_editoriale`
- `Commune_forme_index`
- `COG_Insee_lors_de_la_protection`
- `coordonnees_au_format_WGS84`

**Data quality observations**
- Monuments without coordinates: `64`
- Coordinates outside the Lyon bounding box although the commune is in Lyon: `0`
- Duplicate Mérimée references: `0`
- Leading/trailing whitespace in `Denomination_de_l_edifice`: `1 record`
- Additional observation: 2257 records across the French dataset have missing coordinates, compared with 64 in the Métropole de Lyon

---

### 2.3 Lyon restaurants — Kaggle

**Identification**
- Exact dataset name: `Lyon Restaurant Reviews dataset`
- Owner: `Launay Christian`
- Page URL: https://www.kaggle.com/datasets/launay10christian/lyon-restaurant-reviews-dataset
- Direct download URL (CSV resource): `none (manual download, Kaggle login required)`
- Date of the resource's last update: `8 years ago`

**Access**
- Method: `Manual download from the Kaggle dataset page, authentication needed`
- Download date and time: `12/11/2026 13:10`
- Update frequency of the source / of our reload: `none`
- Script used: `none`

**Licence**
- Licence stated on Kaggle: `unknown`
- Redistribution of the file in the GitHub repository allowed? `not mentioned`

**File**
- Name and path: `data/raw/r_restaurant_data_kaggles.csv`
- Format / encoding / delimiter: `csv / utf-8 / ,`
- Size: `493 Ko`
- Row count: `3058`

**Columns kept**
- `restaurant_name`: the restaurant name
- `food_type`: list of food types served in the restaurant
- `lat`: latitude of the restaurant
- `lng`: longitude of the restaurant
- `overallRating`: overall rating on TripAdvisor
- `district`: district of the restaurant (example: 69002 Lyon)

**Data quality observations**
- Coordinates: `31 restaurants missing coordinates or outside Lyon (29 missing, 2 outside bbox). Only 195 distinct coordinate pairs for 3,029 valid rows -> low spatial precision`
- District: `Inconsistent values: 46 rows with only Lyon, 12 invalid/non-Rhône postcodes, 1 malformed value, and some restaurants outside the Métropole`
- Duplicates: `22 rows involved (11 surplus rows), including 8 exact duplicate rows. Same-name restaurants at different locations are generally chains`
- Ratings: `253 missing (8.3%). No invalid values; observed ratings range from 1.0 to 5.0`
- Cuisine types: `1084 missing placeholders, (35.4%). 478 raw values reduce to 85 normalized values; field mixes cuisines, dietary tags and venue types`
- Other issues: `Three spellings of the missing-value placeholder; 250 no_information values in ranking; 3 restaurant names with leading/trailing whitespace`

---

### 2.4 Physical activities — MET seed

**Identification**
- Reference: Compendium of Physical Activities, https://pacompendium.com/adult-compendium/
- Edition used: `2024 Adult Compendium` (third update of the adult compendium)
- File: `data/raw/r_met.csv` (hand-built seed file; first draft produced with AI, then every row checked manually against the Compendium)

**Licence / citation**
- Dataset usage restrictions: `As stated on the Compendium website: researchers may download the Compendium for use in their research; the Adult, Older Adult and Wheelchair Compendia are free to use for commercial purposes; teachers may use the Compendium or portions of it for educational purposes with their students.`
- Data licence: `No standard open licence; free-use terms published by the Compendium authors (see above).`
- Copyright notice: `Compendium of Physical Activities, © its authors. Values reproduced here for educational use, with attribution.`
- Required citation: `Herrmann SD, Willis EA, Ainsworth BE, et al. 2024 Adult Compendium of Physical Activities: A third update of the energy costs of human activities. Journal of Sport and Health Science, 2024, 13(1) (PMID 38242596).`
- Licence text: no licence text; terms are on https://pacompendium.com/ (the paper itself is open access: https://pmc.ncbi.nlm.nih.gov/articles/PMC10818145/)
- Terms of use reference: https://pacompendium.com/

**Columns**
- `activity_key`: surrogate key of the activity + level
- `activity_name`: walking, running or cycling
- `speed_kmh`: speed in km/h (Compendium values in mph converted to km/h, ranges replaced by their midpoint)
- `met_value`: MET, in kcal per kg of body weight per hour
- `intensity`: light / moderate / vigorous (see below)
- `compendium_code` (to add): the Compendium activity code each MET value comes from, so every row is traceable

**Content**
The seed contains the three activities (walking, running and cycling), each with 3 levels (slow/leisure, moderate and fast), i.e. 9 rows. Speeds and MET values come from the Compendium; where the Compendium gives a speed range, the midpoint is used. The intensity labels are our own practical grouping based on the MET value:
- Light: 3 METs and below
- Moderate: over 3 and up to 6 METs
- Vigorous: over 6 METs

This is a small reference dataset, created by hand, not an extract of the whole Compendium.

---


## 3. File organisation

```
project/
├── data/
│   ├── raw/
│   ├── staging/
│   ├── sample/
│   ├── sample_run/        (generated by a SAMPLE=true run)
│   └── processed/
├── diagrams_schema/
│   ├── architecture_diagram.jpeg
│   └── star_schema
├── scripts_data_prep/
│   ├── csv_parser.py
│   ├── check_encoding.py
│   ├── profile_landmarks.py
│   ├── profile_recipes.py
│   ├── config.py
│   ├── staging_x.py (x=landmarks, restaurants, recipes)
│   └── processing_x.py (x=landmarks, restaurants, recipes)
├── files/
│   ├── 01_ddl.sql
│   └── 02_sample_data.sql
├── documentation/
│   └── sources.md
├── .gitignore
├── github_issues.md
└── README.md
```

- Large files versioned or not? `Mostly not (.gitignore, no Git LFS). Only the MET files, p_landmarks.csv (~324 rows, open licence) and a small data/sample/ folder are committed. All other raw, staged and processed files are ignored: they are too large (recipes zip 302 MB, landmarks 95.5 MB), under restricted or unknown licences (recipes, restaurants), or regenerated by the pipeline.`
- Procedure to retrieve the non-versioned files:
  - `r_recipes.zip`: download by script from the GitLab repository, saved as `data/raw/r_recipes.zip`:
    ```
    curl -L -o data/raw/r_recipes.zip "https://gitlab.com/felix134/connected-recipe-data-set/-/raw/eb672598cc4891da0eb436daefcd25b412dad641/data/hummus_data/preprocessed/pp_recipes.zip"
    ```
  - `r_landmarks.csv`: downloaded automatically by the Airflow ingestion DAG from `https://www.data.gouv.fr/fr/datasets/r/3a52af4a-f9da-4dcc-8110-b07774dfb3bc` into `data/raw/r_landmarks.csv`.
  - `r_restaurant_data_kaggles.csv`: manual download (Kaggle login required) from https://www.kaggle.com/datasets/launay10christian/lyon-restaurant-reviews-dataset, then renamed and placed in `data/raw/`.
  - Staged and processed files: generated by running the pipeline once the raw files are in place.

---


## 4. Reproducibility

| Source | Retrieval command | SHA-256 | Date |
|---|---|---|---|
| Recipes | `TO FILL` | `TO FILL` | `TO FILL` |
| Monuments | `TO FILL` | `TO FILL` | `TO FILL` |
| Restaurants | `TO FILL` | `TO FILL` | `TO FILL` |
| MET | (versioned file) | `TO FILL` | `TO FILL` |

---


## 5. Data staging

This section describes the technical preparation applied to each source dataset before the processing phase.

The staging phase aims to:
- Select the columns required for the project
- Standardize column names
- Standardize data types and encoding
- Preserve the original records
- Identify and document missing values

### 5.1. Recipes

- Source file: `r_recipes.zip`  
- Output file: `s_recipes.csv`

**General information**

| Property | Result |
|---|---|
| Original rows | `507335` |
| Staged rows | `507335` |
| Selected columns | `7` |
| Encoding | `UTF-8` |
| Delimiter | `,` |
| Data types | `string, float` |

**Selected columns and renaming**

| Original column | Staged column |
|---|---|
| `recipe_id` | `recipe_id` |
| `title` | `title` |
| `ingredients` | `ingredients` |
| `recipe_url` | `recipe_url` |
| `servingsPerRecipe` | `servings` |
| `calories [cal]` | `kcal_per_serving` |
| `tags` | `category` |

**Missing values**

| Column | Missing values |
|---|---:|
| `recipe_id` | 0 |
| `title` | 0 |
| `ingredients` | 2 |
| `recipe_url` | 0 |
| `servings` | 0 |
| `kcal_per_serving` | 0 |
| `category` | 276686 |

**Staging operations**

- Selected the 7 columns required for the project
- Read the file in chunks directly from the ZIP archive (nothing is extracted to disk, memory use stays low)
- Removed leading and trailing whitespace from column names
- Renamed columns for readability
- Kept descriptive columns as strings (`ingredients` stays as raw JSON text)
- Converted `servings` and `kcal_per_serving` to nullable numeric types (`Float64`)
- Removed leading and trailing whitespace from string values
- Converted empty strings and `no information` placeholders to missing values (NULL)
- Reported values that were not empty but could not be read as numbers (set to NULL, with a warning)
- Kept all rows: no filtering at this stage (filtering and deduplication are done in processing)
- Wrote to a temporary file and replaced the previous staging file only once everything succeeded
- Saved the output using UTF-8 encoding

### 5.2 Landmarks

- Source file: `r_landmarks.csv`  
- Output file: `s_landmarks.csv`

**General information**

| Property | Result |
|---|---|
| Original rows | `46761` |
| Staged rows | `46761` |
| Selected columns | `6` |
| Encoding | `UTF-8` |
| Delimiter | `\|` |
| Data types | `String` |

**Selected columns and renaming**

| Original column | Staged column |
|---|---|
| `Reference` | `landmark_key` |
| `Commune_forme_index` | `commune` |
| `COG_Insee_lors_de_la_protection` | `insee_code` |
| `Denomination_de_l_edifice` | `building_name` |
| `coordonnees_au_format_WGS84` | `coordinates` |
| `Adresse_forme_editoriale` | `address` |

**Missing values**

| Column | Missing values |
|---|---:|
| `landmark_key` | 0 |
| `commune` | 1 |
| `insee_code` | 7 |
| `building_name` | 160 |
| `coordinates` | 2257 |
| `address` | 28433 |

**Staging operations**

- Selected the 6 columns required for the project (identifier, name, address, commune, INSEE code, coordinates)
- Renamed columns for readability
- Standardized all retained columns to string types
- Removed leading and trailing whitespace from string values
- Converted empty strings and `no information` placeholders to missing values (NULL)
- Kept all rows: no filtering at this stage (the Lyon filter is applied in processing)
- Kept coordinates as a single text column (`"lat, lon"`); splitting into latitude and longitude is done in processing
- Saved the output using UTF-8 encoding

### 5.3 Restaurants

- Source file: `r_restaurant_data_kaggles.csv`  
- Output file: `s_restaurants.csv`

**General information**

| Property | Result |
|---|---|
| Original rows | `3058` |
| Staged rows | `3058` |
| Selected columns | `6` |
| Encoding | `UTF-8` |
| Delimiter | `,` |
| Data types | `string, float` |

**Selected columns and renaming**

| Original column | Staged column |
|---|---|
| `restaurant_name ` | `restaurant_name` |
| ` food_type ` | `food_type` |
| ` lat ` | `lat` |
| ` lng ` | `lng` |
| ` overallRating ` | `overall_rating` |
| ` district` | `district` |

**Missing values**

| Column | Missing values |
|---|---:|
| `restaurant_name` | 0 |
| `food_type` | 1084 |
| `lat` | 29 |
| `lng` | 29 |
| `overall_rating` | 253 |
| `district` | 0 |

**Staging operations**

- Removed leading and trailing spaces from column names
- Selected the 6 columns required for the project
- Renamed `overallRating` to `overall_rating` (the other columns already use `snake_case`)
- Standardized all retained columns to string and float types
- Removed leading and trailing whitespace from string values
- Converted empty strings and `no information` placeholders to missing values (NULL)
- Saved the output using UTF-8 encoding

### 5.4 MET
No staging needed since the source file has been done manually and is already standardized

---


## 6. Data processing

For each dataset `x` (except MET, see 6.4), processing produces 2 files:
- `p_x.csv`: the kept rows, with the added columns
- `p_x_rejected.csv`: the rejected rows with a reject_reason column

### 6.1 Recipes

**Processing rules**
The processing script rejects the recipes with the following rules:
- missing `recipe_id`
- missing `title`
- `kcal_per_serving` is NULL or ≤ 0
- duplicates on `recipe_id` (the first valid occurrence is kept)

A row gets the first reason that applies, in the order above.

The script also adds 2 columns:
- `total_kcal` = `kcal_per_serving` × `servings` (NULL if `servings` is missing or ≤ 0)
- `source_id` = `hummus_recipes`

A missing `servings` value does not reject the recipe: only `total_kcal` is NULL.

**Processing Results**
| Rows read |Rows kept | Rows rejected | 
|---|---|---|
| 507335 | 504385 | 2950 |

Rejected rows by reason:
- non_positive_calories: 2950

### 6.2 Landmarks

**Processing rules**
The processing script rejects the landmarks with the following rules:
- missing `insee_code`
- `insee_code` not in the INSEE codes of the Métropole de Lyon
- missing `landmark_key`
- missing or invalid `coordinates`
- `coordinates` outside the bounding box of the Lyon area
- duplicates on `landmark_key`

The script also adds 3 columns:
- `lat` and `lon` = `coordinates` split into two numeric values
- `source_id` = `monuments_historiques`

**Processing Results**
| Rows read |Rows kept | Rows rejected | 
|---|---|---|
| 46761 | 260 | 46501 |

Rejected rows by reason:
- outside_lyon_scope: 46430
- missing_coordinates: 64
- missing_insee_code: 7

### 6.3 Restaurants

**Processing rules**
The processing script rejects the restaurants with the following rules:
- missing `lat` or `lng`
- `lat`/`lng` outside the bounding box of the Lyon area
- `overall_rating` below 0 or above 5
- duplicates on `restaurant_name`, `lat` and `lng` (the first occurrence is kept)

The script also adds 1 column:
- `source_id` = `kaggle_restaurants`

Cuisines: in `food_type`, several cuisines are separated by two spaces; the script replaces this separator with `, `.
Missing values: a missing `overall_rating` or `food_type` does not reject the restaurant, the value stays NULL.

**Processing Results**
| Rows read |Rows kept | Rows rejected | 
|---|---|---|
| 3058 | 3016 | 42 |

Rejected rows by reason:
- missing_coordinates: 29
- duplicate_restaurant: 11
- outside_bounding_box: 2

### 6.4 MET seed
The MET reference table is hand-built from the 2024 Adult Compendium of Physical Activities and is already in its final format: it has no missing values, no duplicates and no rows to filter, so it needs neither staging nor processing. It is copied as is to `data/processed/p_met.csv`, so that every table loaded into the database comes from the same folder.

---


## 7. Issues and decisions log

| Date | Source | Issue found | Decision | Owner |
|---|---|---|---|---|
| `TO FILL` | | | | |