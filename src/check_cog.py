"""Compare data/processed/communes.csv with the INSEE COG (official list of communes).

Usage:
    python src/check_cog.py path\\to\\v_commune_2026.csv
    python src/check_cog.py path\\to\\v_commune_2026.csv --mine data/processed/communes.csv

Download the COG (communes file) from insee.fr, "Code officiel geographique".
Only rows with TYPECOM == COM are kept (excludes arrondissements, associated
and delegated communes). Column names are matched case-insensitively.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd


def find_col(df, *names):
    cols = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in cols:
            return cols[n.lower()]
    sys.exit(f"Column not found, looked for {names}. Columns available: {list(df.columns)}")


def dept_key(code):
    return code[:3] if code[:2] == "97" else code[:2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cog", help="INSEE COG communes file (csv)")
    ap.add_argument("--mine", default="data/processed/communes.csv")
    ap.add_argument("--out", default="data/processed/cog_check.txt")
    args = ap.parse_args()

    cog = pd.read_csv(args.cog, dtype=str, sep=None, engine="python")
    c_type = find_col(cog, "TYPECOM")
    c_code = find_col(cog, "COM")
    c_name = find_col(cog, "LIBELLE", "NCCENR")
    cog = cog[cog[c_type] == "COM"].copy()

    mine = pd.read_csv(args.mine, dtype=str)

    ref = set(cog[c_code])
    got = set(mine["insee"])
    missing = sorted(ref - got)
    extra = sorted(got - ref)

    lines = []
    lines.append(f"COG communes (TYPECOM=COM): {len(ref)}")
    lines.append(f"My extraction             : {len(got)}")
    lines.append(f"Difference                : {len(got) - len(ref):+d}")
    lines.append("")

    lines.append(f"MISSING (in COG, not in Wikidata extraction): {len(missing)}")
    if missing:
        lines.append(cog[cog[c_code].isin(missing)][[c_code, c_name]].to_string(index=False))
    lines.append("")

    lines.append(f"EXTRA (in extraction, not in COG): {len(extra)}")
    if extra:
        lines.append(mine[mine["insee"].isin(extra)][["qid", "insee", "name", "pop", "lat"]]
                     .to_string(index=False))
    lines.append("")

    # per-department comparison
    a = cog[c_code].map(dept_key).value_counts().rename("cog")
    b = mine["insee"].map(dept_key).value_counts().rename("mine")
    cmp_ = pd.concat([a, b], axis=1).fillna(0).astype(int)
    cmp_["diff"] = cmp_["mine"] - cmp_["cog"]
    bad = cmp_[cmp_["diff"] != 0]
    lines.append(f"Departments with a different count: {len(bad)}")
    if len(bad):
        lines.append(bad.to_string())
    lines.append("")

    # suspects: incomplete rows
    no_name = mine[mine["name"].isna()][["qid", "insee", "pop"]]
    no_coord = mine[mine["lat"].isna()][["qid", "insee", "name"]]
    lines.append(f"Rows without name ({len(no_name)}):")
    lines.append(no_name.to_string(index=False) if len(no_name) else "  none")
    lines.append(f"Rows without coordinates ({len(no_coord)}):")
    lines.append(no_coord.to_string(index=False) if len(no_coord) else "  none")

    text = "\n".join(lines)
    print(text)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"\nReport saved to {args.out}")


if __name__ == "__main__":
    main()