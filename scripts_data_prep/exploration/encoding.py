# Exploration script (one-off profiling), not part of the pipeline.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts_data_prep/, for config
from charset_normalizer import from_path
from config import RAW_DIR

# Define paths
input_path = RAW_DIR / "r_met.csv"

result = from_path(input_path).best()

print("Detected encoding:", result.encoding)