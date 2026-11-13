from charset_normalizer import from_path
from config import RAW_DIR

# Define paths
input_path = RAW_DIR / "r_met.csv"

result = from_path(input_path).best()

print("Detected encoding:", result.encoding)