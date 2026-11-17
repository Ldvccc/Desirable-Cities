"""Extract all French communes from Wikidata, department by department.

Output (in data/processed/):
    communes.csv, communes.parquet, communes_duplicates.csv,
    communes_report.txt, raw/dept_XX.json (cache of Wikidata answers)

Usage:
    python src/wikidata_communes.py
    python src/wikidata_communes.py --only 77 2A     # test on a few departments
    python src/wikidata_communes.py --out C:\\path\\to\\output

Cache: delete data/processed/raw/dept_XX.json to re-query a department,
or the whole raw/ folder to start again. Changing the query or EXTRA_QIDS
requires deleting the cache of the departments concerned.
EXCLUDE_INSEE is applied after the query, so no cache reset is needed for it.

Notes / assumptions to verify on wikidata.org:
- Q484170 = "commune of France", P374 = INSEE code, P1082 = population,
  P585 = point in time, P625 = coordinates, P576 = dissolved/abolished date.
- Reference total: 34 875 communes (metropole + DOM) on 1 Jan 2026
  (DGCL / INSEE, BIS 206). Validate with src/check_cog.py.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS = {
    "User-Agent": "UTSEUS-student-project/0.1 (replace-with-your-email@example.com)",
    "Accept": "application/sparql-results+json",
}
INSEE_REFERENCE_TOTAL = 34875  # metropole + DOM, 1 Jan 2026

# Communes that exist in Wikidata with an INSEE code (P374) but are NOT typed
# "commune of France" (P31 = Q484170), so the generic filter misses them.
# Paris (Q90): typed as metropole / collectivite a statut particulier /
# capitale nationale... Add other items here after comparing with the INSEE COG.
EXTRA_QIDS = ["Q90"]

# INSEE codes present in Wikidata but not valid in the INSEE COG 2026.
# Les Trois Lacs (Q26275353) carries two codes: old 27058 and current 27676.
EXCLUDE_INSEE = {"27058"}

# Metropolitan departments + Corsica + DOM
DEPARTMENTS = (
    [f"{i:02d}" for i in range(1, 20)]
    + ["2A", "2B"]
    + [f"{i:02d}" for i in range(21, 96)]
    + ["971", "972", "973", "974", "976"]
)

QUERY = """
SELECT ?commune ?communeLabel ?insee ?pop ?popDate ?coord WHERE {{
  {{
    SELECT ?commune ?insee WHERE {{
      {{ ?commune wdt:P31 wd:Q484170 . }}
      UNION
      {{ VALUES ?commune {{ {extra} }} }}
      ?commune wdt:P374 ?insee .
      FILTER(STRSTARTS(?insee, "{prefix}"))
      FILTER NOT EXISTS {{ ?commune wdt:P576 ?dissolved . }}
    }}
  }}
  OPTIONAL {{
    ?commune p:P1082 ?popStmt .
    ?popStmt ps:P1082 ?pop .
    OPTIONAL {{ ?popStmt pq:P585 ?popDate . }}
  }}
  OPTIONAL {{ ?commune wdt:P625 ?coord . }}
  OPTIONAL {{ ?commune rdfs:label ?communeLabel . FILTER(LANG(?communeLabel) = "fr") }}
}}
"""


def run_query(prefix, retries=4):
    extra = " ".join(f"wd:{q}" for q in EXTRA_QIDS)
    q = QUERY.format(prefix=prefix, extra=extra)
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(
                ENDPOINT, params={"query": q, "format": "json"},
                headers=HEADERS, timeout=120,
            )
            if r.status_code == 200:
                return r.json()["results"]["bindings"]
            print(f"  dept {prefix}: HTTP {r.status_code} (try {attempt}) {r.text[:150]}")
        except requests.RequestException as e:
            print(f"  dept {prefix}: {type(e).__name__} (try {attempt}) {e}")
        time.sleep(5 * attempt)
    return None


def val(row, key):
    return row[key]["value"] if key in row else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="restrict to these department prefixes")
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()

    out = Path(args.out)
    cache = out / "raw"
    cache.mkdir(parents=True, exist_ok=True)

    depts = args.only or DEPARTMENTS
    rows, failed = [], []
    for d in depts:
        f = cache / f"dept_{d}.json"
        if f.exists():
            res = json.loads(f.read_text(encoding="utf-8"))
            print(f"dept {d}: {len(res)} rows (cache)")
        else:
            res = run_query(d)
            if res is None:
                failed.append(d)
                continue
            f.write_text(json.dumps(res), encoding="utf-8")
            print(f"dept {d}: {len(res)} rows")
            time.sleep(1)  # be polite to the service
        for b in res:
            rows.append({
                "qid": val(b, "commune").rsplit("/", 1)[-1],
                "name": val(b, "communeLabel"),
                "insee": val(b, "insee"),
                "pop": val(b, "pop"),
                "pop_date": val(b, "popDate"),
                "coord": val(b, "coord"),
            })

    df = pd.DataFrame(rows)
    if df.empty:
        print("No data retrieved.")
        sys.exit(1)

    df["pop"] = pd.to_numeric(df["pop"], errors="coerce")
    # keep latest population per commune (undated values come first, so last() = latest)
    df = df.sort_values(["insee", "pop_date"], na_position="first")
    raw_rows = len(df)
    df = df.groupby(["qid", "insee"], as_index=False).last()

    # drop obsolete INSEE codes (see EXCLUDE_INSEE)
    excluded = df[df["insee"].isin(EXCLUDE_INSEE)][["qid", "insee", "name"]]
    df = df[~df["insee"].isin(EXCLUDE_INSEE)].copy()

    # coordinates "Point(lon lat)" -> two columns
    xy = df["coord"].str.extract(r"Point\(([-\d.]+) ([-\d.]+)\)")
    df["lon"] = pd.to_numeric(xy[0])
    df["lat"] = pd.to_numeric(xy[1])
    df = df.drop(columns=["coord"])

    # one INSEE code attached to several items
    dup_insee = df[df.duplicated("insee", keep=False)].sort_values("insee")
    # one item carrying several INSEE codes (old code + new code)
    dup_qid = df[df.duplicated("qid", keep=False)].sort_values("qid")

    out.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(out / "communes.csv", index=False)
    except PermissionError:
        print("communes.csv is locked (open in Excel?). Close it and rerun "
              "(data is read from the cache, so it is fast).")
        sys.exit(1)
    try:
        df.to_parquet(out / "communes.parquet", index=False)
    except Exception as e:
        print("Parquet not written:", e)
    dup_insee.to_csv(out / "communes_duplicates.csv", index=False)

    n_unique = df["insee"].nunique()
    extra_found = df[df["qid"].isin(EXTRA_QIDS)][["qid", "insee", "name"]]
    dept_key = df["insee"].str[:3].where(df["insee"].str[:2] == "97", df["insee"].str[:2])
    report = [
        f"Departments queried : {len(depts)} (failed: {failed or 'none'})",
        f"Raw rows (before keeping latest population): {raw_rows}",
        f"Communes (unique INSEE codes): {n_unique}",
        f"INSEE/DGCL reference (1 Jan 2026): {INSEE_REFERENCE_TOTAL}",
        f"Difference: {n_unique - INSEE_REFERENCE_TOTAL:+d}",
        f"Missing name: {df['name'].isna().sum()}",
        f"Missing population: {df['pop'].isna().sum()}",
        f"Missing coordinates: {df['lat'].isna().sum()}",
        f"INSEE codes shared by several items: {dup_insee['insee'].nunique()}",
        f"Items with several INSEE codes: {dup_qid['qid'].nunique()}",
        dup_qid[["qid", "insee", "name"]].to_string(index=False) if not dup_qid.empty else "  none",
        "Items added manually (EXTRA_QIDS, not typed 'commune of France'):",
        extra_found.to_string(index=False) if not extra_found.empty else "  none found",
        "Items excluded (EXCLUDE_INSEE, old INSEE codes):",
        excluded.to_string(index=False) if not excluded.empty else "  none",
        "Per-department counts:",
        df.groupby(dept_key).size().to_string(),
    ]
    (out / "communes_report.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report[:14]))


if __name__ == "__main__":
    main()