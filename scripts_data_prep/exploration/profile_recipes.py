# Exploration script (one-off profiling), not part of the pipeline.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts_data_prep/, for config
import pandas as pd
from config import RAW_DIR


path = RAW_DIR / "r_recipes.zip"
df = pd.read_csv(path, compression="zip", dtype=str)  

print("rows:", len(df))
print("nulls:\n", df.replace("", pd.NA).isna().sum())
print("dup recipe_id (distinct / surplus rows):",
      df.recipe_id[df.recipe_id.duplicated(keep=False)].nunique(),
      df.recipe_id.duplicated().sum())

cal = pd.to_numeric(df["calories [cal]"], errors="coerce")
srv = pd.to_numeric(df["servingsPerRecipe"], errors="coerce")
print("calories non-numeric:", cal.isna().sum() - df["calories [cal]"].isna().sum())
print("calories == 0:", (cal == 0).sum(), "| < 0:", (cal < 0).sum(), "| > 3000:", (cal > 3000).sum(), "| max:", cal.max())
print(df.loc[cal > 3000, ["recipe_id", "title", "calories [cal]", "servingsPerRecipe"]].head(5))
print("servings null:", srv.isna().sum(), "| == 0:", (srv == 0).sum(),
      "| non-integer:", (srv.dropna() % 1 != 0).sum(), "| > 50:", (srv > 50).sum())
print("bad url:", (~df.recipe_url.fillna("").str.contains(r"^https?://(www\.)?food\.com/")).sum())
print("ingredients sample:", df.ingredients.iloc[0][:200])