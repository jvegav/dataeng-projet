#processing recipes
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

# Accepted range for the calories of one serving, in kcal (same as the CHECK of dim_recipe)
KCAL_MIN, KCAL_MAX = 1, 3000

chunk_size = int(os.environ.get("CHUNK_SIZE", 50_000))

output_path.parent.mkdir(parents=True, exist_ok=True)
for tmp in (temp_output, temp_rejected):
    if tmp.exists():
        tmp.unlink()

seen_ids = set()         
rows_read = 0
rows_kept = 0
servings_set_null = 0      # servings missing, <= 0 or rounded to 0: kept as NULL
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
        # source_id must be a whole number (it becomes dim_recipe.source_id, an INT)
        id_number = pd.to_numeric(chunk["source_id"], errors="coerce").astype("Float64")
        invalid_id = chunk["source_id"].notna() & (id_number.isna() | (id_number % 1 != 0))
        id_number = id_number.where(~invalid_id).astype("Int64")

        chunk["servings"] = pd.to_numeric(chunk["servings"], errors="coerce").astype("Float64")
        chunk["kcal_per_serving"] = (
            pd.to_numeric(chunk["kcal_per_serving"], errors="coerce").astype("Float64")
        )

        # Rejection rules, in priority order: a row gets the first reason that applies
        chunk["reject_reason"] = pd.Series(pd.NA, index=chunk.index, dtype="string")
        rules = [
            ("missing_source_id", chunk["source_id"].isna()),
            ("invalid_source_id", invalid_id),
            ("missing_title", chunk["title"].isna()),
            ("missing_calories", chunk["kcal_per_serving"].isna()),
            ("non_positive_calories", chunk["kcal_per_serving"] <= 0),
            ("calories_out_of_range",
             (chunk["kcal_per_serving"] < KCAL_MIN) | (chunk["kcal_per_serving"] > KCAL_MAX)),
        ]
        for reason, condition in rules:
            condition = condition.fillna(False).astype(bool)
            chunk.loc[condition & chunk["reject_reason"].isna(), "reject_reason"] = reason

        # Duplicates are searched among valid rows only, so a rejected row
        # never hides a valid recipe with the same source_id
        valid = chunk["reject_reason"].isna()
        is_duplicate = (
            id_number.where(valid).duplicated() | id_number.isin(seen_ids)
        ) & valid
        chunk.loc[is_duplicate, "reject_reason"] = "duplicate_source_id"

        kept_mask = chunk["reject_reason"].isna()
        kept = chunk[kept_mask].drop(columns="reject_reason").copy()
        rejected = chunk[~kept_mask]
        kept["source_id"] = id_number[kept_mask]
        seen_ids.update(kept["source_id"].tolist())

        # Whole numbers, as in the INT columns of dim_recipe
        kept["kcal_per_serving"] = kept["kcal_per_serving"].round().astype("Int64")
        # servings: rounded to a whole number; NULL when missing, <= 0 or rounded to 0
        servings = kept["servings"].round()
        servings = servings.where(servings > 0)
        servings_set_null += int(servings.isna().sum())
        kept["servings"] = servings.astype("Int64")
        # Calories of the whole recipe (NULL when servings is NULL)
        kept["total_kcal"] = kept["kcal_per_serving"] * kept["servings"]

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
print("Kept rows with servings set to NULL:", servings_set_null)
print("\nRejected rows by reason:")
for reason, count in reject_counts.most_common():
    print(f"  {reason}: {count}")