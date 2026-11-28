"""Method 'IA': an LLM codes the whole article like a human coder.

The LLM receives what the human coders receive: the rules for manual coding v2
(docs/rules_manual_coding_v2.md, sections 0 to 3) and keyword list v3, then the
sentences of the article in batches. It returns every span it codes (word as
written, code, list entry, and the PID links of each response). The spans are
located in the sentences and written in the same format as keyword_coder.py,
so that every method is scored the same way.

Unlike the Hybrid method, the LLM chooses the words itself: it can find what
the keyword matcher misses, and it can also code words that are not in the
list. Answers are cached (data/llm/llm_coder_answers.jsonl) under a key made
of the model, the prompt version and the request.

Usage:
    python src/llm_coder.py --sentences data/processed/sentences_500.parquet
        -> data/processed/spans_ia.csv
Needs ANTHROPIC_API_KEY (project .env, environment, or `ant auth login`) unless --offline.
"""
import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import hybrid
import keyword_coder as kc

ROOT = kc.ROOT
CACHE = ROOT / "data" / "llm" / "llm_coder_answers.jsonl"
MODEL = hybrid.MODEL
EFFORT = hybrid.EFFORT
PROMPT_VERSION = "ia-v3"
BATCH = 20
MANUAL = ROOT / "docs" / "rules_manual_coding_v2.md"

SCHEMA = {
    "type": "object",
    "properties": {
        "spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "word": {"type": "string"},
                    "code": {"type": "string", "enum": list(kc.CODES)},
                    "entry": {"type": "string"},
                    "links": {"type": "array", "items": {"type": "string", "enum": list(kc.ENV_CODES)}},
                },
                "required": ["i", "word", "code", "entry", "links"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["spans"],
    "additionalProperties": False,
}


def manual_text() -> str:
    """Sections 0 to 3 of the manual: everything a human coder reads, not the
    note on how the algorithm applies the rules."""
    text = MANUAL.read_text(encoding="utf-8")
    start = text.index("## 0.")
    end = text.index("## How the algorithm applies these rules")
    return text[start:end].strip()


def list_text(kw: dict) -> str:
    """The list by category; each entry is followed by the derived words already identified in the list
    encoding (rule I1), in brackets: hints, not an exhaustive list."""
    lines = []
    for section, cat in kw["categories"].items():
        lines.append(f"\n{section} — {cat['label']}")
        for group in cat["groups"]:
            words = ", ".join(e["fr"] + (f" [{', '.join(e['forms'])}]" if e.get("forms") else "")
                              for e in group["entries"])
            lines.append(f"  {group['name']}: {words}")
    return "\n".join(lines)


HOW_TO_DECIDE = """You decide, word by word, as an expert coder who applies the rules fully:

- Rule I1, forms. Code every form of a list entry AND every word built on the same French stem, whatever its part
  of speech: noun, adjective, verb, adverb, singular or plural, masculine or feminine. A derived word counts even
  when it is not given in brackets after the entry: the brackets are hints, not a closed list. Examples: forêt →
  forestier, forestière; climat → climatique; agriculture → agricole; urbain → urbanisé, urbanisation. Synonyms and
  more specific words still do not count (chêne is not arbres; fleuve is not rivière).
- Rule I4, homonyms and fixed expressions. Decide from the meaning of the sentence, not from the spelling: "il a
  été élu" is the verb être, "l'été" or "un été frais" is the season; "prendre place", "fiscalité propre",
  "bassin houiller", "son maire" (possessive) are not list words. A list word that is only part of a proper name
  is not coded (Arbonne-la-Forêt, lycée du Parc), but a common noun naming the real thing is (la forêt de
  Fontainebleau → forêt).
- Rules D4 and D6, responses: see the precisions below.
- When a word is a form of a list entry and not a homonym, code it (rule I9): do not leave it out for prudence."""


def rule_precisions() -> str:
    """Rules D4 and D6 as worded for the Hybrid method (hybrid.SYSTEM), so that both LLM methods receive
    exactly the same precisions on top of the manual."""
    text = hybrid.SYSTEM
    return text[text.index("D4. Who feels or acts."):text.index("D7. PID links.")].strip()


def system_prompt(kw: dict) -> str:
    return f"""You are a coder of the Desirable Cities project. You code French Wikipedia articles about French \
communes with the framework of J. Villar, exactly as the human coders do, following their manual and their \
keyword list below.

For each sentence you receive, mark every span (a word or a fixed expression of the running text) that the rules \
tell you to code, with its code (N, C, B, E, A, R) and the list entry it is a form of. For each E, A or R span, give \
the environment codes of the same sentence it relates to (rule D7), or an empty list. Write `word` exactly as it \
appears in the sentence (same case, same accents), one item per occurrence, in reading order. A sentence with \
nothing to code gives no item. Use the sentence numbers `i` you are given.

# Rules for manual coding (v2)

{manual_text()}

# How to decide

{HOW_TO_DECIDE}

# Precisions on rules D4 and D6 (the same as given to the Hybrid method)

{rule_precisions()}

# Keyword list v3 (only these words, in any of their forms and derived words, rule I1)
{list_text(kw)}
"""


def build_requests(sentences: pd.DataFrame, title: str = "", batch: int = BATCH) -> list:
    """[(sentence ids of the batch, request)] with sentences numbered from 0 in each batch."""
    sents = sentences.reset_index(drop=True)
    has_section = "section_titre" in sents
    out = []
    for start in range(0, len(sents), batch):
        part = sents.iloc[start:start + batch]
        request = {"article": title, "sentences": [
            {"i": k, "section": (r.section_titre or "") if has_section else "", "text": r.text}
            for k, r in enumerate(part.itertuples(index=False))]}
        out.append((list(part["sentence_id"]), request))
    return out


class AnthropicCoder:
    def __init__(self, kw: dict, model: str = MODEL, effort: str = EFFORT):
        try:
            import anthropic
        except ImportError as e:
            raise hybrid.JudgeUnavailable("the anthropic package is not installed (pip install anthropic)") from e
        hybrid.load_env()
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.system = system_prompt(kw)
        self.model, self.effort = model, effort

    def __call__(self, request: dict) -> dict:
        t0 = time.perf_counter()
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=64000,
                **hybrid.fallback_args(self.model),
                system=[{"type": "text", "text": self.system, "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": json.dumps(request, ensure_ascii=False)}],
            ) as stream:
                response = stream.get_final_message()
        except (self.anthropic.AuthenticationError, self.anthropic.PermissionDeniedError) as e:
            raise hybrid.JudgeUnavailable(f"Claude API: {type(e).__name__}") from e
        usage = {"input": response.usage.input_tokens, "output": response.usage.output_tokens,
                 "cache_read": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
                 "served_by": response.model, "seconds": round(time.perf_counter() - t0, 2)}
        if response.stop_reason == "refusal":
            return {"status": "refused", "spans": [], "usage": usage}
        text = next((b.text for b in response.content if b.type == "text"), "")
        return {"status": "checked" if response.stop_reason != "max_tokens" else "truncated",
                **json.loads(text), "usage": usage}


def locate(text: str, word: str, used: set):
    """(start, end) of the first occurrence of `word` in `text` not used yet,
    as a whole word; case-insensitive as a fallback."""
    for flags in (0, re.IGNORECASE):
        for m in re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", text, flags):
            if (m.start(), m.end()) not in used:
                return m.start(), m.end()
    return None


def to_spans(batches: list, answers: list, texts: dict) -> tuple:
    """(spans DataFrame, number of returned spans that could not be located)."""
    rows, lost = [], 0
    for (ids, _), answer in zip(batches, answers):
        used = {}
        for s in answer.get("spans", []):
            if not 0 <= s["i"] < len(ids) or not s["word"].strip():
                lost += 1
                continue
            sid = ids[s["i"]]
            pos = locate(texts[sid], s["word"], used.setdefault(sid, set()))
            if pos is None:
                lost += 1
                continue
            used[sid].add(pos)
            links = [c for c in kc.ENV_CODES if c in s["links"]]
            pid = (",".join(links) or "0") if s["code"] in kc.RESPONSE_CODES else ""
            rows.append({"sentence_id": sid, "start": pos[0], "end": pos[1], "text": texts[sid][pos[0]:pos[1]],
                         "code": s["code"], "pid": pid, "entry": s["entry"], "tag": "", "src": "",
                         "kind": "llm", "method": "ia"})
    columns = ["sentence_id", "start", "end", "text", "code", "pid", "entry", "tag", "src", "kind", "method"]
    spans = pd.DataFrame(rows, columns=columns)
    position = {}
    for ids, _ in batches:
        for sid in ids:
            position[sid] = len(position)
    spans = (spans.assign(_o=spans["sentence_id"].map(position)).sort_values(["_o", "start"])
             .drop(columns="_o").reset_index(drop=True))
    return spans, lost


def code_article(sentences: pd.DataFrame, coder, title: str = "", workers: int = 4) -> tuple:
    """(spans, {status: number of batches}, unlocated spans). `coder(request) -> answer`."""
    batches = build_requests(sentences, title)

    def ask(item):
        try:
            return coder(item[1])
        except (hybrid.MissingAnswers, hybrid.JudgeUnavailable):
            raise
        except Exception as e:
            return {"status": f"error: {type(e).__name__}", "spans": []}

    if workers > 1 and len(batches) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            answers = list(pool.map(ask, batches))
    else:
        answers = [ask(b) for b in batches]
    texts = dict(zip(sentences["sentence_id"], sentences["text"]))
    spans, lost = to_spans(batches, answers, texts)
    status = {}
    for a in answers:
        status[a.get("status", "checked")] = status.get(a.get("status", "checked"), 0) + 1
    return spans, status, lost


def make_coder(kw: dict, model: str = MODEL, effort: str = EFFORT, cache: Path = CACHE, offline: bool = False):
    inner = None
    if not offline:
        try:
            inner = AnthropicCoder(kw, model, effort)
        except hybrid.JudgeUnavailable as e:
            print(f"ia: {e}; using cached answers only", file=sys.stderr)
    coder = hybrid.CachedJudge(cache, model, inner, prompt=PROMPT_VERSION)
    coder.lock = threading.Lock()
    return coder


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sentences", default=kc.SENTENCES)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT)
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    sentences = pd.read_parquet(args.sentences)
    coder = make_coder(kc.load_list(), args.model, args.effort, Path(args.cache), args.offline)
    spans, status, lost = code_article(sentences, coder, workers=args.workers)
    out = Path(args.out or Path(args.sentences).with_name("spans_ia.csv"))
    spans.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{len(spans)} spans ({lost} not located), batches {status} -> {out}")


if __name__ == "__main__":
    main()
