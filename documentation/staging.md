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
| `calories_kcal` | 0 |
| `category` | 276686 |

**Staging operations**

- Selected the 7 columns required for the project
- Read the file in chunks directly from the ZIP archive (nothing is extracted to disk, memory use stays low)
- Removed leading and trailing whitespace from column names
- Renamed columns for readability
- Kept descriptive columns as strings (`ingredients` stays as raw JSON text)
- Converted `servings` and `calories_kcal` to nullable numeric types (`Float64`)
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
| Delimiter | `|` |
| Data types | `String` |

**Selected columns and renaming**

| Original column | Staged column |
|---|---|
| `Reference` | `id` |
| `Commune_forme_index` | `commune` |
| `COG_Insee_lors_de_la_protection` | `insee_code` |
| `Denomination_de_l_edifice` | `building_name` |
| `coordonnees_au_format_WGS84` | `coordinates` |
| `Adresse_forme_editoriale` | `address` |

**Missing values**

| Column | Missing values |
|---|---:|
| `commune` | 1 |
| `insee_code` | 7 |
| `building_name` | 160 |
| `coordinates` | 2257 |
| `address` | 28433 |

**Staging operation**

- Selected the 6 columns required for the project (identifiers, name, address, commune, INSEE code, coordinates)
- Standardized column names to lowercase `snake_case`
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
| Original rows | `3059` |
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
| ` district` | 0 |

**Staging operations**

- Removed leading and trailing spaces from column name
- Selected the 5 columns required for the project
- Standardized column names to lowercase `snake_case`
- Renamed columns for readability
- Standardized all retained columns to string and float types
- Removed leading and trailing whitespace from string values
- Converted empty strings to missing values
- Saved the output using UTF-8 encoding

### 5.4 MET
No staging needed since the source file has been done manually and is already standardized