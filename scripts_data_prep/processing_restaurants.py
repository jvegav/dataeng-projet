#processing restaurants
import hashlib
import os
from collections import Counter

import pandas as pd

from config import PROCESSED_DIR, STAGING_DIR

# Define paths
input_path = STAGING_DIR / "s_restaurants.csv"
output_path = PROCESSED_DIR / "p_restaurants.csv"
rejected_path = PROCESSED_DIR / "p_restaurants_rejected.csv"
temp_output = output_path.with_name(output_path.name + ".tmp")
temp_rejected = rejected_path.with_name(rejected_path.name + ".tmp")

# Loose bounding box around the Lyon area (same as the landmarks)
LAT_MIN, LAT_MAX = 45.4, 46.1
LON_MIN, LON_MAX = 4.5, 5.3

# In food_type, several cuisines are separated by two spaces: replaced by this separator
CUISINE_SEPARATOR = ", "

# Read staging CSV: only empty cells are missing values
df = pd.read_csv(
    input_path,
    encoding="utf-8",
    dtype=str,
    keep_default_na=False,
    na_values=[""],
)
rows_read = len(df)

for col in ["lat", "lng", "overall_rating"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")

# Rejection rules, in priority order: a row gets the first reason that applies
in_bbox = (
    df["lat"].between(LAT_MIN, LAT_MAX) & df["lng"].between(LON_MIN, LON_MAX)
).fillna(False).astype(bool)
has_name = df["restaurant_name"].notna()
has_coordinates = df["lat"].notna() & df["lng"].notna()
rules = [
    ("missing_name", ~has_name),
    ("missing_coordinates", ~has_coordinates),
    ("outside_bounding_box", has_coordinates & ~in_bbox),
    ("rating_out_of_range", (df["overall_rating"] < 0) | (df["overall_rating"] > 5)),
]
df["reject_reason"] = pd.Series(pd.NA, index=df.index, dtype="string")
for reason, condition in rules:
    condition = condition.fillna(False).astype(bool)
    df.loc[condition & df["reject_reason"].isna(), "reject_reason"] = reason

# Duplicates (same name and coordinates) are searched among valid rows only;
# the first occurrence is kept
valid = df["reject_reason"].isna()
is_duplicate = df[valid].duplicated(subset=["restaurant_name", "lat", "lng"]).reindex(df.index, fill_value=False)
df.loc[is_duplicate, "reject_reason"] = "duplicate_restaurant"


def make_source_id(name, lat, lng):
    """The source has no restaurant ID: first 15 hex digits of md5(name|lat|lng), read as a number
    (fits a BIGINT). lat and lng are formatted as in the CSV file (%.10g)."""
    key = f"{name}|{lat:.10g}|{lng:.10g}"
    return int(hashlib.md5(key.encode("utf-8")).hexdigest()[:15], 16)


# source_id is computed for the valid rows only. Two different restaurants can still get the same
# source_id (coordinates equal once written with 10 digits, or an md5 collision): the first is kept
valid = df["reject_reason"].isna()
df["source_id"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
df.loc[valid, "source_id"] = pd.Series(
    [make_source_id(n, la, lo) for n, la, lo in zip(df.loc[valid, "restaurant_name"],
                                                    df.loc[valid, "lat"], df.loc[valid, "lng"])],
    index=df.index[valid], dtype="Int64",
)
is_duplicate_id = df["source_id"].duplicated() & valid
df.loc[is_duplicate_id, "reject_reason"] = "duplicate_source_id"

kept = df[df["reject_reason"].isna()].drop(columns="reject_reason").copy()
kept = kept[["source_id"] + [c for c in kept.columns if c != "source_id"]]
rejected = df[df["reject_reason"].notna()].drop(columns="source_id")

# Several cuisines are separated by two spaces: use a clear separator
kept["food_type"] = kept["food_type"].str.replace(r"\s{2,}", CUISINE_SEPARATOR, regex=True)


# Write to temporary files, then replace the previous ones (a rerun gives the same result)
output_path.parent.mkdir(parents=True, exist_ok=True)
try:
    kept.to_csv(temp_output, index=False, encoding="utf-8", float_format="%.10g")
    rejected.to_csv(temp_rejected, index=False, encoding="utf-8", float_format="%.10g")
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
print("source_id unique:", kept["source_id"].is_unique)
print("\nRejected rows by reason:")
for reason, count in Counter(rejected["reject_reason"]).most_common():
    print(f"  {reason}: {count}")
print("\nMissing values in the processed file:")
print(kept.isna().sum())