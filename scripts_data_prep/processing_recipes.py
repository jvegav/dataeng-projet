import os
from collections import Counter

import pandas as pd

from config import PROCESSED_DIR, STAGING_DIR

# Define paths
input_path = STAGING_DIR / "s_recipes.csv"
output_path = PROCESSED_DIR / "p_recipes.csv"
rejected_path = PROCESSED_DIR / "p_recipes_rejected.csv"
temp_output = output_path.with_name(output_path.name + ".tmp")
temp_rejected = rejected_path.with_name(rejected_path.name + ".tmp")

# Value written in the source_id column for every recipe of this source
SOURCE_ID = "hummus_recipes"

chunk_size = int(os.environ.get("CHUNK_SIZE", 50_000))

output_path.parent.mkdir(parents=True, exist_ok=True)
for tmp in (temp_output, temp_rejected):
    if tmp.exists():
        tmp.unlink()

seen_ids = set()           # recipe_id of the recipes already kept (duplicates across chunks)
rows_read = 0
rows_kept = 0
reject_counts = Counter()

try:
    # Only empty cells are missing values: a title such as "NA" must stay a title
    reader = pd.read_csv(
        input_path,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        chunksize=chunk_size,
    )

    for chunk_number, chunk in enumerate(reader):
        chunk["servings"] = pd.to_numeric(chunk["servings"], errors="coerce").astype("Float64")
        chunk["kcal_per_serving"] = pd.to_numeric(chunk["kcal_per_serving"], errors="coerce").astype("Float64")

        # Rejection rules, in priority order: a row gets the first reason that applies
        chunk["reject_reason"] = pd.Series(pd.NA, index=chunk.index, dtype="string")
        rules = [
            ("missing_recipe_id", chunk["recipe_id"].isna()),
            ("missing_title", chunk["title"].isna()),
            ("missing_calories", chunk["kcal_per_serving"].isna()),
            ("non_positive_calories", chunk["kcal_per_serving"] <= 0),
        ]
        for reason, condition in rules:
            condition = condition.fillna(False).astype(bool)
            chunk.loc[condition & chunk["reject_reason"].isna(), "reject_reason"] = reason

        # Duplicates are searched among valid rows only, so a rejected row
        # never hides a valid recipe with the same recipe_id
        valid = chunk["reject_reason"].isna()
        is_duplicate = (
            chunk["recipe_id"].where(valid).duplicated() | chunk["recipe_id"].isin(seen_ids)
        ) & valid
        chunk.loc[is_duplicate, "reject_reason"] = "duplicate_recipe_id"

        kept = chunk[chunk["reject_reason"].isna()].drop(columns="reject_reason").copy()
        rejected = chunk[chunk["reject_reason"].notna()]
        seen_ids.update(kept["recipe_id"])

        # Added columns: source_id and calories per serving (NULL when servings is missing or <= 0)
        kept.insert(1, "source_id", SOURCE_ID)
        valid_servings = kept["servings"].where(kept["servings"] > 0)
        kept["total_kcal"] = (kept["kcal_per_serving"] * valid_servings)

        first = chunk_number == 0
        kept.to_csv(temp_output, mode="w" if first else "a", header=first,
                    index=False, encoding="utf-8", float_format="%.10g")
        rejected.to_csv(temp_rejected, mode="w" if first else "a", header=first,
                        index=False, encoding="utf-8", float_format="%.10g")

        rows_read += len(chunk)
        rows_kept += len(kept)
        reject_counts.update(rejected["reject_reason"].tolist())

    # Replace the previous files only once everything was written (a rerun gives the same result)
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
print("Rows read / kept / rejected:", rows_read, "/", rows_kept, "/", rows_read - rows_kept)
print("\nRejected rows by reason:")
for reason, count in reject_counts.most_common():
    print(f"  {reason}: {count}")