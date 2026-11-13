"""Processing tests on the p_*.csv files (issue #6): columns, required values, unique IDs,
no duplicates, calories, MET and speeds, coordinates, and the rejected files.

    pytest tests/test_processing.py               on the sample
    pytest tests/test_processing.py --data real   on data/processed/
"""

import hashlib

import pandas as pd
import pytest

from conftest import lyon_codes, read_csv

LAT_MIN, LAT_MAX = 45.4, 46.1
LON_MIN, LON_MAX = 4.5, 5.3
INT_MAX = 2**31 - 1        # PostgreSQL INT
BIGINT_MAX = 2**63 - 1     # PostgreSQL BIGINT

# Kept columns, in file order (MET: written by hand, so only the set of columns is checked)
COLUMNS = {
    "p_recipes.csv": ["source_id", "title", "ingredients", "recipe_url", "servings",
                      "kcal_per_serving", "category", "total_kcal"],
    "p_restaurants.csv": ["source_id", "restaurant_name", "food_type", "lat", "lng", "overall_rating", "district"],
    "p_landmarks.csv": ["source_id", "commune", "insee_code", "building_name", "lat", "lon", "address"],
}
MET_COLUMNS = {"activity_key", "activity_name", "speed_kmh", "met_value", "intensity"}

# NOT NULL columns of the DDL
REQUIRED = {
    "p_recipes.csv": ["source_id", "title", "kcal_per_serving"],
    "p_restaurants.csv": ["source_id", "restaurant_name", "lat", "lng"],
    "p_landmarks.csv": ["source_id", "building_name", "lat", "lon"],
    "p_met.csv": ["activity_key", "activity_name", "speed_kmh", "met_value", "intensity"],
}

# Unique keys
UNIQUE = {
    "p_recipes.csv": [["source_id"]],
    "p_restaurants.csv": [["source_id"], ["restaurant_name", "lat", "lng"]],
    "p_landmarks.csv": [["source_id"]],
    "p_met.csv": [["activity_key"], ["activity_name"]],
}

# Staged file, rejected file and possible reject_reason values of each source
REJECTS = {
    "recipes": ("s_recipes.csv", "p_recipes.csv", "p_recipes_rejected.csv",
                {"missing_source_id", "invalid_source_id", "missing_title", "missing_calories",
                 "non_positive_calories", "calories_out_of_range", "duplicate_source_id"}),
    "restaurants": ("s_restaurants.csv", "p_restaurants.csv", "p_restaurants_rejected.csv",
                    {"missing_name", "missing_coordinates", "outside_bounding_box", "rating_out_of_range",
                     "duplicate_restaurant", "duplicate_source_id"}),
    "landmarks": ("s_landmarks.csv", "p_landmarks.csv", "p_landmarks_rejected.csv",
                  {"missing_insee_code", "outside_lyon_scope", "missing_id", "missing_name", "invalid_id",
                   "missing_coordinates", "invalid_coordinates", "outside_bounding_box", "duplicate_id"}),
}

RECIPE_COLUMNS = ["source_id", "servings", "kcal_per_serving", "total_kcal"]   # ingredients not loaded


def processed(dirs, name, usecols=None):
    return read_csv(dirs["processed"] / name, usecols=usecols)


def as_int(series):
    """Text column -> Int64; fails if a value is not a whole number."""
    numbers = pd.to_numeric(series, errors="coerce")
    bad = series[series.notna() & (numbers.isna() | (numbers % 1 != 0))]
    assert bad.empty, f"{series.name}: not whole numbers, e.g. {bad.head().tolist()}"
    return numbers.astype("Int64")


def as_float(series):
    numbers = pd.to_numeric(series, errors="coerce")
    bad = series[series.notna() & numbers.isna()]
    assert bad.empty, f"{series.name}: not numbers, e.g. {bad.head().tolist()}"
    return numbers.astype("Float64")


# --- All sources ---------------------------------------------------------------------------------

@pytest.mark.parametrize("name", COLUMNS)
def test_columns_present(dirs, name):
    assert read_csv(dirs["processed"] / name, nrows=0).columns.tolist() == COLUMNS[name]


def test_met_columns_present(dirs):
    assert set(read_csv(dirs["processed"] / "p_met.csv", nrows=0).columns) == MET_COLUMNS


@pytest.mark.parametrize("name", REQUIRED)
def test_required_values_present(dirs, name):
    df = processed(dirs, name, usecols=REQUIRED[name])
    missing = df.isna().sum()
    assert missing.sum() == 0, f"NULL in required columns:\n{missing[missing > 0]}"


@pytest.mark.parametrize("name, key", [(n, k) for n, keys in UNIQUE.items() for k in keys],
                         ids=lambda v: v if isinstance(v, str) else "+".join(v))
def test_unique_ids_no_duplicates(dirs, name, key):
    df = processed(dirs, name, usecols=key)
    duplicates = df[df.duplicated(keep=False)]
    assert duplicates.empty, f"duplicates on {key}, e.g.\n{duplicates.head()}"


@pytest.mark.parametrize("source", REJECTS)
def test_every_staged_row_is_kept_or_rejected(dirs, source):
    staged, kept, rejected, _ = REJECTS[source]
    count = lambda folder, name: len(read_csv(dirs[folder] / name, usecols=[0]))
    assert count("processed", kept) + count("processed", rejected) == count("staging", staged)


@pytest.mark.parametrize("source", REJECTS)
def test_reject_reasons(dirs, source):
    _, _, rejected, reasons = REJECTS[source]
    values = processed(dirs, rejected, usecols=["reject_reason"])["reject_reason"]
    assert values.notna().all(), "rejected rows without reject_reason"
    assert set(values) <= reasons, f"unknown reasons: {set(values) - reasons}"


# --- Recipes -------------------------------------------------------------------------------------

def test_recipes_source_id_is_int(dirs):
    ids = as_int(processed(dirs, "p_recipes.csv", usecols=["source_id"])["source_id"])
    assert ids.between(-INT_MAX - 1, INT_MAX).all()


def test_recipes_calories(dirs):
    """kcal_per_serving: whole number between 1 and 3000 (so positive)."""
    kcal = as_int(processed(dirs, "p_recipes.csv", usecols=["kcal_per_serving"])["kcal_per_serving"])
    out = kcal[~kcal.between(1, 3000)]
    assert out.empty, f"kcal_per_serving out of 1-3000, e.g. {out.head().tolist()}"


def test_recipes_servings(dirs):
    """servings: whole number > 0, or NULL."""
    servings = as_int(processed(dirs, "p_recipes.csv", usecols=["servings"])["servings"]).dropna()
    assert (servings > 0).all()


def test_recipes_total_kcal(dirs):
    """total_kcal = kcal_per_serving x servings, NULL exactly when servings is NULL."""
    df = processed(dirs, "p_recipes.csv", usecols=RECIPE_COLUMNS)
    kcal, servings, total = as_int(df["kcal_per_serving"]), as_int(df["servings"]), as_int(df["total_kcal"])
    assert total.isna().equals(servings.isna())
    has = servings.notna()
    assert (total[has] == kcal[has] * servings[has]).all()
    assert (total[has] >= 0).all()


# --- Restaurants ---------------------------------------------------------------------------------

def test_restaurants_coordinates(dirs):
    df = processed(dirs, "p_restaurants.csv", usecols=["lat", "lng"])
    lat, lng = as_float(df["lat"]), as_float(df["lng"])
    assert lat.between(LAT_MIN, LAT_MAX).all() and lng.between(LON_MIN, LON_MAX).all()


def test_restaurants_source_id(dirs):
    """source_id = first 15 hex digits of md5(restaurant_name|lat|lng), read as a number (BIGINT)."""
    df = processed(dirs, "p_restaurants.csv", usecols=["source_id", "restaurant_name", "lat", "lng"])
    ids = as_int(df["source_id"])
    expected = [int(hashlib.md5(f"{n}|{float(la):.10g}|{float(lo):.10g}".encode("utf-8")).hexdigest()[:15], 16)
                for n, la, lo in zip(df["restaurant_name"], df["lat"], df["lng"])]
    assert ids.tolist() == expected
    assert ids.between(0, BIGINT_MAX).all()


def test_restaurants_rating(dirs):
    rating = as_float(processed(dirs, "p_restaurants.csv", usecols=["overall_rating"])["overall_rating"]).dropna()
    assert rating.between(0, 5).all()


def test_restaurants_food_type_separator(dirs):
    food = processed(dirs, "p_restaurants.csv", usecols=["food_type"])["food_type"].dropna()
    assert not food.str.contains(r"\s{2,}").any()


# --- Landmarks -----------------------------------------------------------------------------------

def test_landmarks_coordinates(dirs):
    df = processed(dirs, "p_landmarks.csv", usecols=["lat", "lon"])
    lat, lon = as_float(df["lat"]), as_float(df["lon"])
    assert lat.between(LAT_MIN, LAT_MAX).all() and lon.between(LON_MIN, LON_MAX).all()


def test_landmarks_in_lyon_scope(dirs):
    codes = processed(dirs, "p_landmarks.csv", usecols=["insee_code"])["insee_code"]
    outside = codes[~codes.isin(lyon_codes())]
    assert outside.empty, f"INSEE codes outside the Métropole: {sorted(set(outside.dropna()))}"


def test_landmarks_merimee_reference(dirs):
    ids = processed(dirs, "p_landmarks.csv", usecols=["source_id"])["source_id"]
    assert ids.str.fullmatch(r"PA\d+").all()


# --- MET -----------------------------------------------------------------------------------------

def test_met_nine_rows(dirs):
    assert len(processed(dirs, "p_met.csv")) == 9


def test_met_and_speed_positive(dirs):
    df = processed(dirs, "p_met.csv")
    assert (as_float(df["met_value"]) > 0).all() and (as_float(df["speed_kmh"]) > 0).all()


def test_met_intensity(dirs):
    """intensity from MET: <= 3 -> 1, <= 6 -> 2, > 6 -> 3."""
    df = processed(dirs, "p_met.csv")
    met, intensity = as_float(df["met_value"]), as_int(df["intensity"])
    expected = met.map(lambda m: 1 if m <= 3 else 2 if m <= 6 else 3)
    assert intensity.tolist() == expected.tolist()


def test_met_activity_key_is_int(dirs):
    as_int(processed(dirs, "p_met.csv")["activity_key"])


def test_met_copied_unchanged(dirs):
    assert (dirs["processed"] / "p_met.csv").read_bytes() == (dirs["raw"] / "r_met.csv").read_bytes()