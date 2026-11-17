"""Download the plain text of the Wikipedia articles and build the corpus.

Input : data/titles_500.csv    one row per article (insee, qid, langue, titre, url)
        data/sample_500.csv    commune metadata (pop, lat, lon, taille)
Output: data/processed/corpus_500.parquet   one row per (insee, langue), see data/README.md
        docs/corpus_coverage.csv            articles and lengths per size class and language
        data/processed/wikipedia_cache/<langue>/<insee>.json   raw answers (not versioned)

Source: MediaWiki API of each language edition, TextExtracts (prop=extracts,
explaintext): plain text without wiki markup, references, tables or infobox;
section titles are kept as "== Title ==" lines. One request per article.

Usage:
    python src/wikipedia_text.py                      # whole sample (about 1,000 requests)
    python src/wikipedia_text.py --only 77186 75056   # a few communes (test run)
    python src/wikipedia_text.py --langs fr           # one language only
    python src/wikipedia_text.py --refresh            # ignore the cache, download again

The cache is written after each article: an interrupted run resumes where it
stopped. Behind a proxy or VPN, set the HTTPS_PROXY environment variable.
Optional: set WIKI_CONTACT (e-mail or URL) to identify yourself to Wikimedia.
"""
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
import requests

TITLES = "data/titles_500.csv"
COMMUNES = "data/sample_500.csv"
OUTPUT = "data/processed/corpus_500.parquet"
OUTPUT_ONLY = "data/processed/corpus_only.parquet"     # used with --only
CACHE_DIR = "data/processed/wikipedia_cache"
COVERAGE_OUTPUT = "docs/corpus_coverage.csv"

API = "https://{lang}.wikipedia.org/w/api.php"
PAUSE = 0.5            # seconds between requests
STUB_LENGTH = 500      # articles shorter than this are counted as stubs

HEADING = re.compile(r"^(={2,6})[ \t]*(.+?)[ \t]*\1[ \t]*$", re.MULTILINE)

# Section types shared across languages (same list as `section_type` in
# schema/annotation_schema_v1.json), plus "skip" for sections that are not
# article content (references, external links...). Patterns are matched on the
# title in lower case without accents; the FIRST matching rule wins, so the
# order matters. A subsection without match inherits the type of its parent.
SECTION_RULES = {
    "fr": [
        ("skip", r"notes et references|^references?$|^notes$|voir aussi|liens? externes?|bibliographie"
                 r"|^annexes?$|articles? connexes?|^sources?$|pour approfondir"),
        ("other", r"^population et societe$"),
        ("culture", r"^culture locale et patrimoine$|^culture et patrimoine$"),
        ("personalities", r"personnalite|personnages"),
        ("geography", r"patrimoine naturel|espaces? naturels?|milieux naturels"),
        ("heritage", r"patrimoine|monuments?|lieux et|edifices?|architecture"),
        ("transport", r"transports?|voies de communication|voies|desserte|ferroviaire|routi|mobilite"),
        ("education", r"enseignement|education|ecoles?|scolaire"),
        ("sport", r"sports?|sporti"),
        ("demography", r"demographie|population|pyramide des ages"),
        ("politics", r"politique|administrati|municipal|maires?|intercommunalite|jumelage|elections?"
                     r"|electoral|rattachements|finances|instances|canton"),
        ("economy", r"economie|emploi|entreprises|commerces?|agriculture|industrie|tourisme|revenus|activites"),
        ("culture", r"culture|manifestations|festivites|fetes|gastronomie|heraldique|blason|devise|cultes?"
                    r"|langues?|traditions?|evenements|associati|medias|logotype|cinema|litterature|musique"),
        ("history", r"histoire|prehistoire|moyen age|epoque|antiquite|revolution|guerre|siecle|ancien regime"
                    r"|chronologie"),
        ("geography", r"geographie|localisation|situation|climat|hydrographie|relief|geologie|environnement"
                      r"|communes limitrophes|paysages?|topographie|cours d'eau|risques"),
    ],
    "en": [
        ("skip", r"^references?$|external links?|see also|^notes$|further reading|bibliography|^sources?$"
                 r"|citations|footnotes|^gallery$"),
        ("personalities", r"people|personalities|residents|notable"),
        ("heritage", r"sights?|landmarks?|monuments?|heritage|architecture|places of interest|buildings"),
        ("transport", r"transport|transportation|roads?|railways?"),
        ("education", r"education|schools?"),
        ("sport", r"sports?"),
        ("demography", r"demograph|population"),
        ("politics", r"administration|politics|government|twin towns|sister cities|international relations"
                     r"|mayors?|elections?"),
        ("economy", r"economy|tourism|industry|agriculture"),
        ("culture", r"culture|events|festivals?|cuisine|gastronomy|heraldry|coat of arms|religion|language"
                    r"|traditions?|media|arts\b"),
        ("history", r"history|prehistory|middle ages|antiquity|revolution|wars?\b|century|etymology"),
        ("geography", r"geography|climate|location|geology|environment|hydrography|topography"),
    ],
}


def normalise_title(title: str) -> str:
    """Lower case, accents removed: 'Démographie' -> 'demographie'."""
    text = unicodedata.normalize("NFD", title.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn").strip()


def classify_section(title: str, langue: str):
    """Type of a section from its own title, or None when no rule matches
    (unknown language included)."""
    norm = normalise_title(title)
    for section_type, pattern in SECTION_RULES.get(langue, []):
        if re.search(rf"(?:^|\b)(?:{pattern})", norm):
            return section_type
    return None


def clean_text(text: str) -> str:
    """Normalise spaces and blank lines. Typographic spaces (non-breaking,
    thin) become plain spaces so that sentences can be matched and quoted."""
    text = re.sub(r"[     ]", " ", text)
    text = text.replace("​", "").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_sections(texte: str, langue: str) -> list:
    """Split an extract into sections.

    Returns a list of dicts {titre, niveau, type, texte}. The text before the
    first heading is the section 'intro' (titre '', niveau 1). A subsection
    without its own match inherits the type of its nearest parent; everything
    under a 'skip' section is 'skip'; no match at all gives 'other'."""
    sections = []
    matches = list(HEADING.finditer(texte))
    first = matches[0].start() if matches else len(texte)
    sections.append({"titre": "", "niveau": 1, "type": "intro", "texte": texte[:first].strip()})

    parents = {}                                    # niveau -> type of the open section
    for i, m in enumerate(matches):
        niveau = len(m.group(1))
        titre = m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(texte)
        parents = {n: t for n, t in parents.items() if n < niveau}
        inherited = parents[max(parents)] if parents else None
        own = classify_section(titre, langue)
        if inherited == "skip":
            section_type = "skip"
        else:
            section_type = own or inherited or "other"
        parents[niveau] = section_type
        sections.append({"titre": titre, "niveau": niveau, "type": section_type,
                         "texte": texte[m.end():end].strip()})
    return sections


def user_agent() -> str:
    contact = os.environ.get("WIKI_CONTACT", "https://github.com/Ldvccc/Desirable-Cities")
    return f"DesirableCities-EG01/0.1 ({contact}) python-requests"


def parse_api_response(data: dict, requested_title: str) -> dict:
    """Turn the JSON answer of the API (formatversion=2) into a cache record.
    A missing page gives missing=True and no text."""
    pages = data.get("query", {}).get("pages", [])
    page = pages[0] if pages else {"missing": True}
    record = {"titre_demande": requested_title, "titre": page.get("title", requested_title),
              "missing": bool(page.get("missing") or page.get("invalid")),
              "revision_id": None, "revision_date": None, "texte": None}
    if not record["missing"]:
        revisions = page.get("revisions") or [{}]
        record["revision_id"] = revisions[0].get("revid")
        record["revision_date"] = revisions[0].get("timestamp")
        record["texte"] = page.get("extract", "")
    return record


def fetch_page(langue: str, title: str, session, retries: int = 5) -> dict:
    """Download one article. Raises RuntimeError after `retries` failed attempts."""
    params = {
        "action": "query", "format": "json", "formatversion": 2,
        "prop": "extracts|revisions", "titles": title, "redirects": 1,
        "explaintext": 1, "exsectionformat": "wiki",
        "rvprop": "ids|timestamp", "maxlag": 5,
    }
    for attempt in range(1, retries + 1):
        wait = 5 * attempt
        try:
            r = session.get(API.format(lang=langue), params=params,
                            headers={"User-Agent": user_agent()}, timeout=60)
            if r.status_code == 200:
                data = r.json()
                if "error" not in data:
                    return parse_api_response(data, title)
                print(f"  API error: {data['error'].get('code')} (try {attempt})")
            else:
                print(f"  HTTP {r.status_code} (try {attempt}) {r.text[:120]}")
            wait = max(wait, int(r.headers.get("Retry-After", 0) or 0))
        except (requests.RequestException, ValueError) as e:
            print(f"  {type(e).__name__} (try {attempt}) {str(e)[:150]}")
        time.sleep(wait)
    raise RuntimeError(f"{langue}:{title} failed after {retries} tries")


def cache_path(cache_dir: str, langue: str, insee: str) -> Path:
    return Path(cache_dir) / langue / f"{insee}.json"


def get_page(row, session, cache_dir: str, refresh: bool = False):
    """Cached download of one article. Returns (record, downloaded)."""
    path = cache_path(cache_dir, row["langue"], row["insee"])
    if path.exists() and not refresh:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("titre_demande") == row["titre"]:
            return record, False
    record = fetch_page(row["langue"], row["titre"], session)
    record["date_extraction"] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return record, True


def build_row(title_row, record: dict, commune) -> dict:
    """One corpus row (see data/README.md). `commune` is the metadata row of
    the commune, or None when it is unknown."""
    texte = clean_text(record["texte"] or "")
    sections = [{"titre": s["titre"], "niveau": s["niveau"], "type": s["type"]}
                for s in parse_sections(texte, title_row["langue"])]

    def meta(key):
        return None if commune is None or pd.isna(commune[key]) else commune[key]

    pop = meta("pop")
    return {
        "insee": title_row["insee"], "qid": title_row["qid"], "langue": title_row["langue"],
        "titre": record["titre"], "url": title_row["url"],
        "texte": texte, "sections": sections, "longueur": len(texte),
        "population": None if pop is None else int(pop),
        "lat": meta("lat"), "lon": meta("lon"),
        "revision_id": record["revision_id"], "revision_date": record["revision_date"],
        "date_extraction": record.get("date_extraction"),
    }


def build_corpus(titles: pd.DataFrame, communes: pd.DataFrame, records: dict) -> pd.DataFrame:
    """Corpus table from the downloaded records {(insee, langue): record}.
    Missing articles give no row."""
    by_insee = communes.set_index("insee")
    rows = []
    for _, t in titles.iterrows():
        record = records.get((t["insee"], t["langue"]))
        if record is None or record["missing"]:
            continue
        commune = by_insee.loc[t["insee"]] if t["insee"] in by_insee.index else None
        rows.append(build_row(t, record, commune))
    corpus = pd.DataFrame(rows)
    if not corpus.empty:
        corpus["population"] = corpus["population"].astype("Int64")
        corpus["revision_id"] = corpus["revision_id"].astype("Int64")
        corpus = corpus.sort_values(["insee", "langue"]).reset_index(drop=True)
    return corpus


def check_corpus(corpus: pd.DataFrame, titles: pd.DataFrame) -> None:
    """Raise an AssertionError when a sanity check fails."""
    assert not corpus.duplicated(["insee", "langue"]).any(), "duplicate (insee, langue)"
    assert set(zip(corpus["insee"], corpus["langue"])) <= set(zip(titles["insee"], titles["langue"])), \
        "row without title"
    assert corpus["revision_id"].notna().all(), "article without revision_id"
    assert (corpus["longueur"] == corpus["texte"].str.len()).all(), "wrong longueur"


def coverage(corpus: pd.DataFrame, communes: pd.DataFrame) -> pd.DataFrame:
    """Per size class and language: number of articles, stubs, median length."""
    df = corpus.merge(communes[["insee", "taille", "pop"]], on="insee", how="left")
    df["stub"] = df["longueur"] < STUB_LENGTH
    df["n_sections"] = df["sections"].apply(len) - 1          # without the intro
    order = communes.groupby("taille")["pop"].min().sort_values().index.tolist()   # small -> large
    out = df.groupby(["taille", "langue"]).agg(
        articles=("insee", "size"), stubs=("stub", "sum"),
        longueur_mediane=("longueur", "median"), sections_medianes=("n_sections", "median"),
    ).reset_index()
    out["taille"] = pd.Categorical(out["taille"], categories=order, ordered=True)
    out = out.sort_values(["taille", "langue"]).reset_index(drop=True)
    return out.astype({"stubs": int, "longueur_mediane": int, "sections_medianes": int})


def main() -> None:
    sys.stdout.reconfigure(errors="replace")       # Windows console: never crash on a character
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--titles", default=TITLES)
    ap.add_argument("--communes", default=COMMUNES)
    ap.add_argument("--out", default=None, help=f"default: {OUTPUT}")
    ap.add_argument("--only", nargs="*", help="restrict to these INSEE codes (test run)")
    ap.add_argument("--langs", nargs="*", help="restrict to these languages")
    ap.add_argument("--refresh", action="store_true", help="download again, ignore the cache")
    args = ap.parse_args()

    titles = pd.read_csv(args.titles, dtype=str, encoding="utf-8")
    communes = pd.read_csv(args.communes, dtype={"insee": str}, encoding="utf-8")
    if args.only:
        unknown = set(args.only) - set(titles["insee"])
        if unknown:
            sys.exit(f"INSEE codes not in {args.titles}: {sorted(unknown)}")
        titles = titles[titles["insee"].isin(args.only)]
    if args.langs:
        titles = titles[titles["langue"].isin(args.langs)]
    out = args.out or (OUTPUT_ONLY if args.only else OUTPUT)

    print(f"{len(titles)} articles to get ({titles['insee'].nunique()} communes, "
          f"languages: {sorted(titles['langue'].unique())})")
    session = requests.Session()
    records, failed, downloaded = {}, [], 0
    for n, (_, t) in enumerate(titles.iterrows(), start=1):
        try:
            record, fresh = get_page(t, session, CACHE_DIR, args.refresh)
        except RuntimeError as e:
            print("  FAILED:", e)
            failed.append((t["insee"], t["langue"]))
            if len(failed) >= 5 and downloaded == 0:
                sys.exit("Stopped: nothing could be downloaded. Check the internet access to "
                         "wikipedia.org (VPN, HTTPS_PROXY) and run again.")
            continue
        records[(t["insee"], t["langue"])] = record
        if fresh:
            downloaded += 1
            time.sleep(PAUSE)
        if n % 25 == 0 or n == len(titles):
            print(f"  {n}/{len(titles)} ({downloaded} downloaded, {n - downloaded - len(failed)} from cache)")

    corpus = build_corpus(titles, communes, records)
    if corpus.empty:
        sys.exit("No article retrieved.")
    check_corpus(corpus, titles)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    corpus.to_parquet(out, index=False)

    missing = sum(1 for r in records.values() if r["missing"])
    print(f"\n{len(corpus)} articles saved to {out} "
          f"(missing on Wikipedia: {missing}, failed downloads: {len(failed)})")
    cov = coverage(corpus, communes)
    print(cov.to_string(index=False))
    if not args.only and not args.langs:
        Path(COVERAGE_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
        cov.to_csv(COVERAGE_OUTPUT, index=False)
        print(f"Saved {COVERAGE_OUTPUT}")
    if failed:
        print(f"\n{len(failed)} downloads failed: run the script again, the cache keeps the rest.")
        sys.exit(1)


if __name__ == "__main__":
    main()
