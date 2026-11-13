#processing landmarks
import os
from collections import Counter

import pandas as pd

from config import PROCESSED_DIR, STAGING_DIR

# Define paths
input_path = STAGING_DIR / "s_landmarks.csv"
output_path = PROCESSED_DIR / "p_landmarks.csv"
rejected_path = PROCESSED_DIR / "p_landmarks_rejected.csv"
temp_output = output_path.with_name(output_path.name + ".tmp")
temp_rejected = rejected_path.with_name(rejected_path.name + ".tmp")

# INSEE codes of the communes kept (study scope: Métropole de Lyon)
lyon_codes = {
    "69003", "69029", "69033", "69034", "69040",
    "69044", "69046", "69271", "69063", "69273",
    "69068", "69069", "69071", "69072", "69275",
    "69081", "69276", "69085", "69087", "69088",
    "69089", "69278", "69091", "69096", "69100",
    "69279", "69116", "69117", "69123", "69127",
    "69282", "69283", "69284", "69142", "69143",
    "69149", "69153", "69163", "69286", "69168",
    "69191", "69194", "69199", "69204", "69205",
    "69207", "69290", "69233", "69202", "69292",
    "69293", "69296", "69244", "69250", "69256",
    "69260", "69266", "69259",
}

# Loose bounding box around the Métropole: it only catches wrong or swapped coordinates
LAT_MIN, LAT_MAX = 45.4, 46.1
LON_MIN, LON_MAX = 4.5, 5.3

# source_id (from staging) is the Merimee reference: "PA" followed by digits, e.g. PA00117123
REFERENCE_PATTERN = r"^PA(\d+)$"

# Coordinates are stored as one text cell "lat, lon"
COORDINATES_PATTERN = r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$"

# Read staging CSV: only empty cells are missing values
df = pd.read_csv(
    input_path,
    encoding="utf-8",
    dtype=str,
    keep_default_na=False,
    na_values=[""],
)
rows_read = len(df)

# Split "lat, lon" into two numeric columns (NULL when missing or not readable)
parts = df["coordinates"].str.extract(COORDINATES_PATTERN)
df["lat"] = pd.to_numeric(parts[0]).astype("Float64")
df["lon"] = pd.to_numeric(parts[1]).astype("Float64")

# Rejection rules, in priority order: a row gets the first reason that applies.
# The scope is checked first, so the quality reasons only describe landmarks in the Métropole.
in_bbox = (
    df["lat"].between(LAT_MIN, LAT_MAX) & df["lon"].between(LON_MIN, LON_MAX)
).fillna(False).astype(bool)
rules = [
    ("missing_insee_code", df["insee_code"].isna()),
    ("outside_lyon_scope", ~df["insee_code"].isin(lyon_codes)),
    ("missing_id", df["source_id"].isna()),
    ("missing_name", df["building_name"].isna()),
    ("invalid_id", df["source_id"].notna() & ~df["source_id"].str.match(REFERENCE_PATTERN, na=True)),
    ("missing_coordinates", df["coordinates"].isna()),
    ("invalid_coordinates", df["coordinates"].notna() & df["lat"].isna()),
    ("outside_bounding_box", df["lat"].notna() & ~in_bbox),
]
df["reject_reason"] = pd.Series(pd.NA, index=df.index, dtype="string")
for reason, condition in rules:
    df.loc[condition & df["reject_reason"].isna(), "reject_reason"] = reason

# Duplicates are searched among valid rows only; the first occurrence is kept
valid = df["reject_reason"].isna()
is_duplicate = df["source_id"].where(valid).duplicated() & valid
df.loc[is_duplicate, "reject_reason"] = "duplicate_id"

kept = df[df["reject_reason"].isna()].drop(columns=["reject_reason", "coordinates"]).copy()
rejected = df[df["reject_reason"].notna()].drop(columns=["lat", "lon"])

kept = kept[["source_id", "commune", "insee_code", "building_name",
             "lat", "lon", "address"]]

# Write to temporary files, then replace the previous ones (a rerun gives the same result)
output_path.parent.mkdir(parents=True, exist_ok=True)
try:
    kept.to_csv(temp_output, index=False, encoding="utf-8", float_format="%.10g")
    rejected.to_csv(temp_rejected, index=False, encoding="utf-8")
    os.replace(temp_output, output_path)
    os.replace(temp_rejected, rejected_path)
except BaseException:
    for tmp in (temp_output, temp_rejected):
        if tmp.exists():
            tmp.unlink()
    raise

# Display results
print("Processed file created:", output_path)
print("Rejected rows file created:", rejected_path)
print("Rows read / kept / rejected:", rows_read, "/", len(kept), "/", len(rejected))
print("\nRejected rows by reason:")
for reason, count in Counter(rejected["reject_reason"]).most_common():
    print(f"  {reason}: {count}")
print("\nMissing values in the processed file:")
print(kept.isna().sum())