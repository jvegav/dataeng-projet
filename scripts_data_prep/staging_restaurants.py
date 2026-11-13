import pandas as pd

from config import RAW_DIR, STAGING_DIR, clean_text, to_number

# Define paths
input_path = RAW_DIR / "r_restaurant_data_kaggles.csv"
output_path = STAGING_DIR / "s_restaurants.csv"

# Columns kept (source name -> staging name)
columns_to_keep = {
    "restaurant_name": "restaurant_name",
    "food_type": "food_type",
    "lat": "lat",
    "lng": "lng",
    "overallRating": "overall_rating",
    "district": "district",
}
string_columns = ["restaurant_name", "food_type", "district"]
numeric_columns = ["lat", "lng", "overall_rating"]

# Read raw CSV (everything as text: typing is done below)
df = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str)

# The raw header has stray spaces, so strip before selecting columns
df.columns = df.columns.str.strip()
df = df[list(columns_to_keep)].rename(columns=columns_to_keep)

# Descriptive fields stay strings; empty strings and placeholders become NULL
for col in string_columns:
    df[col] = clean_text(df[col])

# Numerical fields: nullable Float64, missing values are NULL (not NaN)
for col in numeric_columns:
    df[col], invalid = to_number(df[col])
    if len(invalid) > 0:
        print(f"WARNING: {len(invalid)} value(s) in '{col}' are not numbers "
              f"and were set to NULL, e.g. {invalid.unique()[:5].tolist()}")

# Save staging CSV (NULL values are written as empty cells)
output_path.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(output_path, index=False, encoding="utf-8")

# Display results
print("Staging file created:", output_path)
print("Rows / columns:", df.shape)
print("\nData types:")
print(df.dtypes)
print("\nMissing values:")
print(df.isna().sum())