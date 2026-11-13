"""Runner tests: hash-skip and --force of run_pipeline.py.

Each test copies data/sample/ into a temporary folder and runs the runner there
(DATA_DIR + SAMPLE=true), so your data/ folder is never touched. The --data option does not apply here.

    pytest tests/test_runner.py
"""

import hashlib
import json

import pytest

from conftest import copy_sample, run_pipeline

FIRST_RUN = {"recipes": "ingested", "landmarks": "ingested", "restaurants": "ingested", "met": "copied"}
ALL_SKIPPED = {name: "skipped" for name in FIRST_RUN}


def statuses(result):
    """Status of each source, read from the summary table printed by the runner."""
    assert result.returncode == 0, f"runner failed:\n{result.stdout}\n{result.stderr}"
    summary = result.stdout.split("=== Summary", 1)[1].splitlines()
    found = {}
    for line in summary:
        parts = line.split()
        if len(parts) == 5 and parts[0] in FIRST_RUN:
            found[parts[0]] = parts[1]
    return found


def output_files(data_dir):
    run_dir = data_dir / "sample_run"
    return sorted(p for p in run_dir.rglob("*.csv"))


def fingerprints(data_dir):
    """Content hash and modification time of every staging and processed file."""
    return {p.relative_to(data_dir).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in output_files(data_dir)}


def read_log(data_dir):
    return json.loads((data_dir / "sample_run" / "ingestion_log.json").read_text(encoding="utf-8"))


@pytest.fixture
def data_dir(tmp_path):
    """A fresh copy of the sample, already ingested once."""
    copy_sample(tmp_path)
    assert statuses(run_pipeline(tmp_path)) == FIRST_RUN
    return tmp_path


def test_first_run_writes_log(tmp_path):
    copy_sample(tmp_path)
    assert statuses(run_pipeline(tmp_path)) == FIRST_RUN

    log = read_log(tmp_path)
    assert set(log) == {"r_recipes.zip", "r_landmarks.csv", "r_restaurant_data_kaggles.csv", "r_met.csv"}
    for entry in log.values():
        assert entry["rows_read"] == entry["rows_kept"] + entry["rows_rejected"]
        assert entry["sha256"] == hashlib.sha256((tmp_path / "sample" / entry["file"]).read_bytes()).hexdigest()
    assert log["r_met.csv"]["rows_rejected"] == 0


def test_second_run_skips_everything(data_dir):
    log_before, files_before = read_log(data_dir), fingerprints(data_dir)

    assert statuses(run_pipeline(data_dir)) == ALL_SKIPPED
    assert read_log(data_dir) == log_before          # one entry per file, unchanged
    assert fingerprints(data_dir) == files_before    # no file rewritten


def test_force_runs_everything_with_same_result(data_dir):
    contents_before = {name: sha for name, (sha, _) in fingerprints(data_dir).items()}

    assert statuses(run_pipeline(data_dir, "--force")) == FIRST_RUN
    contents_after = {name: sha for name, (sha, _) in fingerprints(data_dir).items()}
    assert contents_after == contents_before
    assert len(read_log(data_dir)) == 4                  # still one entry per file


def test_changed_raw_file_runs_only_that_source(data_dir):
    raw = data_dir / "sample" / "r_restaurant_data_kaggles.csv"
    with open(raw, "a", encoding="utf-8", newline="") as f:
        f.write("\r\n")      # empty line: new SHA-256, same rows
    old_hash = read_log(data_dir)["r_restaurant_data_kaggles.csv"]["sha256"]

    assert statuses(run_pipeline(data_dir)) == {**ALL_SKIPPED, "restaurants": "ingested"}
    assert read_log(data_dir)["r_restaurant_data_kaggles.csv"]["sha256"] != old_hash


def test_changed_met_file_is_copied_again(data_dir):
    raw = data_dir / "sample" / "r_met.csv"
    raw.write_bytes(raw.read_bytes() + b"\r\n")

    assert statuses(run_pipeline(data_dir)) == {**ALL_SKIPPED, "met": "copied"}
    assert (data_dir / "sample_run" / "processed" / "p_met.csv").read_bytes() == raw.read_bytes()


def test_deleted_output_runs_only_that_source(data_dir):
    output = data_dir / "sample_run" / "processed" / "p_landmarks.csv"
    output.unlink()

    assert statuses(run_pipeline(data_dir)) == {**ALL_SKIPPED, "landmarks": "ingested"}
    assert output.exists()


def test_missing_raw_file_stops_before_running(tmp_path):
    copy_sample(tmp_path)
    (tmp_path / "sample" / "r_met.csv").unlink()

    result = run_pipeline(tmp_path)
    assert result.returncode == 1
    assert "Missing raw file" in result.stdout and "r_met.csv" in result.stdout
    assert not (tmp_path / "sample_run" / "ingestion_log.json").exists()