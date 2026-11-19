import pandas as pd

# Lire un fichier CSV standard
df = pd.read_csv(
    "data/processed/communes.csv",
    sep=",",
    encoding="utf-8",
    skiprows=1
)

print(df)