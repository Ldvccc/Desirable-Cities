"""Span-level keyword coding with keyword list v3 (algorithms A, A+ and A-form).

Each occurrence of a list word in a sentence becomes one span with one code
(N, C, B, E, A, R), as in the manual coding (docs/rules_manual_coding_v2.md).
Three methods, from the most naive to the closest to the rules:

    a       Koinos tags only (src K). Exact list term, case-insensitive, whole
            word, optional plural s/x. No rule applied (paper §5.3, "A").
    a_plus  Same matcher on the full list v3 (paper §5.3, "A+").
    a_form  Full list + the rules for manual coding v2:
              I1 forms   plural, feminine, conjugated verbs and words built on
                         the same stem (the `forms` of the list encoding)
              I3 span    longest list expression wins, no overlap
              I4         homonyms and fixed expressions (`exclude`, "été" as
                         a participle, possessive "son", reflexive verbs)
              I5         a capitalised word inside a sentence, or a word
                         hyphenated to a capitalised one, is a proper name
              I6         every value in °C is coded N
              I8         every occurrence is coded
              D1/D2      context of calme, voitures, trains, vélos,
                         restaurants, bars, marchés; montagne is N
              D7         PID link of E, A, R = environments of the sentence
            Rule D4/D6 (people really feel, act or think) is not checked:
            E, A and R spans follow the form test only.

Input : a sentences table (output of split_sentences.py)
Output: one row per span: sentence_id, start, end, text, code, pid, entry,
        tag, src, kind (lemma | conj | form | value), method

Usage:
    python src/keyword_coder.py --sentences data/processed/sentences_500.parquet --method a_form
    python src/keyword_coder.py --sentences data/processed/sentences_only.parquet --method a_plus --out spans.csv
"""
import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
LIST_PATH = ROOT / "schema" / "keyword_list_v3.yaml"
SENTENCES = "data/processed/sentences_500.parquet"

CODES = ("N", "C", "B", "E", "A", "R")
ENV_CODES = ("N", "C", "B")
RESPONSE_CODES = ("E", "A", "R")
METHODS = ("a", "a_plus", "a_form")
RANK = {"value": 4, "lemma": 3, "conj": 2, "form": 1}

FUNCTION_WORDS = {"de", "du", "des", "d", "la", "le", "les", "l", "aux", "au", "en", "à", "et"}
APOS = "['’]"

# Rule D1: context words that decide the code of calme, voitures, restaurants...
CONTEXT = {
    "sound": re.compile(r"(?<!\w)(?:bruit\w*|bruyant\w*|sonores?|vacarme|entend\w*|klaxon\w*)(?!\w)", re.I),
    "smell": re.compile(r"(?<!\w)(?:odeurs?|parfums?|senteurs?|effluves?|arômes?|odorant\w*)(?!\w)", re.I),
    "feeling": re.compile(r"(?<!\w)(?:sentiments?|ressen\w+|se sent\w*|s['’](?:y )?sent\w*|apprécient|appréciaient"
                          r"|recherchent|recherchaient)(?!\w)", re.I),
}
# Rule I6: values in degrees Celsius.
VALUE_RE = re.compile(r"(?<![\w,.])[−–-]?\s?\d+(?:[.,]\d+)?\s?°\s?C(?![A-Za-z])")
# Rule I4: "été" is the participle of "être" after a form of "avoir".
SEASON_BEFORE = re.compile(r"(?:(?<!\w)[ldLD]['’]|(?<!\w)(?:le|un|cet|ce|en|à|au|aux|chaque|les|ces|des|pendant"
                           r"|durant|tout|par|cet)\s+)$", re.I)
AVOIR_BEFORE = re.compile(r"(?<!\w)(?:a|ai|as|avons|avez|ont|avait|avais|avaient|avions|aviez|aura|aurai|auras"
                          r"|aurons|aurez|auront|aurait|aurais|auraient|aurions|auriez|ait|aies|aient|eût"
                          r"|eussent|avoir|ayant)(?:\s+[\w'’-]+){0,5}\s+$", re.I)
DET_BEFORE = re.compile(r"(?:(?<!\w)(?:le|la|les|un|une|des|du|de la|au|aux|ce|cet|cette|ces|quelques|plusieurs"
                        r"|chaque|leurs?)\s+|(?<!\w)[ld]['’](?:une?\s+)?)(?:[\w-]+\s+)?$", re.I)
REFLEXIVE_BEFORE = re.compile(r"(?<!\w)(?:se|nous|vous|me|te|s['’]|m['’]|t['’])\s*(?:y\s+|en\s+)?"
                              r"(?:(?:ne\s+|n['’])?(?:sont|est|était|étaient|sera|seront|serait|seraient|soit"
                              r"|soient|fut|furent)\s+)?(?:(?:pas|plus|jamais|souvent|aussi|également|déjà)\s+)?$",
                              re.I)
SENTENCE_START = " \t«»“”\"'‘’()[]—–-•*"

FAIRE = r"(?:faire|fais|fait|faisons|faites|font|faisait|faisaient|faisant|fera|feront|ferait|feraient|fit|firent)"
ER_ENDINGS = ("er", "e", "es", "ent", "ons", "ez", "ais", "ait", "aient", "ions", "iez", "a", "as", "âmes", "âtes",
              "èrent", "ai", "erai", "eras", "era", "erons", "erez", "eront", "erais", "erait", "erions", "eriez",
              "eraient", "ant", "é", "ée", "és", "ées")


# --- the list ----------------------------------------------------------------

def load_list(path: Path = LIST_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_entries(kw: dict):
    """Yield one dict per entry of the list, in document order (341 entries,
    duplicates included), with its section code, effective code and group."""
    order = 0
    for section, cat in kw["categories"].items():
        for group in cat["groups"]:
            for e in group["entries"]:
                yield {**e, "section": section, "code": e.get("code", section), "group": group["name"],
                       "pos": e.get("pos", "n"), "order": order}
                order += 1


# --- forms (rule I1) -------------------------------------------------------------

def inflect_noun(word: str, plural: str = None) -> set:
    forms = {word}
    if plural:
        forms.add(plural)
    elif word[-1] not in "sxz":
        forms.add(word + ("x" if word.endswith(("eau", "au", "eu")) else "s"))
    return forms


def inflect_adj(word: str) -> set:
    """Masculine/feminine, singular/plural. Over-generation is harmless as
    long as it does not create another real word (see tests)."""
    w, f = word, {word}
    if w.endswith("e"):
        f.add(w + "s")
    elif w.endswith("el"):
        f |= {w + "s", w + "le", w + "les"}
    elif w.endswith(("ien", "on")):
        f |= {w + "s", w + "ne", w + "nes"}
    elif w.endswith("if"):
        f |= {w + "s", w[:-1] + "ve", w[:-1] + "ves"}
    elif w.endswith("eux"):
        f |= {w[:-1] + "se", w[:-1] + "ses"}
    elif w.endswith("al"):
        f |= {w + "e", w + "es", w[:-2] + "aux"}
    elif w.endswith("teur"):
        f |= {w + "s", w[:-1] + "se", w[:-1] + "ses", w[:-4] + "trice", w[:-4] + "trices"}
    elif w.endswith("eur"):
        f |= {w + "s", w[:-1] + "se", w[:-1] + "ses"}
    elif w.endswith("er"):
        f |= {w + "s", w[:-2] + "ère", w[:-2] + "ères"}
    elif w[-1] in "sxz":
        pass                                         # repos, marais: invariable
    else:
        f |= {w + "e", w + "s", w + "es"}
    return f


def conjugate_er(infinitive: str) -> set:
    """Conjugated forms of a regular -er verb (manger -> mangeait, mangé...)."""
    stem = infinitive[:-2]
    out = set()
    for ending in ER_ENDINGS:
        s = stem
        if stem.endswith("g") and ending[0] in "aâo":
            s = stem + "e"
        elif stem.endswith("c") and ending[0] in "aâo":
            s = stem[:-1] + "ç"
        out.add(s + ending)
    return out


def bare_verb(fr: str) -> str:
    """'se promener' -> 'promener', 's’asseoir' -> 'asseoir'."""
    return re.sub(r"^(?:se\s+|s['’])", "", fr)


def surface_forms(entry: dict) -> dict:
    """{kind: set of words} for a single-word entry or a verb."""
    pos, fr = entry["pos"], entry["fr"]
    drop = set(entry.get("drop", []))
    kinds = {"lemma": set(), "conj": set(), "form": set()}
    if pos == "v":
        inf = bare_verb(fr)
        kinds["conj"] = ({inf} | (conjugate_er(inf) if inf.endswith("er") else set())
                         | set(entry.get("conj", [])))
    elif pos == "adj":
        kinds["lemma"] = inflect_adj(fr)
    elif pos == "inv":
        kinds["lemma"] = {fr}
    else:
        kinds["lemma"] = {fr} | inflect_noun(entry.get("lemma", fr), entry.get("plural"))
    if entry.get("verb"):
        kinds["conj"] |= conjugate_er(entry["verb"])
    for form in entry.get("forms", []):
        kinds["form"] |= inflect_adj(form)
    return {k: {w for w in v if w not in drop} for k, v in kinds.items()}


def words_regex(words) -> str:
    """Alternation of words, longest first; ' matches ' and ’, - matches - or space."""
    parts = []
    for w in sorted(set(words), key=lambda x: (-len(x), x)):
        p = re.escape(w).replace("'", APOS).replace("’", APOS)
        parts.append(p)
    return "|".join(parts)


def expr_regex(fr: str) -> str:
    """Multi-word entry, every content word may take a plural or feminine
    ending: 'voie ferrée' -> voies ferrées, 'château d’eau' -> châteaux d'eau."""
    if fr.startswith("faire "):
        return FAIRE + r"\s+" + expr_regex(fr[len("faire "):])
    out = []
    for p in re.split(r"(\s+|-|['’])", fr):
        if not p:
            continue
        if p.isspace():
            out.append(r"\s+")
        elif p == "-":
            out.append(r"[-\s]")
        elif p in ("'", "’"):
            out.append(APOS)
        elif p.lower() in FUNCTION_WORDS:
            out.append(re.escape(p))
        else:
            out.append(re.escape(p) + "(?:es|e|s|x)?")
    return "".join(out)


def bounded(body: str, flags=re.IGNORECASE) -> re.Pattern:
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)", flags)


def exclusion_regex(pattern: str) -> re.Pattern:
    body = pattern.replace("'", APOS).replace(" ", r"\s+")
    return bounded(body)


# --- matchers -----------------------------------------------------------------------

def naive_pattern(term: str) -> re.Pattern:
    """Algorithm A / A+: the list term as written, whole word, case-insensitive,
    optional plural s/x (same as classify_keywords.term_pattern)."""
    words = [re.escape(w) for w in term.replace("’", "'").strip().split()]
    body = r"\s+".join(words).replace("'", APOS)
    return re.compile(rf"(?<!\w){body}(?:s|x)?(?!\w)", re.IGNORECASE)


def merge_duplicates(entries: list) -> list:
    """Entries with the same French term and code (culturel, foule, rivière,
    cascade, passerelle, montagne) are one matcher: their encodings are merged."""
    merged = {}
    for e in entries:
        key = (e["fr"], e["code"])
        if key not in merged:
            merged[key] = dict(e)
            continue
        m = merged[key]
        for field in ("forms", "conj", "exclude", "drop"):
            if e.get(field):
                m[field] = list(dict.fromkeys((m.get(field) or []) + e[field]))
        for field in ("require", "when", "lemma", "plural", "verb"):
            if e.get(field) and not m.get(field):
                m[field] = e[field]
    return list(merged.values())


def build_matchers(kw: dict, method: str = "a_form") -> list:
    """List of matcher dicts: {entry, kind, pattern, require, exclude, when}."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}, expected one of {METHODS}")
    entries = list(iter_entries(kw))
    if method == "a":
        entries = [e for e in entries if e["src"] == "K"]
    matchers = []
    if method in ("a", "a_plus"):
        for e in entries:
            if e["pos"] != "value":
                matchers.append({"entry": e, "kind": "lemma", "pattern": naive_pattern(e["fr"]),
                                 "require": None, "exclude": [], "when": None})
        return matchers

    for e in merge_duplicates(entries):
        exclude = [exclusion_regex(p) for p in e.get("exclude", [])]
        flags = 0 if e.get("case") == "exact" else re.IGNORECASE
        base = {"entry": e, "exclude": exclude, "when": e.get("when")}
        if e["pos"] == "value":
            matchers.append({**base, "kind": "value", "pattern": VALUE_RE, "require": None})
            continue
        if e["pos"] == "expr":
            matchers.append({**base, "kind": "lemma", "pattern": bounded(expr_regex(e["fr"]), flags),
                             "require": None})
            continue
        for kind, words in surface_forms(e).items():
            if not words:
                continue
            require = e.get("require")
            if kind == "form":
                require = None                   # derived words need no determiner / pronoun
            elif e["pos"] == "v" and require != "reflexive":
                require = None
            matchers.append({**base, "kind": kind, "pattern": bounded(words_regex(words), flags),
                             "require": require})
    return matchers


# --- rules applied to one candidate --------------------------------------------------

def at_sentence_start(text: str, start: int) -> bool:
    return text[:start].strip(SENTENCE_START) == ""


def is_proper_name(text: str, start: int, end: int) -> bool:
    """Rule I5: 'Arbonne-la-Forêt', 'lycée du Parc', 'Météo-France'."""
    if text[start].isupper() and not at_sentence_start(text, start):
        return True
    left, right = start, end
    while left > 0 and (text[left - 1].isalnum() or text[left - 1] == "-"):
        left -= 1
    while right < len(text) and (text[right].isalnum() or text[right] == "-"):
        right += 1
    outside = text[left:start] + " " + text[end:right]
    return "-" in text[left:right] and any(p[:1].isupper() for p in re.split(r"[-\s]", outside) if p)


def require_ok(require: str, text: str, start: int) -> bool:
    before = text[:start]
    if require == "det":
        return bool(DET_BEFORE.search(before))
    if require == "reflexive":
        return bool(REFLEXIVE_BEFORE.search(before))
    if require == "ete":
        if SEASON_BEFORE.search(before):
            return True
        return not AVOIR_BEFORE.search(before)
    return True


def code_sentence(text: str, matchers: list, method: str = "a_form") -> list:
    """All spans of one sentence, after overlap resolution (rule I3)."""
    naive = method in ("a", "a_plus")
    contexts = {} if naive else {k: bool(p.search(text)) for k, p in CONTEXT.items()}
    candidates = []
    for m in matchers:
        e = m["entry"]
        for x in m["pattern"].finditer(text):
            start, end = x.start(), x.end()
            if not text[start:end].strip():
                continue
            code, when_ok = e["code"], 0
            if not naive:
                if m["kind"] != "value" and e.get("case") != "exact" and is_proper_name(text, start, end):
                    continue
                if m["require"] and not require_ok(m["require"], text, start):
                    continue
                if any(ex.start() <= start and end <= ex.end()
                       for p in m["exclude"] for ex in p.finditer(text)):
                    continue
                if m["when"]:
                    if contexts[m["when"]["context"]]:
                        when_ok = 1
                    else:
                        code = m["when"]["else"]
            candidates.append({"start": start, "end": end, "text": text[start:end], "code": code,
                               "entry": e["fr"], "tag": e["tag"], "src": e["src"], "kind": m["kind"],
                               "_key": (-(end - start), -when_ok, -RANK[m["kind"]], e["order"])})
    chosen = []
    for c in sorted(candidates, key=lambda c: c["_key"]):
        if all(c["end"] <= s["start"] or s["end"] <= c["start"] for s in chosen):
            chosen.append(c)
    chosen.sort(key=lambda c: c["start"])
    envs = [c for c in ENV_CODES if any(s["code"] == c for s in chosen)]
    for c in chosen:
        del c["_key"]
        c["pid"] = (",".join(envs) or "0") if c["code"] in RESPONSE_CODES else ""
    return chosen


def code_sentences(sentences: pd.DataFrame, kw: dict, method: str = "a_form") -> pd.DataFrame:
    """One row per span for a sentences table (columns sentence_id, text)."""
    matchers = build_matchers(kw, method)
    rows = []
    for s in sentences.itertuples(index=False):
        for span in code_sentence(s.text, matchers, method):
            rows.append({"sentence_id": s.sentence_id, **span, "method": method})
    columns = ["sentence_id", "start", "end", "text", "code", "pid", "entry", "tag", "src", "kind", "method"]
    return pd.DataFrame(rows, columns=columns)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sentences", default=SENTENCES)
    ap.add_argument("--method", choices=METHODS, default="a_form")
    ap.add_argument("--list", default=str(LIST_PATH), help="keyword list (YAML)")
    ap.add_argument("--out", default=None, help="default: spans_<method>.csv next to the sentences file")
    args = ap.parse_args()

    if not Path(args.sentences).exists():
        sys.exit(f"{args.sentences} not found: run src/split_sentences.py first.")
    sentences = pd.read_parquet(args.sentences)
    kw = load_list(Path(args.list))
    t0 = time.perf_counter()
    spans = code_sentences(sentences, kw, args.method)
    elapsed = time.perf_counter() - t0
    out = Path(args.out or Path(args.sentences).with_name(f"spans_{args.method}.csv"))
    out.parent.mkdir(parents=True, exist_ok=True)
    spans.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{len(sentences)} sentences, {len(spans)} spans ({args.method}, {elapsed:.2f} s) -> {out}")
    counts = spans["code"].value_counts()
    print("  " + "  ".join(f"{c} {counts.get(c, 0)}" for c in CODES))


if __name__ == "__main__":
    main()
