"""Method 'hybrid': keyword spans (A-form) + an LLM check of the responses.

Environments (N, C, B) are kept exactly as A-form codes them: the keyword
list is reliable for them. Each sentence that contains a response candidate
(E, A, R) is sent once to an LLM, with its candidates, the environment words
of the sentence, the previous sentence (to understand pronouns) and rules D4,
D6 and D7 of the manual. For each candidate the LLM answers:

    valid   does the sentence report that people feel / do / think it?
    links   which environment words of the sentence it relates to (rule D7)
    reason  a few words, kept in the audit file

Invalid responses are dropped; valid ones get the LLM's links instead of "every
environment of the sentence". The LLM never adds a word or changes a code: the
list stays closed (rule I1) and the method stays comparable with the coders.
A candidate the LLM could not judge (refusal, error) keeps its A-form coding
and is flagged.

Answers are cached (JSON lines, one per request) under a key made of the model,
the prompt version and the request, so that a run can be repeated and audited
without new calls. Default cache: data/llm/hybrid_answers.jsonl.

Usage:
    python src/hybrid.py --sentences data/processed/sentences_500.parquet
        -> data/processed/spans_hybrid.csv and spans_hybrid_audit.csv
    python src/hybrid.py --sentences ... --offline       # cached answers only, no API call
Needs an Anthropic credential unless --offline: ANTHROPIC_API_KEY in a `.env` file at the project root (read
automatically, never committed), in the environment, or an `ant auth login` profile.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

import keyword_coder as kc

ROOT = kc.ROOT
CACHE = ROOT / "data" / "llm" / "hybrid_answers.jsonl"
MODEL = "claude-opus-5-5"
EFFORT = "medium"
PROMPT_VERSION = "hybrid-v1"


# Server-side fallback (another model answers when this one declines). Off: in a comparison of models every
# answer must come from the model tested; a declined request is recorded as "refused" and keeps the keyword coding.
FALLBACK = False


def fallback_args(model: str) -> dict:
    """Fallback parameters when FALLBACK is on: Opus, Sonnet and Fable models only (Haiku has none)."""
    if FALLBACK and model.startswith(("claude-opus", "claude-sonnet", "claude-fable")):
        return {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return {}


def load_env(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines of the project's .env into the environment (values
    already set in the environment win). No dependency on python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and not os.environ.get(key):
            os.environ[key] = value

SYSTEM = """You check keyword codes for the Desirable Cities project, which codes the French Wikipedia articles \
of French communes with the framework of J. Villar: three environments (N natural, C cultural, B constructural) \
and three responses of people (E emotions, A actions, R reflections).

A keyword algorithm has already coded the words of one sentence, using a closed list of French words and their \
forms. Its environment words are correct for this task. You check its RESPONSE words only, with three rules of \
the coders' manual:

D4. Who feels or acts. An emotion (E) or an action (A) is coded only when people experience it, whoever they \
are: residents, visitors, workers, kings, pilgrims. Past, future and negation count ("les rois s'y \
promenaient"). An adjective that the article uses about the place ("magnifique") is not an emotion. A document \
is not an action ("photos aériennes" is not "photographier"). The name of a building, an institution, a \
dish or a work is not an action ("patinoire", "Institut national du travail", "Danse à Lyon"). A word in \
another sense is not a response ("actions" in finance, "assisté" for a deputy mayor).

D6. Reflections. A reflection (R) is coded when the text reports what people think of the place: its \
reputation, a nickname, a symbol, a debate or a criticism about it ("Lyon est réputée pour sa gastronomie", \
"la tour surnommée le Crayon"). A fact stated as a fact is not a reflection. A person, a work or an event \
being famous is not a reflection about the place. A project or an offer ("projet de tramway", "radio proposant \
du jazz") is not a reflection.

D7. PID links. For each valid response, list the environment words of THE SAME SENTENCE it relates to: the \
action takes place in that element or uses it, the emotion is caused by it, the reflection is about it. Use \
only the ids of the environment words given. If it relates to none of them, give an empty list.

The input is JSON: the sentence, the previous sentence (only to understand who or what "il", "elle", "y" \
refers to; never link to its words), the section title, the candidates (id, word as written, code, list \
entry) and the environment words (id, word, code). Judge every candidate, in the given order. Do not judge \
or add environment words. Give a reason of at most 12 words."""

SCHEMA = {
    "type": "object",
    "properties": {
        "responses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "valid": {"type": "boolean"},
                    "links": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["id", "valid", "links", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["responses"],
    "additionalProperties": False,
}


class MissingAnswers(RuntimeError):
    """Offline run and some requests have no cached answer."""


class JudgeUnavailable(RuntimeError):
    """No credential or no SDK: the LLM cannot be called at all."""


# --- requests --------------------------------------------------------------------------

def build_requests(spans: pd.DataFrame, sentences: pd.DataFrame) -> list:
    """One request per sentence with at least one response candidate:
    [(sentence_id, request dict, {candidate id: span index}, {env id: code})]."""
    sents = sentences.reset_index(drop=True)
    text = dict(zip(sents["sentence_id"], sents["text"]))
    section = dict(zip(sents["sentence_id"], sents["section_titre"])) if "section_titre" in sents else {}
    order = list(sents["sentence_id"])
    position = {sid: i for i, sid in enumerate(order)}
    out = []
    for sid, g in spans.groupby("sentence_id", sort=False):
        g = g.sort_values("start")
        resp = g[g["code"].isin(kc.RESPONSE_CODES)]
        if resp.empty:
            continue
        env = g[g["code"].isin(kc.ENV_CODES)]
        cand_ids = {f"r{k + 1}": i for k, i in enumerate(resp.index)}
        env_ids = {f"e{k + 1}": c for k, c in enumerate(env["code"])}
        i = position.get(sid)
        previous = text.get(order[i - 1], "") if i else ""
        request = {
            "sentence": text.get(sid, ""),
            "previous_sentence": previous,
            "section": section.get(sid, "") or "",
            "candidates": [{"id": cid, "word": spans.at[i, "text"], "code": spans.at[i, "code"],
                            "list_entry": spans.at[i, "entry"]} for cid, i in cand_ids.items()],
            "environment_words": [{"id": eid, "word": w, "code": c}
                                  for eid, w, c in zip(env_ids, env["text"], env["code"])],
        }
        out.append((sid, request, cand_ids, env_ids))
    return out


def cache_key(model: str, request: dict, prompt: str = PROMPT_VERSION) -> str:
    payload = json.dumps({"model": model, "prompt": prompt, "request": request}, ensure_ascii=False,
                         sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- judges ----------------------------------------------------------------------------

class AnthropicJudge:
    """Calls the Claude API (Messages, structured output)."""

    def __init__(self, model: str = MODEL, effort: str = EFFORT):
        try:
            import anthropic                              # only needed for live runs
        except ImportError as e:
            raise JudgeUnavailable("the anthropic package is not installed (pip install anthropic)") from e
        load_env()
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model, self.effort = model, effort

    def __call__(self, request: dict) -> dict:
        try:
            return self._call(request)
        except (self.anthropic.AuthenticationError, self.anthropic.PermissionDeniedError) as e:
            raise JudgeUnavailable(f"Claude API: {type(e).__name__}") from e

    def _call(self, request: dict) -> dict:
        t0 = time.perf_counter()
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=8000,
            **fallback_args(self.model),                  # another model answers if this one declines
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": json.dumps(request, ensure_ascii=False)}],
        )
        usage = {"input": response.usage.input_tokens, "output": response.usage.output_tokens,
                 "cache_read": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
                 "served_by": response.model, "seconds": round(time.perf_counter() - t0, 2)}
        if response.stop_reason == "refusal":
            return {"status": "refused", "responses": [], "usage": usage}
        text = next((b.text for b in response.content if b.type == "text"), "")
        return {"status": "checked", **json.loads(text), "usage": usage}


class CachedJudge:
    """Answers from the cache; asks `inner` (if any) for the others and stores them."""

    def __init__(self, path: Path, model: str, inner=None, prompt: str = PROMPT_VERSION):
        self.path, self.model, self.inner, self.prompt = Path(path), model, inner, prompt
        self.lock = threading.Lock()
        self.answers = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.answers[row["key"]] = row["answer"]

    def has(self, request: dict) -> bool:
        return cache_key(self.model, request, self.prompt) in self.answers

    def __call__(self, request: dict) -> dict:
        key = cache_key(self.model, request, self.prompt)
        if key in self.answers:
            return self.answers[key]
        if self.inner is None:
            raise MissingAnswers(f"no cached answer for model {self.model!r}")
        answer = self.inner(request)
        self.store(request, answer)
        return answer

    def store(self, request: dict, answer: dict) -> None:
        key = cache_key(self.model, request, self.prompt)
        row = {"key": key, "model": self.model, "prompt": self.prompt, "date": date.today().isoformat(),
               "request": request, "answer": answer}
        with self.lock:
            self.answers[key] = answer
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


# --- the method --------------------------------------------------------------------------

def hybrid_spans(spans: pd.DataFrame, sentences: pd.DataFrame, judge, workers: int = 4) -> tuple:
    """(kept spans, audit). `spans` are A-form spans; `judge(request) -> answer`."""
    requests = build_requests(spans, sentences)
    answers = {}

    def ask(item):
        sid, request, _, _ = item
        try:
            return sid, judge(request)
        except (MissingAnswers, JudgeUnavailable):
            raise
        except Exception as e:                            # API error: keep A-form coding, flag it
            return sid, {"status": f"error: {type(e).__name__}", "responses": []}

    if workers > 1 and len(requests) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            answers = dict(pool.map(ask, requests))
    else:
        answers = dict(ask(item) for item in requests)

    spans = spans.copy()
    spans["check"] = ""
    spans["reason"] = ""
    drop, audit = [], []
    for sid, request, cand_ids, env_ids in requests:
        answer = answers[sid]
        status = answer.get("status", "checked")
        verdicts = {r["id"]: r for r in answer.get("responses", [])}
        for cid, i in cand_ids.items():
            v = verdicts.get(cid)
            before = spans.at[i, "pid"]
            if v is None:
                spans.at[i, "check"] = status if status != "checked" else "missing"
                valid, codes = None, before
            else:
                valid = bool(v["valid"])
                codes = ",".join(c for c in kc.ENV_CODES if c in {env_ids[e] for e in v["links"] if e in env_ids})
                spans.at[i, "check"] = "valid" if valid else "invalid"
                spans.at[i, "reason"] = v.get("reason", "")
                if valid:
                    spans.at[i, "pid"] = codes or "0"
                else:
                    drop.append(i)
            env_words = {e["id"]: e["word"] for e in request["environment_words"]}
            audit.append({"sentence_id": sid, "start": spans.at[i, "start"], "end": spans.at[i, "end"],
                          "text": spans.at[i, "text"], "code": spans.at[i, "code"], "entry": spans.at[i, "entry"],
                          "pid_a_form": before, "valid": valid, "pid_hybrid": codes if valid else "",
                          "linked_words": "; ".join(env_words.get(e, e) for e in (v or {}).get("links", [])),
                          "reason": (v or {}).get("reason", ""), "status": spans.at[i, "check"],
                          "sentence": request["sentence"]})
    kept = spans.drop(index=drop).assign(method="hybrid")
    return kept, pd.DataFrame(audit)


def make_judge(model: str = MODEL, effort: str = EFFORT, cache: Path = CACHE, offline: bool = False) -> CachedJudge:
    """Cached answers first; the Claude API for the others unless offline (or
    when the SDK is missing, in which case only cached answers are used)."""
    inner = None
    if not offline:
        try:
            inner = AnthropicJudge(model, effort)
        except JudgeUnavailable as e:
            print(f"hybrid: {e}; using cached answers only", file=sys.stderr)
    return CachedJudge(cache, model, inner)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sentences", default=kc.SENTENCES)
    ap.add_argument("--list", default=str(kc.LIST_PATH), help="keyword list (YAML)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--effort", default=EFFORT, choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--cache", default=str(CACHE))
    ap.add_argument("--offline", action="store_true", help="use cached answers only")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=None, help="default: spans_hybrid.csv next to the sentences file")
    args = ap.parse_args()

    sentences = pd.read_parquet(args.sentences)
    spans = kc.code_sentences(sentences, kc.load_list(Path(args.list)), "a_form")
    judge = make_judge(args.model, args.effort, Path(args.cache), args.offline)
    t0 = time.perf_counter()
    kept, audit = hybrid_spans(spans, sentences, judge, args.workers)
    out = Path(args.out or Path(args.sentences).with_name("spans_hybrid.csv"))
    kept.to_csv(out, index=False, encoding="utf-8-sig")
    audit.to_csv(out.with_name(out.stem + "_audit.csv"), index=False, encoding="utf-8-sig")
    counts = audit["status"].value_counts().to_dict() if len(audit) else {}
    print(f"{len(audit)} response candidates checked in {time.perf_counter() - t0:.0f} s: {counts} -> {out}")


if __name__ == "__main__":
    main()
