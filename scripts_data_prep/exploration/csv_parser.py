# Exploration script (one-off profiling), not part of the pipeline.
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # scripts_data_prep/, for config

import zipfile
import csv
import unicodedata
from config import RAW_DIR


zip_path = RAW_DIR / "r_recipes.zip"
csv_name = RAW_DIR / "r_restaurant_data_kaggles.csv"

'''
#parser csv dans zip
with zipfile.ZipFile(zip_path, "r") as archive:
    with archive.open(csv_name) as file:
        text_file = __import__("io").TextIOWrapper(
            file, encoding="utf-8-sig", newline=""
        )

        reader = csv.reader(text_file)

        # Première ligne = header
        header = next(reader)

        # Comptage des enregistrements
        row_count = sum(1 for _ in reader)
'''


#parser csv sans zip
with open(csv_name, mode="r", encoding="utf-8-sig", newline="") as file:
    reader = csv.reader(file, delimiter=',')

    # Première ligne = header
    header = next(reader, None)

    # Nombre de colonnes
    column_count = len(header) if header else 0

    # Comptage des enregistrements (hors header)
    row_count = sum(1 for _ in reader)


'''
#parser csv de landmarks dans la metropole de Lyon
communes_metropole = [
    "Albigny-sur-Saône", "Bron", "Cailloux-sur-Fontaines",
    "Caluire-et-Cuire", "Champagne-au-Mont-d'Or",
    "Charbonnières-les-Bains", "Charly", "Chassieu",
    "Collonges-au-Mont-d'Or", "Corbas", "Couzon-au-Mont-d'Or",
    "Craponne", "Curis-au-Mont-d'Or", "Dardilly",
    "Décines-Charpieu", "Écully", "Feyzin", "Fleurieu-sur-Saône",
    "Fontaines-Saint-Martin", "Fontaines-sur-Saône",
    "Francheville", "Genay", "Givors", "Grigny-sur-Rhône",
    "Irigny", "Jonage", "La Mulatière", "La Tour-de-Salvagny",
    "Limonest", "Lissieu", "Lyon", "Marcy-l'Étoile",
    "Meyzieu", "Mions", "Montanay", "Neuville-sur-Saône",
    "Oullins-Pierre-Bénite", "Poleymieux-au-Mont-d'Or",
    "Quincieux", "Rillieux-la-Pape", "Rochetaillée-sur-Saône",
    "Saint-Cyr-au-Mont-d'Or", "Saint-Didier-au-Mont-d'Or",
    "Saint-Fons", "Saint-Genis-Laval",
    "Saint-Genis-les-Ollières", "Saint-Germain-au-Mont-d'Or",
    "Saint-Priest", "Saint-Romain-au-Mont-d'Or",
    "Sainte-Foy-lès-Lyon", "Sathonay-Camp",
    "Sathonay-Village", "Solaize", "Tassin-la-Demi-Lune",
    "Vaulx-en-Velin", "Vénissieux", "Vernaison", "Villeurbanne"
]

# Normalisation des noms de communes
def normaliser(nom):
    nom = unicodedata.normalize("NFD", nom.strip().lower())
    nom = "".join(c for c in nom if unicodedata.category(c) != "Mn")
    return nom.replace("’", "'")

communes_normalisees = {
    normaliser(commune) for commune in communes_metropole
}

landmark_count = 0
with open(csv_name, mode="r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file, delimiter='|')

    for row in reader:
        commune = normaliser(row["Commune_forme_index"])

        if commune in communes_normalisees:
            landmark_count += 1
'''

print(f"Number of columns: {column_count}")
print(f"Number of rows (excluding header): {row_count}")