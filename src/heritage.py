"""Method 'heritage': PID links inherited from the previous sentence.

Rule D7 links a response only to the environments of its own sentence, so
"Le parc borde la Saône. On vient s'y promener." gives an action with no
environment: the place is in the previous sentence and the response refers to
it through a pronoun (y). Heritage keeps every span of the method it is applied
to (A-form by default) and changes one thing: a response (E, A, R) that has no
environment in its sentence inherits the environments of the previous sentence
when

    1. its sentence refers back to something named before:
       - a place pronoun or demonstrative: y (not "il y a", "y compris"),
         là / là-bas (not "de là", "là où"), celui-ci / celle-ci / ceux-ci /
         celles-ci, ce dernier / cette dernière / ces derniers / ces
         dernières, ce lieu, cet endroit, ce site, les lieux;
       - or a subject pronoun that opens the sentence: Il, Elle, Ils, Elles
         ("Elle est fréquentée par un million de visiteurs"), except the
         impersonal il (il est possible que, il s'agit, il faut, il existe…);
    2. the previous sentence is in the same section of the same article and
       has at least one environment.

Only the immediately previous sentence is used, and "en" is not a marker (it
is mostly the preposition). A subject pronoun may also stand for a person:
Heritage cannot tell, the hybrid method can. Inherited links are flagged
(`link = inherited`, `inherited = "N:parc;B:quai"`) so that they can be
counted apart: they go beyond rule D7 and the human coding does not make them.

Usage:
    python src/heritage.py --spans data/processed/spans_a_form.csv --sentences data/processed/sentences_500.parquet
        -> data/processed/spans_heritage.csv (default: next to the spans file)
"""
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

import keyword_coder as kc

MARKERS = re.compile(
    r"(?<![\w-])(?:y(?![\w'’-])|là(?:-bas)?(?![\w'’-])|(?:celui|celle|ceux|celles)-ci|"
    r"ce\s+dernier|cette\s+dernière|ces\s+derniers|ces\s+dernières|ce\s+lieu|cet\s+endroit|ce\s+site|les\s+lieux)"
    r"(?![\w-])", re.IGNORECASE)
SUBJECT_PRONOUN = re.compile(r"^[\s«“\"(]*(?:Il|Elle|Ils|Elles)(?=\s)")
NOT_MARKERS = re.compile(r"(?<!\w)(?:il\s+(?:n['’]\s*)?y\s+(?:a|avait|eut|aura|aurait|ait|avoir)(?!\w)"
                         r"|y\s+compris(?!\w)|de\s+là(?!\w)|par\s+là(?!\w)|là\s+où(?!\w))", re.IGNORECASE)
IMPERSONAL = re.compile(r"^[\s«“\"(]*Il\s+(?:(?:est|était|serait|sera|fut)\s+[\w-]+\s+(?:de|d['’]|que|qu['’])"
                        r"|(?:s['’]agi[ts]|faut|fallait|faudra|existe|existait|reste|restait|semble|semblait"
                        r"|paraît|pleut|neige|fait|faisait|convient|suffit|arrive)(?!\w))")


def refers_back(text: str) -> bool:
    """True when the sentence refers back to something named in the previous one."""
    hidden = NOT_MARKERS.sub(lambda m: " " * len(m.group()), text)
    if MARKERS.search(hidden):
        return True
    return bool(SUBJECT_PRONOUN.match(text)) and not IMPERSONAL.match(text) and bool(SUBJECT_PRONOUN.match(hidden))


def env_words(spans: pd.DataFrame) -> dict:
    """{code: [entries]} of the environment spans of one sentence."""
    out = {}
    for code, entry in zip(spans["code"], spans["entry"]):
        if code in kc.ENV_CODES:
            out.setdefault(code, []).append(entry)
    return out


def format_inherited(envs: dict) -> str:
    return ";".join(f"{c}:{','.join(envs[c])}" for c in kc.ENV_CODES if c in envs)


def parse_inherited(value) -> dict:
    """'N:parc,rive;B:quai' -> {'N': ['parc', 'rive'], 'B': ['quai']}."""
    if not isinstance(value, str) or not value:
        return {}
    out = {}
    for part in value.split(";"):
        code, _, words = part.partition(":")
        out[code] = [w for w in words.split(",") if w]
    return out


def inherit_links(spans: pd.DataFrame, sentences: pd.DataFrame) -> pd.DataFrame:
    """Spans of any method with inherited links added (see module docstring).

    sentences: sentence_id, text, and optionally insee, langue, index,
    section_titre (the previous sentence must be in the same section)."""
    spans = spans.copy()
    if "link" not in spans:
        spans["link"] = ["sentence" if c in kc.RESPONSE_CODES and str(p) not in ("0", "", "nan") else ""
                         for c, p in zip(spans["code"], spans["pid"])]
    if "inherited" not in spans:
        spans["inherited"] = ""
    sents = sentences.reset_index(drop=True)
    group_cols = [c for c in ("insee", "langue", "section_titre") if c in sents]
    previous = {}
    keys = list(zip(*(sents[c] for c in group_cols))) if group_cols else [()] * len(sents)
    for i in range(1, len(sents)):
        if keys[i] == keys[i - 1]:
            previous[sents.at[i, "sentence_id"]] = sents.at[i - 1, "sentence_id"]
    text = dict(zip(sents["sentence_id"], sents["text"]))
    by_sentence = {sid: g for sid, g in spans.groupby("sentence_id", sort=False)}

    for sid, g in by_sentence.items():
        responses = g.index[g["code"].isin(kc.RESPONSE_CODES)]
        if not len(responses) or env_words(g) or sid not in previous or not refers_back(text.get(sid, "")):
            continue
        prev = by_sentence.get(previous[sid])
        envs = env_words(prev) if prev is not None else {}
        if not envs:
            continue
        for i in responses:
            if str(spans.at[i, "pid"]) in ("0", "", "nan"):
                spans.at[i, "pid"] = ",".join(c for c in kc.ENV_CODES if c in envs)
                spans.at[i, "link"] = "inherited"
                spans.at[i, "inherited"] = format_inherited(envs)
    return spans


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spans", required=True, help="spans CSV written by keyword_coder.py or hybrid.py")
    ap.add_argument("--sentences", required=True, help="sentences parquet the spans come from")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    spans = pd.read_csv(args.spans, dtype={"pid": str})
    out_spans = inherit_links(spans, pd.read_parquet(args.sentences)).assign(method="heritage")
    out = Path(args.out or Path(args.spans).with_name("spans_heritage.csv"))
    out_spans.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{(out_spans['link'] == 'inherited').sum()} inherited links -> {out}")


if __name__ == "__main__":
    main()
