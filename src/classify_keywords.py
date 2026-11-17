"""Algorithm A: naive keyword classifier (the baseline to beat).

For each sentence, look for the terms of schema/lexicon_v0.yaml and tick every
category that has at least one match. Deliberately naive:
- exact match of the lexicon term, case-insensitive, whole words only, with an
  optional plural s/x; no lemmatisation, no context, no disambiguation
  ("a été" matches the season "été", "Arbonne-la-Forêt" matches "forêt");
- French terms for French sentences, the English term for English sentences;
- PID cells = every environment x every response found in the sentence;
- register = imaginary or spectacle when one of their markers appears, else
  descriptive; never uncertain.

Input : data/processed/sentences_500.parquet   (output of split_sentences.py)
Output: data/processed/annotations_keywords_500.json   annotation records (schema v1)
        data/processed/annotations_keywords_500.csv    same, one readable line per sentence

Usage:
    python src/classify_keywords.py
    python src/classify_keywords.py --sentences data/processed/sentences_only.parquet
    python src/classify_keywords.py --insee 77186 77037      # only some communes
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import schema_utils as su

SENTENCES = "data/processed/sentences_500.parquet"
METHOD_ID = "lexicon_naive"
PID_ROWS = su.ENVIRONMENTS
PID_COLS = su.RESPONSES + ("none",)


def term_pattern(term: str) -> re.Pattern:
    """Whole-word, case-insensitive pattern of a term, optional plural s/x.
    Spaces match any run of spaces; ' matches both ' and ’."""
    words = [re.escape(w) for w in term.strip().split()]
    body = r"\s+".join(words).replace("'", "['’]")
    return re.compile(rf"(?<!\w){body}(?:s|x)?(?!\w)", re.IGNORECASE)


def english_forms(en: str) -> list:
    """'square/plaza' -> ['square', 'plaza']; 'stars-full' stays as is."""
    return [f.strip() for f in en.split("/") if f.strip()]


def build_matchers(lexicon: dict) -> dict:
    """{langue: [(pattern, category, tag)]} for the categories, and the facets.
    Longer terms first, so that the evidence is the most specific match."""
    by_lang = {"fr": [], "en": []}
    for t in su.iter_terms(lexicon):
        for form in t["fr"]:
            by_lang["fr"].append((form, t["category"], t["tag"]))
        for form in english_forms(t["en"]):
            by_lang["en"].append((form, t["category"], t["tag"]))
    matchers = {lang: [(term_pattern(f), c, tag) for f, c, tag in sorted(items, key=lambda x: -len(x[0]))]
                for lang, items in by_lang.items()}

    spaces = {"fr": [], "en": []}
    for st in lexicon["facets"]["public_space_types"]["types"]:
        for form in st["fr"]:
            spaces["fr"].append((form, st["id"]))
        for form in [st["en"]] + st.get("koinos", []):
            for f in english_forms(form):
                spaces["en"].append((f, st["id"]))
    space_matchers = {lang: [(term_pattern(f), sid) for f, sid in sorted(items, key=lambda x: -len(x[0]))]
                      for lang, items in spaces.items()}

    register = [(term_pattern(f), v["id"]) for v in lexicon["facets"]["register"]["values"]
                for f in v.get("fr", [])]
    return {"terms": matchers, "spaces": space_matchers, "register": register}


def classify_sentence(text: str, langue: str, matchers: dict) -> dict:
    """Labels of one sentence: {environments, responses, pid_cells,
    public_space_types, register}, in the format of the annotation schema."""
    found = {}                                     # category -> {"evidence": str, "tags": [..]}
    for pattern, category, tag in matchers["terms"].get(langue, []):
        m = pattern.search(text)
        if not m:
            continue
        label = found.setdefault(category, {"category": category, "evidence": m.group(0), "tags": []})
        if tag not in label["tags"]:
            label["tags"].append(tag)

    environments = [found[c] for c in su.ENVIRONMENTS if c in found]
    responses = [found[c] for c in su.RESPONSES if c in found]
    cells = [{"environment": e["category"], "response": r["category"]}
             for e in environments for r in responses]
    spaces = []
    for pattern, sid in matchers["spaces"].get(langue, []):
        if sid not in spaces and pattern.search(text):
            spaces.append(sid)
    register = "descriptive"
    if langue == "fr":
        for pattern, value in matchers["register"]:
            if pattern.search(text):
                register = value
                break
    return {"environments": environments, "responses": responses, "pid_cells": cells,
            "public_space_types": sorted(spaces), "register": register}


def annotate(sentences: pd.DataFrame, lexicon: dict, today: str = None) -> list:
    """One schema-v1 record per sentence."""
    matchers = build_matchers(lexicon)
    annotator = {"kind": "keywords", "id": METHOD_ID, "lexicon_version": str(lexicon["version"]),
                 "date": today or date.today().isoformat()}
    records = []
    for _, s in sentences.iterrows():
        labels = classify_sentence(s["text"], s["langue"], matchers)
        records.append({
            "schema_version": "1.0.0", "sentence_id": s["sentence_id"], "insee": s["insee"],
            "langue": s["langue"], "revision_id": int(s["revision_id"]),
            "section_type": s["section_type"], "text": s["text"], **labels,
            "uncertain": False, "annotator": dict(annotator),
        })
    return records


def flat_table(records: list) -> pd.DataFrame:
    """One readable row per sentence (for VS Code or Excel)."""
    return pd.DataFrame([{
        "sentence_id": r["sentence_id"], "langue": r["langue"], "section_type": r["section_type"],
        "text": r["text"],
        "environments": ", ".join(e["category"] for e in r["environments"]),
        "responses": ", ".join(x["category"] for x in r["responses"]),
        "pid_cells": ", ".join(f"{c['environment']}x{c['response']}" for c in r["pid_cells"]),
        "evidence": " | ".join(f"{x['category']}: {x['evidence']}" for x in r["environments"] + r["responses"]),
        "public_space_types": ", ".join(r["public_space_types"]),
        "register": r["register"],
    } for r in records])


def pid_matrix(records: list) -> pd.DataFrame:
    """Share of sentences (%) per environment x response; column 'none' =
    sentences with this environment and no response."""
    counts = pd.DataFrame(0, index=list(PID_ROWS), columns=list(PID_COLS))
    for r in records:
        for c in r["pid_cells"]:
            counts.loc[c["environment"], c["response"]] += 1
        if not r["responses"]:
            for e in r["environments"]:
                counts.loc[e["category"], "none"] += 1
    return (100 * counts / max(len(records), 1)).round(1)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sentences", default=SENTENCES)
    ap.add_argument("--insee", nargs="*", help="restrict to these INSEE codes")
    ap.add_argument("--out", default=None, help="default: next to the sentences file")
    args = ap.parse_args()

    if not Path(args.sentences).exists():
        sys.exit(f"{args.sentences} not found: run src/split_sentences.py first.")
    sentences = pd.read_parquet(args.sentences)
    if args.insee:
        sentences = sentences[sentences["insee"].isin(args.insee)]
        if sentences.empty:
            sys.exit(f"No sentence for {args.insee} in {args.sentences}.")
    out = Path(args.out or Path(args.sentences).with_name(
        Path(args.sentences).stem.replace("sentences", "annotations_keywords") + ".json"))

    lexicon = su.load_lexicon()
    records = annotate(sentences, lexicon)
    report = su.validate_records(records, lexicon=lexicon)
    if report:
        first = next(iter(report.items()))
        sys.exit(f"{len(report)} records do not follow the schema, e.g. {first}")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    flat_table(records).to_csv(out.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    print(f"{len(records)} sentences annotated -> {out} (+ .csv)")

    n = len(records)
    for cat in su.ENVIRONMENTS + su.RESPONSES:
        k = sum(any(x["category"] == cat for x in r["environments"] + r["responses"]) for r in records)
        print(f"  {cat:<14} {k:>6} sentences ({100 * k / n:.0f} %)")
    nothing = sum(not r["environments"] and not r["responses"] for r in records)
    print(f"  {'no label':<14} {nothing:>6} sentences ({100 * nothing / n:.0f} %)")
    for (insee, langue), group in pd.DataFrame(records).groupby(["insee", "langue"]):
        print(f"\nPID matrix, {insee} {langue} ({len(group)} sentences, % of sentences):")
        print(pid_matrix(group.to_dict("records")).to_string())


if __name__ == "__main__":
    main()
