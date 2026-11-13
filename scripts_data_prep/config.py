"""Shared settings for the data preparation scripts.

Base directory
--------------
By default the data folder is <project root>/data, where <project root> is the
parent of the folder that contains this file. The location does not depend on
the folder the script is launched from. Two environment variables change it:

    DATA_DIR   path of the data folder (e.g. /opt/airflow/data inside Docker)
    SAMPLE     "true" -> read data/sample/ and write to data/sample_run/, so the
               real staging and processed files are never overwritten
"""

import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", PROJECT_ROOT / "data")).resolve()
SAMPLE = os.environ.get("SAMPLE", "false").strip().lower() in {"1", "true", "yes"}

if SAMPLE:
    RAW_DIR = DATA_DIR / "sample"
    STAGING_DIR = DATA_DIR / "sample_run" / "staging"
    PROCESSED_DIR = DATA_DIR / "sample_run" / "processed"
else:
    RAW_DIR = DATA_DIR / "raw"
    STAGING_DIR = DATA_DIR / "staging"
    PROCESSED_DIR = DATA_DIR / "processed"

# Texts used by the sources instead of a real missing value
NULL_PLACEHOLDERS = {"no information", "no informations", "no_information"}


def clean_text(series: pd.Series) -> pd.Series:
    """Strip spaces; turn empty strings and 'no information' placeholders into NULL."""
    text = series.astype("string").str.strip()
    is_null = (text.eq("") | text.str.casefold().isin(NULL_PLACEHOLDERS)).fillna(False)
    return text.mask(is_null)


def to_number(series: pd.Series):
    """Convert a text column to a nullable Float64 column.

    Missing values stay NULL (<NA>, never NaN). Returns the converted column and
    the list of values that were not empty but could not be read as a number,
    so that nothing is lost silently.
    """
    cleaned = clean_text(series)
    numbers = pd.to_numeric(cleaned, errors="coerce").astype("Float64")
    invalid = cleaned[cleaned.notna() & numbers.isna()]
    return numbers, invalid