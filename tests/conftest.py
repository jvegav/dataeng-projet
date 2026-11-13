"""Shared settings for the ingestion tests.

    pytest tests                  staging and processing tests on the sample: the runner is run on a
                                  temporary copy of data/sample/ (your data/ folder is not touched)
    pytest tests --data real      staging and processing tests on your real files in data/staging/ and
                                  data/processed/ (run run_pipeline.py first; nothing is rerun)

The runner tests (test_runner.py) always use a temporary copy of data/sample/.
"""

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts_data_prep"
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_FILES = ["r_recipes.zip", "r_landmarks.csv", "r_restaurant_data_kaggles.csv", "r_met.csv"]

sys.path.insert(0, str(SCRIPTS_DIR))


def pytest_addoption(parser):
    parser.addoption("--data", choices=["sample", "real"], default="sample",
                     help="files tested by test_staging.py and test_processing.py (default: sample)")


def run_pipeline(data_dir, *args):
    """Run run_pipeline.py with SAMPLE=true on data_dir/sample/ (outputs in data_dir/sample_run/)."""
    env = os.environ.copy()
    env.update(DATA_DIR=str(data_dir), SAMPLE="true", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(SCRIPTS_DIR / "run_pipeline.py"), *args],
                          cwd=PROJECT_ROOT, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def copy_sample(target_dir):
    """Copy data/sample/ into target_dir/sample/ and return target_dir."""
    source = DATA_DIR / "sample"
    missing = [name for name in SAMPLE_FILES if not (source / name).exists()]
    if missing:
        pytest.fail(f"Missing sample file(s) in {source}: {missing}. "
                    "Run python scripts_data_prep/make_sample.py first.")
    shutil.copytree(source, target_dir / "sample")
    return target_dir


@pytest.fixture(scope="session")
def dirs(request, tmp_path_factory):
    """Folders of the files under test: raw, staging and processed."""
    if request.config.getoption("--data") == "real":
        found = {"raw": DATA_DIR / "raw", "staging": DATA_DIR / "staging", "processed": DATA_DIR / "processed"}
        for name, path in found.items():
            if not path.is_dir():
                pytest.fail(f"{path} not found: run python scripts_data_prep/run_pipeline.py first")
        return found

    data_dir = copy_sample(tmp_path_factory.mktemp("data"))
    result = run_pipeline(data_dir, "--force")
    if result.returncode != 0:
        pytest.fail(f"run_pipeline.py failed on the sample:\n{result.stdout}\n{result.stderr}")
    return {"raw": data_dir / "sample",
            "staging": data_dir / "sample_run" / "staging",
            "processed": data_dir / "sample_run" / "processed"}


def read_csv(path, **kwargs):
    """Read a staging or processed CSV as text, the way the scripts read it: only empty cells are NULL."""
    if not Path(path).exists():
        pytest.fail(f"{path} not found")
    return pd.read_csv(path, encoding="utf-8", dtype=str, keep_default_na=False, na_values=[""], **kwargs)


def lyon_codes():
    """The INSEE codes list of processing_landmarks.py, read from the script (not copied here)."""
    tree = ast.parse((SCRIPTS_DIR / "processing_landmarks.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "lyon_codes" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("lyon_codes not found in processing_landmarks.py")