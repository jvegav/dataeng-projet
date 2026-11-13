"""Run the whole data preparation (staging + processing), then update the ingestion log.

For each source: staging script, processing script, row counts, log entry.
The MET seed has no staging or processing: raw/r_met.csv is copied to processed/p_met.csv.

Usage (paths and the SAMPLE / DATA_DIR / CHUNK_SIZE variables are handled by config.py):
    python scripts_data_prep/run_pipeline.py            # skips the sources already ingested
    python scripts_data_prep/run_pipeline.py --force    # runs everything again

Ingestion log: ingestion_log.json, next to the processed folder, one entry per raw file
(source, file, SHA-256, date, rows read / kept / rejected). A source is skipped when its raw file
and the scripts that process it have the same SHA-256 as in the log and its outputs exist.
The raw files are only read, never modified.
"""

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import PROCESSED_DIR, RAW_DIR, STAGING_DIR

SCRIPTS_DIR = Path(__file__).resolve().parent
LOG_PATH = PROCESSED_DIR.parent / "ingestion_log.json"

# Order of the runs. "kept" and "rejected" are the processed files used for the row counts.
SOURCES = [
    {
        "name": "recipes",
        "raw": "r_recipes.zip",
        "staging_script": "staging_recipes.py",
        "processing_script": "processing_recipes.py",
        "staged": "s_recipes.csv",
        "kept": "p_recipes.csv",
        "rejected": "p_recipes_rejected.csv",
        "how_to_get": "download it with the curl command documented in documentation/sources.md",
    },
    {
        "name": "landmarks",
        "raw": "r_landmarks.csv",
        "staging_script": "staging_landmarks.py",
        "processing_script": "processing_landmarks.py",
        "staged": "s_landmarks.csv",
        "kept": "p_landmarks.csv",
        "rejected": "p_landmarks_rejected.csv",
        "how_to_get": "download it from https://www.data.gouv.fr/fr/datasets/r/3a52af4a-f9da-4dcc-8110-b07774dfb3bc",
    },
    {
        "name": "restaurants",
        "raw": "r_restaurant_data_kaggles.csv",
        "staging_script": "staging_restaurants.py",
        "processing_script": "processing_restaurants.py",
        "staged": "s_restaurants.csv",
        "kept": "p_restaurants.csv",
        "rejected": "p_restaurants_rejected.csv",
        "how_to_get": "download it manually from Kaggle (login required)",
    },
]
MET = {"name": "met", "raw": "r_met.csv", "kept": "p_met.csv",
       "how_to_get": "it is versioned in the repository (data/raw/r_met.csv)"}

# Text cells can be very long (ingredients): do not stop on csv's default field size limit
csv.field_size_limit(2**31 - 1)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scripts_sha256(source):
    """One hash for the staging script, the processing script and config.py:
    a change in the code makes the source run again."""
    digest = hashlib.sha256()
    for name in (source["staging_script"], source["processing_script"], "config.py"):
        digest.update(sha256_file(SCRIPTS_DIR / name).encode("ascii"))
    return digest.hexdigest()


def count_rows(path):
    """Number of data rows of a CSV file (header excluded, quoted line breaks handled)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        return sum(1 for _ in reader)


def load_log():
    if LOG_PATH.exists():
        with open(LOG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_log(log):
    """Written to a temporary file, then replaced: the log is never half written."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = LOG_PATH.with_name(LOG_PATH.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(temp, LOG_PATH)


def run_script(name):
    print(f"\n--- Running {name}")
    result = subprocess.run([sys.executable, str(SCRIPTS_DIR / name)])
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed (exit code {result.returncode})")


def log_entry(source_name, raw_name, raw_hash, code_hash, read, kept, rejected):
    return {
        "source": source_name,
        "file": raw_name,
        "sha256": raw_hash,
        "scripts_sha256": code_hash,
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows_read": read,
        "rows_kept": kept,
        "rows_rejected": rejected,
    }


def ingest_source(source, log, force):
    raw_path = RAW_DIR / source["raw"]
    outputs = [PROCESSED_DIR / source["kept"], PROCESSED_DIR / source["rejected"]]
    raw_hash = sha256_file(raw_path)
    code_hash = scripts_sha256(source)

    entry = log.get(source["raw"])
    if (not force and entry and entry["sha256"] == raw_hash and entry["scripts_sha256"] == code_hash
            and all(p.exists() for p in outputs)):
        print(f"\n--- {source['name']}: already ingested (same raw file and scripts), skipped")
        return "skipped", entry

    run_script(source["staging_script"])
    run_script(source["processing_script"])

    read = count_rows(STAGING_DIR / source["staged"])
    kept = count_rows(PROCESSED_DIR / source["kept"])
    rejected = count_rows(PROCESSED_DIR / source["rejected"])
    if read != kept + rejected:
        raise RuntimeError(f"{source['name']}: {read} rows staged but {kept} kept + {rejected} rejected")

    entry = log_entry(source["name"], source["raw"], raw_hash, code_hash, read, kept, rejected)
    log[source["raw"]] = entry
    save_log(log)
    return "ingested", entry


def ingest_met(log, force):
    raw_path = RAW_DIR / MET["raw"]
    output = PROCESSED_DIR / MET["kept"]
    raw_hash = sha256_file(raw_path)

    entry = log.get(MET["raw"])
    if not force and entry and entry["sha256"] == raw_hash and output.exists() and sha256_file(output) == raw_hash:
        print(f"\n--- {MET['name']}: already copied (same raw file), skipped")
        return "skipped", entry

    print(f"\n--- Copying {raw_path.name} to {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".tmp")
    shutil.copyfile(raw_path, temp)
    os.replace(temp, output)

    rows = count_rows(output)
    entry = log_entry(MET["name"], MET["raw"], raw_hash, None, rows, rows, 0)
    log[MET["raw"]] = entry
    save_log(log)
    return "copied", entry


def main():
    parser = argparse.ArgumentParser(description="Run staging, processing and the MET copy, and update the ingestion log.")
    parser.add_argument("--force", action="store_true", help="run every source again, even if already ingested")
    args = parser.parse_args()

    # Every raw file must be there before anything runs
    missing = [s for s in SOURCES + [MET] if not (RAW_DIR / s["raw"]).exists()]
    if missing:
        print("Missing raw file(s) in", RAW_DIR)
        for s in missing:
            print(f"  - {s['raw']}: {s['how_to_get']}")
        return 1

    log = load_log()
    results = []
    try:
        for source in SOURCES:
            results.append((source["name"],) + ingest_source(source, log, args.force))
        results.append((MET["name"],) + ingest_met(log, args.force))
    except RuntimeError as error:
        print(f"\nERROR: {error}")
        return 1

    print("\n=== Summary")
    print(f"{'source':<12}{'status':<10}{'read':>10}{'kept':>10}{'rejected':>10}")
    for name, status, entry in results:
        print(f"{name:<12}{status:<10}{entry['rows_read']:>10}{entry['rows_kept']:>10}{entry['rows_rejected']:>10}")
    print("\nIngestion log:", LOG_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())