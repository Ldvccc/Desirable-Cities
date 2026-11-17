"""Get the Wikipedia article titles (fr, en) of the sampled communes.

Input : data/sample_500.csv            (output of make_sample.py)
Output: data/titles_500.csv            one row per existing article (insee, qid, langue, titre, url)
        docs/titles_coverage.csv       coverage per population class
        data/processed/titles_cache.json   cache of Wikidata answers (not versioned)

Source: Wikidata sitelinks (API wbgetentities, 50 items per request).
A commune without article in a language has NO row for that language
(see data/README.md).

Usage:
    python src/wikipedia_titles.py
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

INPUT = "data/sample_500.csv"
OUTPUT = "data/titles_500.csv"
COVERAGE_OUTPUT = "docs/titles_coverage.csv"
CACHE = "data/processed/titles_cache.json"

API = "https://www.wikidata.org/w/api.php"
HEADERS = {"User-Agent": "ludovic.blondeau@utbm.fr"}
LANGUAGES = ["fr", "en"]          # Wikipedia language codes; sitelink key = code + "wiki"
BATCH_SIZE = 50                   # API limit for anonymous requests
PAUSE = 1.0                       # seconds between requests


def load_sample(path: str) -> pd.DataFrame:
    """Read sample_500.csv. `insee` must stay text."""
    return pd.read_csv(path, dtype={"insee": str}, encoding="utf-8")


def load_cache(path: str) -> dict:
    """Return {qid: {"frwiki": title, ...}} or an empty dict."""
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_cache(cache: dict, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def parse_sitelinks(response: dict, qids: list, languages: list) -> dict:
    """Turn a wbgetentities answer into {qid: {"frwiki": title, ...}}.
    A requested qid absent from the answer, or without sitelinks, maps to {}."""
    wanted = {f"{lang}wiki" for lang in languages}
    out = {}
    entities = response.get("entities", {})
    for qid in qids:
        entity = entities.get(qid, {})
        links = entity.get("sitelinks", {}) if isinstance(entity, dict) else {}
        out[qid] = {site: links[site]["title"] for site in wanted if site in links}
    return out


def fetch_batch(qids: list, languages: list, retries: int = 4) -> dict:
    """Query Wikidata for one batch of qids. Returns {qid: sitelinks}.
    Raises RuntimeError after `retries` failed attempts."""
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "sitelinks",
        "sitefilter": "|".join(f"{lang}wiki" for lang in languages),
        "format": "json",
    }
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(API, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 200:
                data = r.json()
                if "error" not in data:
                    return parse_sitelinks(data, qids, languages)
                print(f"  API error: {data['error'].get('info')} (try {attempt})")
            else:
                print(f"  HTTP {r.status_code} (try {attempt}) {r.text[:150]}")
        except requests.RequestException as e:
            print(f"  {type(e).__name__} (try {attempt}) {e}")
        time.sleep(5 * attempt)
    raise RuntimeError(f"batch failed after {retries} tries: {qids[:3]}...")


def get_sitelinks(qids: list, languages: list, cache: dict, cache_path: str) -> dict:
    """Sitelinks for all qids, querying only those missing from the cache.
    The cache is saved after each batch, so an interrupted run can resume."""
    todo = [q for q in qids if q not in cache]
    print(f"{len(qids) - len(todo)} qids in cache, {len(todo)} to fetch")
    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        cache.update(fetch_batch(batch, languages))
        save_cache(cache, cache_path)
        print(f"  fetched {min(i + BATCH_SIZE, len(todo))}/{len(todo)}")
        time.sleep(PAUSE)
    return cache


def make_url(lang: str, title: str) -> str:
    """Article URL: spaces become underscores, the rest is percent-encoded."""
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='/:()_,-.')}"


def build_titles(sample: pd.DataFrame, sitelinks: dict, languages: list) -> pd.DataFrame:
    """One row per (commune, language) with an existing article.
    Columns: insee, qid, langue, titre, url."""
    rows = []
    for _, c in sample.iterrows():
        links = sitelinks.get(c["qid"], {})
        for lang in languages:
            title = links.get(f"{lang}wiki")
            if title:
                rows.append({"insee": c["insee"], "qid": c["qid"], "langue": lang,
                             "titre": title, "url": make_url(lang, title)})
    return pd.DataFrame(rows, columns=["insee", "qid", "langue", "titre", "url"])


def coverage(sample: pd.DataFrame, titles: pd.DataFrame, languages: list) -> pd.DataFrame:
    """Per population class: communes, with an article in each language, in all of them."""
    has = {lang: set(titles.loc[titles["langue"] == lang, "insee"]) for lang in languages}
    df = sample[["insee", "taille"]].copy()
    for lang in languages:
        df[lang] = df["insee"].isin(has[lang])
    df["all"] = df[languages].all(axis=1)
    order = sample.groupby("taille")["pop"].min().sort_values().index.tolist()  # small -> large
    out = df.groupby("taille", sort=False).agg(
        communes=("insee", "size"), **{lang: (lang, "sum") for lang in languages},
        all_languages=("all", "sum"),
    ).reindex(order)
    out.loc["TOTAL"] = out.sum()
    return out.astype(int)


def check_titles(titles: pd.DataFrame, sample: pd.DataFrame) -> None:
    """Raise an AssertionError when a sanity check fails."""
    assert not titles.duplicated(["insee", "langue"]).any(), "duplicate (insee, langue)"
    assert set(titles["insee"]) <= set(sample["insee"]), "unknown insee in titles"
    assert titles["titre"].notna().all() and (titles["titre"] != "").all(), "empty title"


def save_titles(titles: pd.DataFrame, path: str) -> None:
    """Write the CSV sorted by (insee, langue) so two runs give the same file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    titles.sort_values(["insee", "langue"]).to_csv(path, index=False, encoding="utf-8")


def main() -> None:
    sample = load_sample(INPUT)
    cache = load_cache(CACHE)
    try:
        sitelinks = get_sitelinks(sample["qid"].tolist(), LANGUAGES, cache, CACHE)
    except RuntimeError as e:
        print("Stopped:", e, "\nRerun the script: the cache keeps what was already fetched.")
        sys.exit(1)

    titles = build_titles(sample, sitelinks, LANGUAGES)
    check_titles(titles, sample)
    save_titles(titles, OUTPUT)

    cov = coverage(sample, titles, LANGUAGES)
    Path(COVERAGE_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    cov.to_csv(COVERAGE_OUTPUT)
    print(f"\n{len(titles)} articles for {len(sample)} communes")
    print(cov)
    print(f"\nSaved {OUTPUT} and {COVERAGE_OUTPUT}")


if __name__ == "__main__":
    main()