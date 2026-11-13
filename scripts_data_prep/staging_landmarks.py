import pandas as pd

from config import RAW_DIR, STAGING_DIR, clean_text

# Define paths
input_path = RAW_DIR / "r_landmarks.csv"
output_path = STAGING_DIR / "s_landmarks.csv"

# Columns kept (source name -> staging name)
columns_to_keep = {
    "Reference": "landmark_key",
    "Commune_forme_index": "commune",
    "COG_Insee_lors_de_la_protection": "insee_code",
    "Denomination_de_l_edifice": "building_name",
    "coordonnees_au_format_WGS84": "coordinates",
    "Adresse_forme_editoriale": "address",
}

# Read raw CSV (everything as text)
df = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, sep="|")

# Strip the header in case of stray spaces, then select and rename
df.columns = df.columns.str.strip()
df = df[list(columns_to_keep)].rename(columns=columns_to_keep)

# All columns are descriptive (the key included): keep them as strings,
# empty strings and placeholders become NULL
for col in df.columns:
    df[col] = clean_text(df[col])

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