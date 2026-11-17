"""Draw a stratified sample of French communes (pilot corpus, milestone M1).

Input : data/processed/communes.csv  (output of wikidata_communes.py)
Output: data/sample_500.csv          (versioned in Git, unlike data/processed/)
        docs/sample_strata.csv       (control table: communes per class)

Design choices (to justify in the report):
- Strata = population class only, fixed quota per class (100 each), so that
  small and large communes can be compared. The sample is therefore NOT
  representative of the national distribution (97% of communes are small).
- Hand-picked communes (FORCED_INSEE) are always included; each one replaces a
  randomly drawn, non-forced commune of the same class, so the total stays 500.
- Fixed seed + sort by insee => two runs give a byte-identical file.

Usage:
    python src/make_sample.py
"""
from pathlib import Path

import pandas as pd

INPUT = "data/processed/communes.csv"
OUTPUT = "data/sample_500.csv"
STRATA_OUTPUT = "docs/sample_strata.csv"

SEED = 42
SIZE_BINS = [-1, 499, 1999, 9999, 49999, float("inf")]   # right-inclusive
SIZE_LABELS = ["<500", "500-1999", "2000-9999", "10000-49999", ">=50000"]
QUOTAS = {label: 100 for label in SIZE_LABELS}            # 5 x 100 = 500

# Fontainebleau, Bois-le-Roi (Seine-et-Marne; 27073 is another commune), Paris
FORCED_INSEE = ["77186", "77037", "75056"]


def load_communes(path: str) -> pd.DataFrame:
    """Read communes.csv. `insee` must stay text (leading zeros, 2A/2B)."""
    return pd.read_csv(path, dtype={"insee": str}, encoding="utf-8")


def add_department(df: pd.DataFrame) -> pd.DataFrame:
    """Add a `departement` column derived from `insee`."""
    df = df.copy()
    is_overseas = df["insee"].str.startswith("97")
    df["departement"] = df["insee"].str[:2].where(~is_overseas, df["insee"].str[:3])
    return df


def add_size_class(df: pd.DataFrame, bins: list, labels: list) -> pd.DataFrame:
    """Add a `taille` column. Bounds are right-inclusive; missing population
    gives a missing class (and is reported by main)."""
    df = df.copy()
    df["taille"] = pd.cut(df["pop"], bins=bins, labels=labels, right=True)
    return df


def count_strata(df: pd.DataFrame) -> pd.DataFrame:
    """Number of communes per size class."""
    return df.groupby("taille", observed=False).size().rename("communes").to_frame()


def draw_stratified(df: pd.DataFrame, quotas: dict, seed: int) -> pd.DataFrame:
    """Draw min(quota, class size) communes in each size class."""
    parts = []
    for label, quota in quotas.items():
        stratum = df[df["taille"] == label]
        n = min(quota, len(stratum))
        parts.append(stratum.sample(n=n, random_state=seed))
    return pd.concat(parts)


def add_forced_communes(sample: pd.DataFrame, df: pd.DataFrame,
                        insee_list: list, seed: int) -> pd.DataFrame:
    """Include hand-picked communes. A forced commune not already drawn replaces
    a random non-forced commune of the same class (total size unchanged)."""
    unknown = set(insee_list) - set(df["insee"])
    if unknown:
        raise ValueError(f"Forced INSEE codes not found: {sorted(unknown)}")
    sample = sample.copy()
    for code in insee_list:
        if code in set(sample["insee"]):
            continue
        row = df[df["insee"] == code]
        cls = row["taille"].iloc[0]
        candidates = sample[(sample["taille"] == cls) & ~sample["insee"].isin(insee_list)]
        if candidates.empty:
            sample = pd.concat([sample, row])         # no room: sample grows by 1
        else:
            drop = candidates.sample(n=1, random_state=seed).index
            sample = pd.concat([sample.drop(index=drop), row])
    return sample


def check_sample(sample: pd.DataFrame, df: pd.DataFrame, quotas: dict,
                 forced: list) -> None:
    """Raise an AssertionError when a sanity check fails."""
    assert sample["insee"].is_unique, "duplicate insee in sample"
    assert set(sample["insee"]) <= set(df["insee"]), "unknown insee in sample"
    assert set(forced) <= set(sample["insee"]), "a forced commune is missing"
    counts = sample["taille"].value_counts()
    for label, quota in quotas.items():
        n_class = int((df["taille"] == label).sum())
        assert counts.get(label, 0) == min(quota, n_class), f"class {label}: wrong count"
    assert len(sample) == sum(min(q, int((df["taille"] == l).sum()))
                              for l, q in quotas.items()), "wrong sample size"


def save_sample(sample: pd.DataFrame, path: str) -> None:
    """Write the CSV sorted by insee (byte-identical across runs)."""
    cols = ["insee", "qid", "name", "pop", "lat", "lon", "departement", "taille"]
    out = sample.sort_values("insee")[cols]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, encoding="utf-8")


def main() -> None:
    communes = add_size_class(add_department(load_communes(INPUT)), SIZE_BINS, SIZE_LABELS)
    print(f"{len(communes)} communes, {communes['departement'].nunique()} departments, "
          f"{communes['taille'].isna().sum()} without size class")

    strata = count_strata(communes)
    print("\nCommunes per class (whole of France):")
    print(strata)

    sample = draw_stratified(communes, QUOTAS, SEED)
    sample = add_forced_communes(sample, communes, FORCED_INSEE, SEED)
    check_sample(sample, communes, QUOTAS, FORCED_INSEE)
    save_sample(sample, OUTPUT)

    control = strata.join(sample["taille"].value_counts().rename("in_sample"))
    Path(STRATA_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    control.to_csv(STRATA_OUTPUT)
    print(f"\nSample: {len(sample)} communes, {sample['departement'].nunique()} departments")
    print(control)
    print(f"\nSaved {OUTPUT} and {STRATA_OUTPUT}")


if __name__ == "__main__":
    main()