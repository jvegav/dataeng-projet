"""Staging tests: no filtering, columns renamed, text cleaned, numeric columns typed.

    pytest tests/test_staging.py               on the sample
    pytest tests/test_staging.py --data real   on data/raw/ and data/staging/ (the recipes count reads
                                               the whole ZIP, so it takes a little while)
"""

import zipfile

import pandas as pd
import pytest

from config import NULL_PLACEHOLDERS
from conftest import read_csv

CHUNK_SIZE = 100_000

SOURCES = {
    "recipes": {
        "staged": "s_recipes.csv",
        "columns": ["source_id", "title", "ingredients", "recipe_url", "servings", "kcal_per_serving", "category"],
        "text": ["source_id", "title", "ingredients", "recipe_url", "category"],
        "numeric": ["servings", "kcal_per_serving"],
    },
    "landmarks": {
        "staged": "s_landmarks.csv",
        "columns": ["source_id", "commune", "insee_code", "building_name", "coordinates", "address"],
        "text": ["source_id", "commune", "insee_code", "building_name", "coordinates", "address"],
        "numeric": [],
    },
    "restaurants": {
        "staged": "s_restaurants.csv",
        "columns": ["restaurant_name", "food_type", "lat", "lng", "overall_rating", "district"],
        "text": ["restaurant_name", "food_type", "district"],
        "numeric": ["lat", "lng", "overall_rating"],
    },
}


def raw_row_count(raw_dir, source):
    """Rows of the raw file, read with the same options as the staging script."""
    if source == "recipes":
        with zipfile.ZipFile(raw_dir / "r_recipes.zip") as zf:
            name = [n for n in zf.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")][0]
            with zf.open(name) as f:
                return sum(len(chunk) for chunk in pd.read_csv(f, encoding="utf-8-sig", dtype=str, sep=",",
                                                               usecols=[0], chunksize=CHUNK_SIZE))
    if source == "landmarks":
        return len(pd.read_csv(raw_dir / "r_landmarks.csv", encoding="utf-8-sig", dtype=str, sep="|", usecols=[0]))
    return len(pd.read_csv(raw_dir / "r_restaurant_data_kaggles.csv", encoding="utf-8-sig", dtype=str, usecols=[0]))


def staged_chunks(dirs, source, usecols=None):
    return read_csv(dirs["staging"] / SOURCES[source]["staged"], usecols=usecols, chunksize=CHUNK_SIZE)


@pytest.mark.parametrize("source", SOURCES)
def test_columns_renamed(dirs, source):
    columns = read_csv(dirs["staging"] / SOURCES[source]["staged"], nrows=0).columns.tolist()
    assert columns == SOURCES[source]["columns"]


@pytest.mark.parametrize("source", SOURCES)
def test_no_row_filtered(dirs, source):
    staged = sum(len(chunk) for chunk in staged_chunks(dirs, source, usecols=[0]))
    assert staged == raw_row_count(dirs["raw"], source)


@pytest.mark.parametrize("source", SOURCES)
def test_text_cleaned(dirs, source):
    """No empty string, no 'no information' placeholder, no leading or trailing spaces: those are NULL."""
    columns = SOURCES[source]["text"]
    for chunk in staged_chunks(dirs, source, usecols=columns):
        for col in columns:
            values = chunk[col].dropna()
            placeholders = values[values.str.strip().str.casefold().isin(NULL_PLACEHOLDERS)]
            assert placeholders.empty, f"{col}: placeholders left, e.g. {placeholders.head().tolist()}"
            not_stripped = values[values != values.str.strip()]
            assert not_stripped.empty, f"{col}: spaces not stripped, e.g. {not_stripped.head().tolist()}"


@pytest.mark.parametrize("source", [s for s in SOURCES if SOURCES[s]["numeric"]])
def test_numeric_columns_typed(dirs, source):
    """Every non-NULL value of a numeric column is a number (unreadable values were set to NULL)."""
    columns = SOURCES[source]["numeric"]
    for chunk in staged_chunks(dirs, source, usecols=columns):
        for col in columns:
            values = chunk[col].dropna()
            not_numbers = values[pd.to_numeric(values, errors="coerce").isna()]
            assert not_numbers.empty, f"{col}: not numbers, e.g. {not_numbers.head().tolist()}"