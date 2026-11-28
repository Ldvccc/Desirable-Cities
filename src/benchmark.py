"""Benchmark of five coders on Courchaton, Lyon and Fontainebleau (spans only, no PID matrix).

    Naive       list v3, every word as written (whole word, optional s/x), no rule, no exclusion
    Upgrade     list v3 + rules v2 and the exclusions written from Courchaton (the list encoding of v3)
    Upgrade +   Upgrade + the exclusions and corrected forms found on Lyon (taken from list v4), WITHOUT the
                words v4 adds or removes: the 341 words of v3 are kept
    Hybrid      Upgrade +, with every response (E, A, R) checked by an LLM (hybrid.py)
    IA          an LLM codes the whole article like a human coder, with the manual and list v3 (llm_coder.py)

Courchaton has a human reference (development data). Lyon is the baseline: no human coding yet; precision is
estimated on the review sample (200 spans judged by Claude). Fontainebleau is the test: no reference; the
coders are compared with each other and with the IA.

Hybrid and IA call the Claude API (ANTHROPIC_API_KEY in the project .env), once per model given with --models
(e.g. claude-haiku-5-5 claude-sonnet-5-5 claude-opus-5-5). Answers are cached per model in data/llm/: a model
already run costs nothing. Without a key, or with --offline and no cached answers, they are reported as not run.

Output: docs/benchmark.pdf, docs/benchmark.csv, docs/benchmark_spans.csv (every span of every coder)

Usage:
    python src/benchmark.py --models claude-haiku-5-5 --plan    # requests still to send and estimated cost; no call
    python src/benchmark.py --models claude-haiku-5-5            # runs the requests not cached yet
    python src/benchmark.py --models claude-haiku-5-5 claude-sonnet-5-5 --offline   # report from the cache only
"""
import argparse
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

import compare_coders as cc
import compare_methods as methods_mod
import hybrid
import keyword_coder as kc
import llm_coder

ROOT = kc.ROOT
OUT = ROOT / "docs" / "benchmark"
BASE = ["Naive", "Upgrade", "Upgrade +"]
MODEL_LABELS = {"claude-haiku-5-5": "Haiku 5.5", "claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5"}
# $ per million tokens: input, output, cache read (first-party prices, cached 2026-11-03)
PRICES = {"claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-sonnet-5-5": (2.0, 10.0, 0.10),
          "claude-opus-5-5": (4.0, 20.0, 0.20)}


def label(model: str) -> str:
    return MODEL_LABELS.get(model, model)


def llm_coders(models: list) -> list:
    return [f"{kind} · {label(m)}" for m in models for kind in ("Hybrid", "IA")]
ROLE = {"Courchaton": "human reference (development data)", "Lyon": "baseline (no human coding yet)",
        "Fontainebleau": "test (no reference)"}


# --- the lists ----------------------------------------------------------------------------

def upgrade_plus_list(v3: dict, v4: dict) -> dict:
    """List v3 with the encoding of list v4 (exclusions, forms, third-person verbs) on the same entries.
    The 45 entries v4 adds are left out; the 3 entries v4 removes keep their v3 encoding. Built in memory:
    neither list file is changed."""
    v4_entries = {}
    for e in kc.iter_entries(v4):
        if e["src"] != "L":
            v4_entries.setdefault((e["section"], e["tag"], e["fr"]), []).append(e)
    seen = Counter()
    out = {k: v for k, v in v3.items() if k != "categories"}
    out["version"] = "3.0.0+lyon-exclusions"
    out["encoding"] = dict(v4.get("encoding") or {})
    out["categories"] = {}
    for section, cat in v3["categories"].items():
        groups = []
        for group in cat["groups"]:
            entries = []
            for e in group["entries"]:
                key = (section, e["tag"], e["fr"])
                match = v4_entries.get(key, [])
                if seen[key] < len(match):
                    new = {k: v for k, v in match[seen[key]].items()
                           if k not in ("section", "group", "order") and not (k == "code" and "code" not in e)
                           and not (k == "pos" and "pos" not in e and v == "n")}
                    entries.append(new)
                else:
                    entries.append(dict(e))
                seen[key] += 1
            groups.append({**group, "entries": entries})
        out["categories"][section] = {**cat, "groups": groups}
    return out


# --- runs -----------------------------------------------------------------------------------

def run_coders(sentences: pd.DataFrame, title: str, lists: dict, judges: list, coders: list,
                workers: int = 4) -> tuple:
    """({coder: spans}, {coder: note}). judges: [(model, judge)] for Hybrid; coders: [(model, coder)] for IA."""
    runs, notes = {}, {}
    for name, (kw, method) in (("Naive", (lists["v3"], "a_plus")), ("Upgrade", (lists["v3"], "a_form")),
                               ("Upgrade +", (lists["v3+"], "a_form"))):
        t0 = time.perf_counter()
        runs[name] = kc.code_sentences(sentences, kw, method)
        notes[name + " seconds"] = time.perf_counter() - t0
    for model, judge in judges:
        h = f"Hybrid · {label(model)}"
        try:
            runs[h], audit = hybrid.hybrid_spans(runs["Upgrade +"], sentences, judge, workers)
            bad = audit[~audit["status"].isin(["valid", "invalid"])] if len(audit) else audit
            if len(bad):
                notes[h + " status"] = f"{len(bad)} candidates not judged ({', '.join(sorted(set(bad['status'])))})"
        except (hybrid.MissingAnswers, hybrid.JudgeUnavailable) as e:
            notes[h] = str(e)
    for model, coder in coders:
        i = f"IA · {label(model)}"
        try:
            spans, status, lost = llm_coder.code_article(sentences, coder, title, workers)
            runs[i] = spans
            notes[i + " status"] = f"batches {status}, {lost} spans not located"
        except (hybrid.MissingAnswers, hybrid.JudgeUnavailable) as e:
            notes[i] = str(e)
    return runs, notes


def requests_of(article_sentences: dict, lists: dict) -> dict:
    """{"hybrid": [requests], "ia": [requests]} that a run on these articles sends (one model)."""
    out = {"hybrid": [], "ia": []}
    for title, sentences in article_sentences.items():
        base = kc.code_sentences(sentences, lists["v3+"], "a_form")
        out["hybrid"] += [r for _, r, _, _ in hybrid.build_requests(base, sentences)]
        out["ia"] += [r for _, r in llm_coder.build_requests(sentences, title)]
    return out


def cache_rows(path: Path) -> dict:
    import json
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["key"]] = r
    return rows


def usage_cost(model: str, rows: list) -> tuple:
    """(input, output, cache read tokens, $) of cached answers; cache writes are counted as plain input."""
    pin, pout, pcache = PRICES.get(model, (float("nan"),) * 3)
    i = sum(r["answer"].get("usage", {}).get("input", 0) for r in rows)
    usage_cost.seconds = sum(r["answer"].get("usage", {}).get("seconds", 0) or 0 for r in rows)
    o = sum(r["answer"].get("usage", {}).get("output", 0) for r in rows)
    c = sum(r["answer"].get("usage", {}).get("cache_read", 0) for r in rows)
    return i, o, c, (i * pin + o * pout + c * pcache) / 1e6


def plan(models: list, requests: dict, kw: dict) -> list:
    """Requests not cached yet per model and method, with an estimated cost. Token counts are estimated from
    the text length (4 characters per token) and from the output per request measured on the cached Haiku run,
    doubled to allow for longer thinking by bigger models; this is an estimate, not a quote."""
    import json
    hc, ic = cache_rows(hybrid.CACHE), cache_rows(llm_coder.CACHE)
    sys_h, sys_i = len(hybrid.SYSTEM) // 4, len(llm_coder.system_prompt(kw)) // 4
    measured = {}
    for kind, rows in (("hybrid", hc), ("ia", ic)):
        haiku = [r for r in rows.values() if r["model"] == "claude-haiku-5-5"
                 and r["prompt"] == (hybrid.PROMPT_VERSION if kind == "hybrid" else llm_coder.PROMPT_VERSION)]
        if not haiku and kind == "ia":                      # ia-v1 (40 sentences): scale to the current batch
            old = [r for r in rows.values() if r["model"] == "claude-haiku-5-5"]
            per_sentence = (sum(r["answer"].get("usage", {}).get("output", 0) for r in old)
                            / max(1, sum(len(r["request"]["sentences"]) for r in old)))
            measured[kind] = per_sentence * llm_coder.BATCH
        else:
            measured[kind] = (sum(r["answer"].get("usage", {}).get("output", 0) for r in haiku) / max(1, len(haiku)))
    out = []
    for model in models:
        pin, pout, pcache = PRICES.get(model, (float("nan"),) * 3)
        for kind, reqs, rows, system, version in (("hybrid", requests["hybrid"], hc, sys_h, hybrid.PROMPT_VERSION),
                                                  ("ia", requests["ia"], ic, sys_i, llm_coder.PROMPT_VERSION)):
            todo = [r for r in reqs if hybrid.cache_key(model, r, version) not in rows]
            user = sum(len(json.dumps(r, ensure_ascii=False)) // 4 for r in todo)
            factor = 1 if model == "claude-haiku-5-5" else 2
            out_tokens = measured[kind] * len(todo) * factor
            cost = ((system * len(todo) + user) * pin + out_tokens * pout) / 1e6
            out.append({"model": model, "method": kind, "requests": len(reqs), "to_send": len(todo),
                        "est_input_tokens": system * len(todo) + user, "est_output_tokens": int(out_tokens),
                        "est_cost_usd": cost})
    return out


# --- measures -------------------------------------------------------------------------------

def overlap_index(spans: pd.DataFrame) -> dict:
    """{(sentence_id, code): [(start, end)]} for fast overlap tests."""
    idx = {}
    for sid, code, s, e in zip(spans["sentence_id"], spans["code"], spans["start"], spans["end"]):
        idx.setdefault((sid, code), []).append((s, e))
    return idx


def covered(idx: dict, sid, code, start, end) -> bool:
    return any(s < end and start < e for s, e in idx.get((sid, code), []))


def agreement(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Share of the spans of `a` that a span of `b` overlaps with the same code."""
    if not len(a):
        return float("nan")
    idx = overlap_index(b)
    return sum(covered(idx, *x) for x in zip(a["sentence_id"], a["code"], a["start"], a["end"])) / len(a)


def reference_row(article: str, name: str, ref: pd.DataFrame, spans: pd.DataFrame) -> dict:
    n = len(ref)
    union = {i for i in range(n) if ref.at[i, "human_a"] or ref.at[i, "human_b"]}
    consensus = {i for i in range(n) if ref.at[i, "human_a"] and ref.at[i, "human_b"]}
    cells, span_rows, _ = cc.align(ref, spans)
    found = {i for i, c in enumerate(cells) if c == "✓"}
    u = cc.scores(found, len(spans), sum(1 for r in span_rows if r & union), union)
    c = cc.scores(found, len(spans), sum(1 for r in span_rows if r & consensus), consensus)
    extra = [s["text"] for s, r in zip(spans.to_dict("records"), span_rows) if not r & union]
    missed = [ref.at[i, "word"] for i in sorted(union - found)]
    return {"article": article, "coder": name, "spans": len(spans), "found": u["found"], "words": len(union),
            "extra": u["extra"], "precision_ref": u["P"], "recall_ref": u["R"], "F1": u["F1"], "F1_consensus": c["F1"],
            "extra_words": cc.with_counts(extra), "missed_words": cc.with_counts(missed)}


def counts_row(article: str, name: str, spans: pd.DataFrame, review: pd.DataFrame = None,
               ia: pd.DataFrame = None) -> dict:
    counts = spans["code"].value_counts()
    row = {"article": article, "coder": name, "spans": len(spans), **{c: int(counts.get(c, 0)) for c in kc.CODES}}
    if review is not None:
        idx = overlap_index(spans)
        member = review[[covered(idx, *x) for x in zip(review["sentence_id"], review["code"], review["start"],
                                                       review["end"])]]
        row.update({"review_n": len(member), "review_valid": int(member["valid"].sum()),
                    "precision": member["valid"].mean() if len(member) else float("nan")})
        lo, hi = wilson(row["review_valid"], row["review_n"])
        row.update({"precision_lo": lo, "precision_hi": hi})
    if ia is not None and ia is not spans:
        row.update({"ia_found": agreement(ia, spans), "ia_confirmed": agreement(spans, ia)})
    return row


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    import math
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def entry_diff(a: pd.DataFrame, b: pd.DataFrame, k: int = 12) -> tuple:
    """Spans of a absent from b (same position and code), counted by entry, and the reverse."""
    key = ["sentence_id", "start", "end", "code"]
    ka = set(map(tuple, a[key].itertuples(index=False, name=None)))
    kb = set(map(tuple, b[key].itertuples(index=False, name=None)))
    lost = Counter(f"{e} ({c})" for e, c, t in zip(a["entry"], a["code"], map(tuple, a[key].itertuples(
        index=False, name=None))) if t not in kb)
    gained = Counter(f"{e} ({c})" for e, c, t in zip(b["entry"], b["code"], map(tuple, b[key].itertuples(
        index=False, name=None))) if t not in ka)
    fmt = lambda c: ", ".join(f"{w} {n}" for w, n in c.most_common(k)) or "none"           # noqa: E731
    return sum(lost.values()), fmt(lost), sum(gained.values()), fmt(gained)


# --- PDF --------------------------------------------------------------------------------------

def write_pdf(path: Path, ref_rows: list, rows: list, diffs: dict, notes: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold = "Helvetica", "Helvetica-Bold"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        for b_, i_ in ((0, 0), (1, 0), (0, 1), (1, 1)):
            addMapping("DejaVu", b_, i_, "DejaVu-Bold" if b_ else "DejaVu")
        regular, bold = "DejaVu", "DejaVu-Bold"
    ink, grey, head = colors.HexColor("#1a1a1a"), colors.HexColor("#5f6368"), colors.HexColor("#e6ebf2")
    rule, accent, missing_bg = colors.HexColor("#9aa3ad"), colors.HexColor("#1c5cab"), colors.HexColor("#f3f3f1")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=15, leading=19, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.4, leading=11, textColor=grey),
        "h": ParagraphStyle("h", fontName=bold, fontSize=12, leading=15, spaceBefore=10, spaceAfter=4,
                            textColor=accent),
        "body": ParagraphStyle("b", fontName=regular, fontSize=8.8, leading=12, textColor=ink, spaceAfter=3),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.5, leading=9.2, textColor=ink),
        "hdr": ParagraphStyle("r", fontName=bold, fontSize=7.6, leading=9.2, textColor=ink),
    }

    def table(data, widths, extra=(), align_from=1):
        data = [[Paragraph(str(h), st["hdr"]) for h in data[0]]] + data[1:]
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                               ("BACKGROUND", (0, 0), (-1, 0), head), ("GRID", (0, 0), (-1, -1), 0.4, rule),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (align_from, 1), (-1, -1), "CENTER"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
                              + list(extra)))
        return t

    def pct(x):
        return "–" if x != x else f"{100 * x:.0f} %"

    def missing(article, coder):
        return notes["missing"].get((article, coder))

    story = [Paragraph("Benchmark: Naive, Upgrade, Upgrade +, Hybrid, IA (" + ", ".join(notes["model_labels"])
                       + ")", st["title"]),
             Paragraph(notes["subtitle"], st["sub"]), Spacer(1, 6)]
    story.append(table([["Coder", "What it does"]] + [[c, Paragraph(t, st["cell"])] for c, t in notes["coders"]],
                       [2.6, 22.0], align_from=9))
    if notes.get("status"):
        story += [Spacer(1, 4), Paragraph(notes["status"], st["body"])]

    # Courchaton
    story.append(Paragraph("Courchaton · against the human reference (development data)", st["h"]))
    data = [["Coder", "Spans", "Found (union of 50)", "Extra", "Precision", "Recall", "F1 union", "F1 consensus",
             "Missed words", "Extra words"]]
    extra = []
    for r in ref_rows:
        if r.get("not_run"):
            data.append([r["coder"], "not run", "", "", "", "", "", "", Paragraph(r["not_run"], st["cell"]), ""])
            extra.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), missing_bg))
            continue
        data.append([r["coder"], r["spans"], f"{r['found']}/{r['words']}", r["extra"], pct(r["precision_ref"]), pct(r["recall_ref"]),
                     f"{r['F1']:.2f}", f"{r['F1_consensus']:.2f}", Paragraph(r["missed_words"] or "–", st["cell"]),
                     Paragraph(r["extra_words"] or "–", st["cell"])])
    story.append(table(data, [3.2, 1.4, 2.2, 1.3, 1.8, 1.5, 1.5, 2.0, 5.2, 5.2], extra))
    story.append(Paragraph(notes["courchaton"], st["body"]))

    # Lyon and Fontainebleau
    for article in ("Lyon", "Fontainebleau"):
        story.append(Paragraph(f"{article} · {ROLE[article]}", st["h"]))
        head_row = ["Coder", "Spans"] + list(kc.CODES)
        if article == "Lyon":
            head_row += ["Sample spans", "Est. precision (95 % CI)"]
        head_row += [f"Spans of {notes['ia_ref']} it also finds", f"Its spans {notes['ia_ref']} also codes"]
        data, extra = [head_row], []
        for name in notes["order"]:
            r = next((x for x in rows if x["article"] == article and x["coder"] == name), None)
            if r is None:
                data.append([name, "not run"] + [""] * (len(head_row) - 3)
                            + [Paragraph(missing(article, name) or "", st["cell"])])
                extra.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), missing_bg))
                continue
            line = [name, r["spans"]] + [r[c] for c in kc.CODES]
            if article == "Lyon":
                ci = (f"{pct(r['precision'])} ({100 * r['precision_lo']:.0f}–{100 * r['precision_hi']:.0f})"
                      if r["review_n"] else "–")
                line += [r["review_n"], ci]
            line += [pct(r.get("ia_found", float("nan"))), pct(r.get("ia_confirmed", float("nan")))]
            data.append(line)
        widths = [3.2, 1.4] + [1.05] * 6 + ([1.8, 3.2] if article == "Lyon" else []) + [3.0, 3.0]
        story.append(table(data, widths, extra))
        lost_n, lost, gained_n, gained = diffs[article]
        story.append(Paragraph(f"<b>Upgrade → Upgrade +</b> (what the Lyon exclusions change): {lost_n} spans "
                               f"removed ({lost}); {gained_n} spans added ({gained}).", st["body"]))
        story.append(Paragraph(notes[article], st["body"]))

    if notes.get("costs"):
        story.append(Paragraph("Cost of the LLM runs (from the token counts returned by the API)", st["h"]))
        data = [["Model", "Method", "API requests", "Input tokens", "Cache read", "Output tokens", "Cost ($)",
                 "Time (s)"]]
        for c in notes["costs"]:
            data.append([c["model"], c["method"], c["requests"], f"{c['input']:,}", f"{c['cache_read']:,}",
                         f"{c['output']:,}", f"{c['cost']:.2f}", f"{c['seconds']:.1f}"])
        story.append(table(data, [3.2, 2.0, 2.0, 2.6, 2.6, 2.6, 1.8, 1.8]))
        story.append(Paragraph("Time: keyword methods = computing time on this machine, all articles; LLM methods "
                               "= sum of the durations of the API calls (requests run 4 at a time, so the waiting "
                               "time is about a quarter of it).", st["body"]))
        story.append(Paragraph("Prices of the Claude API per million tokens (input / output / cache read): Haiku 5.5 "
                               "0.10 / 0.50 / 0.01, Sonnet 5.5 2 / 10 / 0.10, Opus 5.5 4 / 20 / 0.20. Cache writes "
                               "are counted as plain input, so the cost is slightly under-estimated.", st["body"]))
    story.append(Paragraph("How to read and what to be careful about", st["h"]))
    for t in notes["caution"]:
        story.append(Paragraph(t, st["body"]))
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm, title="Benchmark of the coders",
                            author="Desirable Cities (UTSEUS EG01)")
    try:
        doc.build(story)
    except PermissionError:
        sys.exit(f"cannot write {path}: the file is open in another program (PDF viewer). Close it and run again.")


# --- main -------------------------------------------------------------------------------------

def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--models", nargs="+", default=None, help="LLMs of both Hybrid and IA")
    ap.add_argument("--hybrid-models", nargs="+", default=None, help="LLMs of the Hybrid method")
    ap.add_argument("--ia-models", nargs="+", default=None, help="LLMs of the IA method")
    ap.add_argument("--effort", default=hybrid.EFFORT)
    ap.add_argument("--offline", action="store_true", help="no API call: cached LLM answers only")
    ap.add_argument("--plan", action="store_true", help="only print what a run would send and cost; no call")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--articles", nargs="+", default=list(methods_mod.ARTICLES),
                    help="subset of articles (e.g. Courchaton Fontainebleau) to run the LLMs step by step")
    args = ap.parse_args()

    v3 = kc.load_list()
    v4 = kc.load_list(ROOT / "schema" / "keyword_list_v4.yaml")
    lists = {"v3": v3, "v3+": upgrade_plus_list(v3, v4)}
    hybrid_models = args.hybrid_models or args.models or ["claude-haiku-5-5"]
    ia_models = args.ia_models or args.models or ["claude-haiku-5-5"]
    all_models = list(dict.fromkeys(hybrid_models + ia_models))
    articles = {a: s for a, s in methods_mod.load_articles().items() if a in args.articles}
    requests = requests_of(articles, lists)
    if args.plan:
        total = 0.0
        print(f"prompts: hybrid {hybrid.PROMPT_VERSION}, ia {llm_coder.PROMPT_VERSION} (batches of "
              f"{llm_coder.BATCH} sentences), effort {args.effort}, fallback {'on' if hybrid.FALLBACK else 'off'}")
        for r in plan(all_models, requests, v3):
            if (r["method"] == "hybrid" and r["model"] not in hybrid_models) or (
                    r["method"] == "ia" and r["model"] not in ia_models):
                continue
            total += r["est_cost_usd"]
            print(f"  {r['model']:<18} {r['method']:<7} {r['to_send']:>4} of {r['requests']:>4} requests to send"
                  f"  ~{r['est_input_tokens']:>9,} in  ~{r['est_output_tokens']:>9,} out  ~${r['est_cost_usd']:.2f}")
        print(f"  estimated total: ~${total:.2f} (estimate, not a quote)")
        return

    judges = [(m, hybrid.make_judge(m, args.effort, hybrid.CACHE, args.offline)) for m in hybrid_models]
    coders = [(m, llm_coder.make_coder(v3, m, args.effort, llm_coder.CACHE, args.offline)) for m in ia_models]
    order = BASE + [f"Hybrid · {label(m)}" for m in hybrid_models] + [f"IA · {label(m)}" for m in ia_models]
    ia_ref = f"IA · {label(ia_models[-1])}"
    review = pd.read_csv(methods_mod.ARTICLES["Lyon"]["review"])

    ref_rows, rows, diffs, missing_notes, all_spans, statuses, keyword_seconds = [], [], {}, {}, [], {}, {}
    for article, sentences in articles.items():
        runs, notes_run = run_coders(sentences, article, lists, judges, coders, args.workers)
        for k, v in notes_run.items():
            if k.endswith(" seconds"):
                keyword_seconds[(article, k[:-8])] = v
            elif k.endswith(" status"):
                statuses[(article, k[:-7])] = v
            else:
                missing_notes[(article, k)] = v
        for name, spans in runs.items():
            all_spans.append(spans.assign(article=article, coder=name))
        if article == "Courchaton":
            ref = cc.load_reference(methods_mod.ARTICLES["Courchaton"]["reference"], sentences)
            for name in order:
                if name in runs:
                    ref_rows.append(reference_row(article, name, ref, runs[name]))
                else:
                    ref_rows.append({"article": article, "coder": name, "not_run": missing_notes[(article, name)]})
            ai = ref[ref["ai"] == 1]
            ref_rows.append({"article": article, "coder": "IA on PDFs (19 Nov)", "spans": len(ai),
                             "found": int(((ref["ai"] == 1) & ((ref["human_a"] == 1) | (ref["human_b"] == 1))).sum()),
                             "words": int(((ref["human_a"] == 1) | (ref["human_b"] == 1)).sum()),
                             "extra": 0, "precision_ref": 1.0, "recall_ref": 1.0, "F1": 1.0,
                             "F1_consensus": 2 * 45 / (50 + 45), "extra_words": "", "missed_words": ""})
        else:
            ia = runs.get(ia_ref)
            for name in order:
                if name in runs:
                    rows.append(counts_row(article, name, runs[name], review if article == "Lyon" else None, ia))
        diffs[article] = entry_diff(runs["Upgrade"], runs["Upgrade +"])

    hc, ic = cache_rows(hybrid.CACHE), cache_rows(llm_coder.CACHE)
    costs = []
    for kind, models_k, reqs, rows_c, version in (
            ("Hybrid", hybrid_models, requests["hybrid"], hc, hybrid.PROMPT_VERSION),
            ("IA", ia_models, requests["ia"], ic, llm_coder.PROMPT_VERSION)):
        for m in models_k:
            used = [rows_c[k] for k in (hybrid.cache_key(m, r, version) for r in reqs) if k in rows_c]
            if used:
                i, o, c, cost = usage_cost(m, used)
                costs.append({"model": label(m), "method": kind, "requests": len(used), "input": i, "output": o,
                              "cache_read": c, "cost": cost, "seconds": usage_cost.seconds})
    for name in BASE:
        costs.insert(BASE.index(name), {"model": "—", "method": name, "requests": 0, "input": 0, "output": 0,
                                        "cache_read": 0, "cost": 0.0,
                                        "seconds": sum(v for (a, n), v in keyword_seconds.items() if n == name)})

    rv = review[review["code"].isin(kc.RESPONSE_CODES)]
    notes = {
        "model_labels": [f"Hybrid {label(m)}" for m in hybrid_models] + [f"IA {label(m)}" for m in ia_models],
        "order": order,
        "ia_ref": ia_ref,
        "costs": costs,
        "subtitle": "Courchaton rev. 234797520 (human reference) · Lyon rev. 241583218 (baseline) · Fontainebleau "
                    f"rev. 240633341 (test) · Hybrid: {', '.join(hybrid_models)} · IA: {', '.join(ia_models)} · effort "
                    f"{args.effort}, prompts "
                    f"{hybrid.PROMPT_VERSION} / {llm_coder.PROMPT_VERSION}, no fallback · "
                    f"{date.today().strftime('%d %B %Y').lstrip('0')}",
        "coders": [
            ("Naive", "Keyword list v3 (341 words), each word as written: whole word, case-insensitive, optional "
                      "final s/x. No rule, no exclusion; responses linked to every environment of the sentence."),
            ("Upgrade", "List v3 + rules v2: forms (plural, feminine, conjugation, same-stem words), proper names, "
                        "and the exclusions of homonyms and fixed expressions written while coding Courchaton "
                        "(list v3 encoding; three of them come from an early Fontainebleau trial: a été after "
                        "avoir, se placer, ouvrage d'art)."),
            ("Upgrade +", "Upgrade + the exclusions and corrected forms found on Lyon (v4 encoding: fleurs de lys, "
                          "Michelin stars, places assises, permis de construire, third-person verbs only…), "
                          "on the same 341 words: the 45 words v4 adds and the 3 it removes are not used."),
            ("Hybrid · model", "Upgrade +, then the LLM checks every response (E, A, R) against rules D4 and D6 and "
                               "drops the false ones; environments are those of Upgrade +."),
            ("IA · model", f"The LLM codes the whole article like a human coder, by batches of {llm_coder.BATCH} "
                           "sentences, with the manual (rules v2), list v3 and the same precisions on rules D4 and "
                           "D6 as the Hybrid; it chooses the words itself."),
        ],
        "status": "" if not missing_notes else ("<b>Some LLM runs are missing</b> (no API key, or --offline "
                                                "without cached answers): they are marked 'not run'."),
        "courchaton": "The reference is the union of the two human coders (50 words; 45 in their consensus). The "
                      "rules and the Upgrade exclusions were written on this article, so it measures how well each "
                      "coder reproduces the manual, not how it generalises. 'IA on PDFs' is the first AI coding "
                      "(Claude given the three PDFs, 19 November), kept for comparison.",
        "Lyon": f"Est. precision: share of valid spans among the spans of the review sample that the coder also "
                f"codes (a coder covers a sampled span when one of its spans overlaps it with the same code). The "
                f"sample was drawn from the keyword coders' spans and judged by Claude Opus: it cannot see words "
                f"that only an IA finds, and it is not independent of the Claude models. In the sample, "
                f"{int(rv['valid'].sum())} of {len(rv)} response spans were valid.",
        "Fontainebleau": f"No reference: the two last columns compare each coder with {ia_ref} (the most capable "
                         "model run). An IA is not a reference either: agreement is not accuracy.",
        "caution": [
            "Upgrade + has the union of the exclusions written on Courchaton and of those written on Lyon. Half "
            "of them were written by looking at the errors on Lyon, so Lyon cannot judge them fairly (they were "
            "made to fix exactly those errors): its Lyon figures are optimistic. Fontainebleau, where no "
            "exclusion was written, shows what they bring on a new article (Upgrade → Upgrade + lines).",
            "The LLM methods depend on a model version and a prompt; answers are cached in data/llm/ with the "
            "exact requests, so a run can be audited and repeated. Each model was run once: the variation between "
            "repeated runs is not measured. The prompts are in docs/llm_prompts.md. "
            + "; ".join(f"{c} {a}: {s}" for (a, c), s in statuses.items()),
            "No PID matrix here: only spans and codes are compared.",
        ],
        "missing": missing_notes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ref_rows + rows).to_csv(OUT.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    pd.concat(all_spans).to_csv(OUT.parent / "benchmark_spans.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(costs).to_csv(OUT.parent / "benchmark_costs.csv", index=False, encoding="utf-8-sig")
    write_pdf(OUT.with_suffix(".pdf"), ref_rows, rows, diffs, notes)
    print(f"-> {OUT}.pdf / .csv")
    for r in ref_rows:
        if r.get("not_run"):
            print(f"  Courchaton    {r['coder']:<20} not run: {r['not_run']}")
        else:
            print(f"  Courchaton    {r['coder']:<20} spans {r['spans']:>4}  found {r['found']}/{r['words']}"
                  f"  extra {r['extra']:>2}  F1 {r['F1']:.2f}")
    for r in rows:
        p = f"  precision {r['precision']:.2f}" if "precision" in r and r["precision"] == r["precision"] else ""
        print(f"  {r['article']:<13} {r['coder']:<20} spans {r['spans']:>4}  "
              + " ".join(f"{c} {r[c]}" for c in kc.CODES) + p)
    for c in costs:
        print(f"  cost {c['model']:<11} {c['method']:<9} {c['requests']:>4} requests  ${c['cost']:.3f}"
              f"  {c['seconds']:.1f} s")
    for k, v in missing_notes.items():
        print(f"  not run {k}: {v}")


if __name__ == "__main__":
    main()
