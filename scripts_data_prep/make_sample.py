"""Build the offline sample (issue #19) from the real raw files.

Reads data/raw/ and writes data/sample/ with the same four file names and formats,
so that the runner can read it with SAMPLE=true:
    r_recipes.zip                   random recipes (one CSV inside, same name as in the real ZIP)
    r_landmarks.csv                 random landmarks among the Métropole de Lyon INSEE codes
    r_restaurant_data_kaggles.csv   random restaurants
    r_met.csv                       copied as is

The rows are picked at random with a fixed seed: the same raw files always give the same sample.
The raw files are only read, never modified.

Usage:
    python scripts_data_prep/make_sample.py
"""

import ast
import csv
import io
import os
import random
import shutil
import zipfile
from pathlib import Path

from config import DATA_DIR

RAW_DIR = DATA_DIR / "raw"          # not config.RAW_DIR: with SAMPLE=true it points to data/sample
SAMPLE_DIR = DATA_DIR / "sample"
SCRIPTS_DIR = Path(__file__).resolve().parent

SEED = 42
N_RECIPES = 300
N_LANDMARKS = 30
N_RESTAURANTS = 20

# Text cells can be very long (ingredients)
csv.field_size_limit(2**31 - 1)


def lyon_codes():
    """The INSEE codes list of processing_landmarks.py, read from the script (not copied here)."""
    tree = ast.parse((SCRIPTS_DIR / "processing_landmarks.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "lyon_codes" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("lyon_codes not found in processing_landmarks.py")


def pick(rows, n, rng):
    """Random pick of n rows (reservoir sampling: one pass, small memory), kept in file order."""
    chosen = []
    for i, row in enumerate(rows):
        if len(chosen) < n:
            chosen.append((i, row))
        else:
            j = rng.randint(0, i)
            if j < n:
                chosen[j] = (i, row)
    return [row for _, row in sorted(chosen, key=lambda item: item[0])]


def write_csv(path, header, rows, delimiter=","):
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(header)
        writer.writerows(rows)
    os.replace(temp, path)


def sample_recipes(rng):
    source = RAW_DIR / "r_recipes.zip"
    with zipfile.ZipFile(source) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")]
        if len(names) != 1:
            raise SystemExit(f"Expected exactly one CSV in {source}, found: {names}")
        with zf.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header = next(reader)
            rows = pick(reader, N_RECIPES, rng)

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)

    output = SAMPLE_DIR / "r_recipes.zip"
    temp = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(names[0], buffer.getvalue().encode("utf-8"))
    os.replace(temp, output)
    return len(rows)


def sample_landmarks(rng):
    codes = lyon_codes()
    with open(RAW_DIR / "r_landmarks.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="|")
        header = next(reader)
        insee = [h.strip() for h in header].index("COG_Insee_lors_de_la_protection")
        in_scope = (row for row in reader if len(row) > insee and row[insee].strip() in codes)
        rows = pick(in_scope, N_LANDMARKS, rng)
    write_csv(SAMPLE_DIR / "r_landmarks.csv", header, rows, delimiter="|")
    return len(rows)


def sample_restaurants(rng):
    with open(RAW_DIR / "r_restaurant_data_kaggles.csv", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = pick(reader, N_RESTAURANTS, rng)
    write_csv(SAMPLE_DIR / "r_restaurant_data_kaggles.csv", header, rows)
    return len(rows)


def main():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    print("recipes:    ", sample_recipes(rng), "rows")
    print("landmarks:  ", sample_landmarks(rng), "rows")
    print("restaurants:", sample_restaurants(rng), "rows")
    shutil.copyfile(RAW_DIR / "r_met.csv", SAMPLE_DIR / "r_met.csv")
    print("met:         copied")
    print("Sample written to", SAMPLE_DIR)


if __name__ == "__main__":
    main()