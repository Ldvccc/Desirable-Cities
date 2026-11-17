"""Split the articles of the corpus into sentences (the unit of annotation).

Input : data/processed/corpus_500.parquet      (output of wikipedia_text.py)
Output: data/processed/sentences_500.parquet   one row per sentence
        docs/sentences_stats.csv               sentences per language and section type

Columns of the output (names follow schema/annotation_schema_v1.json):
    sentence_id    <insee>-<langue>-<revision_id>-s<index>
    insee, langue, revision_id
    index          position of the sentence in the article (0-based)
    section_titre  title of the section the sentence comes from ('' = introduction)
    section_type   common section type (intro, history, geography, heritage...)
    text           the sentence
    n_mots         number of words

Rules:
- Headings are not sentences. Sections typed 'skip' (references, external
  links, see also...) are left out.
- Each line of the article (paragraph or list item) is split separately, so a
  list item without final full stop is one "sentence".
- A sentence ends at . ! ? or ... followed by a space and an upper-case letter
  or a digit, except after an abbreviation (av. J.-C., M., St., p. 12...), an
  initial (J. Dupont) or inside an open quotation or bracket.
- Rule-based and deterministic: the same text always gives the same sentences.
  Tuned for French and English; other languages use the generic rules.

Usage:
    python src/split_sentences.py
    python src/split_sentences.py --corpus data/processed/corpus_only.parquet
    python src/split_sentences.py --csv      # also write a CSV (readable in VS Code / Excel)
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

from wikipedia_text import parse_sections

CORPUS = "data/processed/corpus_500.parquet"
STATS_OUTPUT = "docs/sentences_stats.csv"

# Abbreviations after which a full stop never ends the sentence (lower case,
# without the final full stop).
ABBREVIATIONS = {
    "fr": {"av", "apr", "m", "mm", "mme", "mmes", "mlle", "mlles", "dr", "pr", "me", "mgr", "st", "ste",
           "sts", "cf", "env", "hab", "vol", "fig", "ex", "art", "chap", "éd", "ed", "coll", "dir", "op",
           "cit", "ibid", "id", "réf", "ref", "tél", "bd", "boul", "cie", "sté", "dép", "arr", "alt",
           "janv", "févr", "fév", "avr", "juill", "sept", "oct", "nov", "déc", "c.-à-d", "ch.-l", "vs"},
    "en": {"mr", "mrs", "ms", "dr", "prof", "st", "mt", "ft", "vs", "approx", "ca", "cf", "vol", "fig",
           "ed", "eds", "est", "gen", "col", "lt", "capt", "sgt", "rev", "hon", "gov", "dept", "univ",
           "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "viz"},
}
GENERIC_ABBREVIATIONS = {"dr", "st", "prof", "cf", "vol", "fig", "ca", "vs", "nr", "bzw", "sr", "sra"}
# Abbreviations only when a number follows: "p. 12", "n. 5", "v. 1150", "No. 3".
NUMERIC_ABBREVIATIONS = {"p", "pp", "n", "no", "nos", "nr", "c", "v", "t", "s", "art", "ch", "env"}
# Era markers: dotted, but they often end a sentence ("... en 43 av. J.-C. La ville ...").
ERA_MARKERS = {"j.-c", "b.c", "a.d", "b.c.e", "c.e"}

BOUNDARY = re.compile(r"([.!?…]+)([»”\"')\]]*)\s+")
TOKEN_BEFORE = re.compile(r"[^\s(\[«“\"']+$")
DOTTED_ACRONYM = re.compile(r"(?:[^\W\d_]{1,3}\.)+[^\W\d_]{1,3}")     # r.n, u.s, m.h, e.g
OPENERS = "«“\"'([¿¡—–-"
CJK_BOUNDARY = re.compile(r"(?<=[。！？!?])")
MAX_OPEN = 600      # beyond this length, an unclosed quote or bracket no longer blocks a split


def starts_sentence(following: str) -> bool:
    """True when the text after a candidate boundary can start a sentence."""
    stripped = following.lstrip(OPENERS + " ")
    return bool(stripped) and (stripped[0].isupper() or stripped[0].isdigit())


def is_abbreviation(token: str, following: str, langue: str) -> bool:
    """True when the full stop after `token` does not end the sentence."""
    low = token.lower()
    if low in ERA_MARKERS:
        return False
    if len(token) == 1 and token.isalpha() and token.isupper():
        return True                                   # initial: "J. Dupont"
    if DOTTED_ACRONYM.fullmatch(low):
        return True                                   # dotted acronym: "R.N. 7", "U.S. Army"
    if low in ABBREVIATIONS.get(langue, GENERIC_ABBREVIATIONS):
        return True
    if low in NUMERIC_ABBREVIATIONS:
        return bool(re.match(r"\d|[IVXLC]+(?=[\s.,;)]|$)", following.lstrip(OPENERS + " ")))
    return False


def is_open(segment: str) -> bool:
    """True when a quotation or a bracket is still open at the end of `segment`."""
    if len(segment) > MAX_OPEN:
        return False
    return (segment.count("«") > segment.count("»")
            or segment.count("“") > segment.count("”")
            or segment.count("(") > segment.count(")")
            or segment.count('"') % 2 == 1)


def split_paragraph(text: str, langue: str) -> list:
    """Split one paragraph (no line break) into sentences."""
    text = text.strip()
    if not text:
        return []
    if langue in ("zh", "ja"):
        return [s.strip() for s in CJK_BOUNDARY.split(text) if s.strip()]
    sentences, start = [], 0
    for m in BOUNDARY.finditer(text):
        if m.start() < start:
            continue
        following = text[m.end():]
        if not starts_sentence(following):
            continue
        if m.group(1) == ".":
            token = TOKEN_BEFORE.search(text[start:m.start(1)])
            if token and is_abbreviation(token.group(0), following, langue):
                continue
        segment = text[start:m.end(2)]
        if is_open(segment):
            continue
        sentences.append(segment.strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def split_text(text: str, langue: str) -> list:
    """Split a section into sentences, line by line. Lines without any letter
    (separators, isolated numbers) are dropped."""
    out = []
    for line in text.split("\n"):
        for sentence in split_paragraph(line, langue):
            if any(c.isalpha() for c in sentence):
                out.append(sentence)
    return out


def article_sentences(article) -> list:
    """Sentence rows of one corpus row (see the module docstring)."""
    rows = []
    for section in parse_sections(article["texte"], article["langue"]):
        if section["type"] == "skip":
            continue
        for sentence in split_text(section["texte"], article["langue"]):
            index = len(rows)
            rows.append({
                "sentence_id": f"{article['insee']}-{article['langue']}-{int(article['revision_id'])}-s{index}",
                "insee": article["insee"], "langue": article["langue"],
                "revision_id": int(article["revision_id"]), "index": index,
                "section_titre": section["titre"], "section_type": section["type"],
                "text": sentence, "n_mots": len(sentence.split()),
            })
    return rows


def build_sentences(corpus: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, article in corpus.iterrows():
        rows.extend(article_sentences(article))
    return pd.DataFrame(rows, columns=["sentence_id", "insee", "langue", "revision_id", "index",
                                       "section_titre", "section_type", "text", "n_mots"])


def check_sentences(sentences: pd.DataFrame, corpus: pd.DataFrame) -> None:
    """Raise an AssertionError when a sanity check fails."""
    assert sentences["sentence_id"].is_unique, "duplicate sentence_id"
    assert sentences["sentence_id"].str.fullmatch(r"[0-9AB]{5}-[a-z]{2,3}-[0-9]+-s[0-9]+").all(), \
        "sentence_id does not follow the annotation schema"
    assert (sentences["text"].str.strip() != "").all(), "empty sentence"
    assert "skip" not in set(sentences["section_type"]), "sentence from a skipped section"
    assert set(zip(sentences["insee"], sentences["langue"])) <= set(zip(corpus["insee"], corpus["langue"])), \
        "sentence without article"


def stats(sentences: pd.DataFrame) -> pd.DataFrame:
    """Per language and section type: sentences, share of the language, median words."""
    out = sentences.groupby(["langue", "section_type"]).agg(
        phrases=("sentence_id", "size"), mots_medians=("n_mots", "median")).reset_index()
    out["part_pct"] = (100 * out["phrases"] / out.groupby("langue")["phrases"].transform("sum")).round(1)
    out["mots_medians"] = out["mots_medians"].astype(int)
    return out.sort_values(["langue", "phrases"], ascending=[True, False]).reset_index(drop=True)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")       # Windows console: never crash on a character
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--out", default=None, help="default: corpus path with 'corpus' -> 'sentences'")
    ap.add_argument("--csv", action="store_true", help="also write a CSV next to the Parquet file")
    args = ap.parse_args()

    if not Path(args.corpus).exists():
        sys.exit(f"{args.corpus} not found: run src/wikipedia_text.py first.")
    out = args.out or str(Path(args.corpus).with_name(Path(args.corpus).name.replace("corpus", "sentences")))
    if Path(out) == Path(args.corpus):
        sys.exit("Output path equals the corpus path: give --out.")

    corpus = pd.read_parquet(args.corpus)
    sentences = build_sentences(corpus)
    check_sentences(sentences, corpus)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sentences.to_parquet(out, index=False)
    print(f"{len(sentences)} sentences from {len(corpus)} articles saved to {out}")
    if args.csv:
        csv_path = str(Path(out).with_suffix(".csv"))
        sentences.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"CSV copy: {csv_path}")

    per_article = sentences.groupby(["insee", "langue"]).size()
    print(f"Sentences per article: median {int(per_article.median())}, max {int(per_article.max())}")
    table = stats(sentences)
    print(table.to_string(index=False))
    if args.corpus == CORPUS:
        Path(STATS_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(STATS_OUTPUT, index=False)
        print(f"Saved {STATS_OUTPUT}")


if __name__ == "__main__":
    main()
