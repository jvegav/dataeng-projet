import zipfile

with zipfile.ZipFile("../data/raw/pp_recipes.zip", "r") as zip_ref:
    zip_ref.extractall("../data/staging/")