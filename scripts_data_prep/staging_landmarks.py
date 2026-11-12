
import pandas as pd
import re
import unicodedata
from pathlib import Path

# Define paths
input_path = Path("../data/raw/r_landmarks.csv")
output_path = Path("../data/staging/s_landmarks.csv")

# Read raw CSV
df = pd.read_csv(
    input_path,
    encoding="utf-8-sig",
    dtype=str,
    sep="|"
)

# Keep only relevant columns
columns_to_keep = [
    "Commune_forme_index",
    "COG_Insee_lors_de_la_protection",
    "Denomination_de_l_edifice",
    "coordonnees_au_format_WGS84",
    "Adresse_forme_editoriale"
]

df = df[columns_to_keep].copy()

# Standardize column names
def standardize_column_name(name):
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("utf-8")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")

df.columns = [
    standardize_column_name(col)
    for col in df.columns
]

# Rename columns
df = df.rename(columns={
    "commune_forme_index": "commune",
    "cog_insee_lors_de_la_protection": "insee_code",
    "denomination_de_l_edifice": "building_name",
    "coordonnees_au_format_wgs84": "coordinates",
    "adresse_forme_editoriale": "address"
})

# Standardize data types
# Identifiers and descriptive fields remain strings
string_columns = [
    "commune",
    "insee_code",
    "building_name",
    "coordinates",
    "address"
]

for col in string_columns:
    df[col] = df[col].astype("string").str.strip()

# Replace empty strings with missing values
df = df.replace(r"^\s*$", pd.NA, regex=True)

# Save staging CSV
output_path.parent.mkdir(parents=True, exist_ok=True)

df.to_csv(
    output_path,
    index=False,
    encoding="utf-8"
)

# Display results
print("Staging file created:", output_path)
print("Rows / columns:", df.shape)
print("\nColumn names:")
print(df.columns.tolist())
print("\nData types:")
print(df.dtypes)
print("\nMissing values:")
print(df.isna().sum())
