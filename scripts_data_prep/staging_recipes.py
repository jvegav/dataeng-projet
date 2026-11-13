#staging recipes
import os
import zipfile

import pandas as pd

from config import RAW_DIR, STAGING_DIR, clean_text, to_number

# Define paths
input_path = RAW_DIR / "r_recipes.zip"
output_path = STAGING_DIR / "s_recipes.csv"
temp_path = output_path.with_name(output_path.name + ".tmp")

# The file has about 500 000 rows (1 GB once unzipped): it is read in chunks
# straight from the ZIP, so nothing is extracted to disk and memory stays small.
chunk_size = int(os.environ.get("CHUNK_SIZE", 50_000))

# Columns kept (source name -> staging name)
columns_to_keep = {
    "recipe_id": "source_id",
    "title": "title",
    "ingredients": "ingredients",
    "recipe_url": "recipe_url",
    "servingsPerRecipe": "servings",
    "calories [cal]": "kcal_per_serving", 
    "tags": "category"
}

string_columns = ["source_id", "title", "ingredients", "recipe_url", "category"]
numeric_columns = ["servings", "kcal_per_serving"]

output_path.parent.mkdir(parents=True, exist_ok=True)
if temp_path.exists():
    temp_path.unlink()

rows_read = 0
null_counts = None
invalid_counts = {col: 0 for col in numeric_columns}
invalid_examples = {col: set() for col in numeric_columns}

try:
    with zipfile.ZipFile(input_path, "r") as zip_ref:
        csv_files = [
            name for name in zip_ref.namelist()
            if name.lower().endswith(".csv") and not name.startswith("__MACOSX")
        ]
        if len(csv_files) != 1:
            raise SystemExit(f"Expected exactly one CSV in {input_path}, found: {csv_files}")

        with zip_ref.open(csv_files[0]) as csv_file:
            reader = pd.read_csv(
                csv_file,
                encoding="utf-8-sig",
                dtype=str,
                sep=",",
                chunksize=chunk_size
            )

            for chunk_number, chunk in enumerate(reader):
                # Remove leading and trailing spaces from column names
                chunk.columns = chunk.columns.str.strip()

                if chunk_number == 0:
                    missing = [c for c in columns_to_keep if c not in chunk.columns]
                    if missing:
                        raise SystemExit(
                            f"Missing column(s) {missing}. Columns found: {chunk.columns.tolist()}"
                        )

                # Keep only relevant columns and standardize column names
                chunk = chunk[list(columns_to_keep)].rename(columns=columns_to_keep)

                # Descriptive fields stay strings; placeholders and empty strings become NULL
                for col in string_columns:
                    chunk[col] = clean_text(chunk[col])

                # Numerical fields: nullable Float64, missing values are NULL (not NaN)
                for col in numeric_columns:
                    chunk[col], invalid = to_number(chunk[col])
                    invalid_counts[col] += len(invalid)
                    invalid_examples[col].update(invalid.unique()[:5].tolist())
                # Append to the staging file (header only for the first chunk)
                chunk.to_csv(
                    temp_path,
                    mode="w" if chunk_number == 0 else "a",
                    header=(chunk_number == 0),
                    index=False,
                    encoding="utf-8",
                    float_format="%.10g"
                )

                rows_read += len(chunk)
                counts = chunk.isna().sum()
                null_counts = counts if null_counts is None else null_counts + counts

    # Replace the previous staging file only once everything was written
    os.replace(temp_path, output_path)

except BaseException:
    if temp_path.exists():
        temp_path.unlink()
    raise

# Display results
print("Staging file created:", output_path)
print("Rows / columns:", (rows_read, len(columns_to_keep)))
print("\nColumn names:")
print(list(chunk.columns))
print("\nMissing values:")
print(null_counts)
for col in numeric_columns:
    if invalid_counts[col] > 0:
        print(f"WARNING: {invalid_counts[col]} value(s) in '{col}' are not numbers "
              f"and were set to NULL, e.g. {sorted(invalid_examples[col])[:5]}")