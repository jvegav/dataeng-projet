import pandas as pd

df = pd.read_csv("../data/raw/landmarks.csv", sep="|", dtype=str, encoding="utf-8")
print("rows / cols:", df.shape)  # expect 46761 x 78

lyon_codes = {
    "69003", "69029", "69033", "69034", "69040",
    "69044", "69046", "69271", "69063", "69273",
    "69068", "69069", "69071", "69072", "69275",
    "69081", "69276", "69085", "69087", "69088",
    "69089", "69278", "69091", "69096", "69100",
    "69279", "69116", "69117", "69123", "69127",
    "69282", "69283", "69284", "69142", "69143",
    "69149", "69153", "69163", "69286", "69168",
    "69191", "69194", "69199", "69204", "69205",
    "69207", "69290", "69233", "69202", "69292",
    "69293", "69296", "69244", "69250", "69256",
    "69260", "69266", "69259"
}
col = "COG_Insee_lors_de_la_protection"
lyon = df[df[col].isin(lyon_codes)]
print("lyon rows:", len(lyon))

coords = lyon["coordonnees_au_format_WGS84"].fillna("").str.strip()
print("no coords (lyon / france):", (coords == "").sum(),
      (df["coordonnees_au_format_WGS84"].fillna("").str.strip() == "").sum())

ll = coords.str.extract(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$").astype(float)
ll.columns = ["lat", "lon"]
print("malformed (non-empty):", ((coords != "") & ll.lat.isna()).sum())
out = ll.dropna()[~ll.dropna().lat.between(45.55, 45.95) | ~ll.dropna().lon.between(4.65, 5.15)]
print("outside bbox:", len(out)); 
print(
    lyon.loc[
        out.index,
        [
            "Identifiant_Agregee",
            "Denomination_de_l_edifice",
            "coordonnees_au_format_WGS84"
        ]
    ].head()
)
ref = "Reference"  # check the exact column name
for name, d in [("lyon", lyon), ("france", df)]:
    dup = d[ref][d[ref].duplicated(keep=False)]
    print(name, "dup refs:", dup.nunique(), "surplus rows:", d[ref].duplicated().sum())
print("encoding BOM / whitespace:", (lyon.Denomination_de_l_edifice != lyon.Denomination_de_l_edifice.str.strip()).sum())