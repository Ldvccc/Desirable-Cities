"""Compare all the keyword methods on the pilot articles (list v3).

    A                  Koinos tags, naive
    A+                 full list, naive
    A-form             list + rules v2
    Heritage           A-form + links inherited from the previous sentence (heritage.py)
    Hybrid             A-form + LLM check of the responses and of their links (hybrid.py)
    Hybrid + Heritage  both

Articles (ARTICLES): Courchaton is compared with the human reference, at span
level and at PID-cell level (one cell = one sentence x environment x
response). Lyon and Fontainebleau have no human coding: spans, responses and
PID cells are counted, and the environment spans of Lyon are scored on its
review sample.

Output: docs/methods_comparison.pdf    the report
        docs/methods_comparison.csv    one row per article and method
        docs/hybrid_audit_<article>.csv every decision of the LLM, with its reason
        docs/pid_matrices.pdf / .csv   regenerated with every method and article (pid_matrix.py)

Usage:
    python src/compare_methods.py                       # Hybrid calls the Claude API for answers not cached
    python src/compare_methods.py --offline             # cached answers only
    python src/compare_methods.py --model <id> --offline   # answers cached under another model id
"""
import argparse
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

import compare_coders as cc
import compare_list_versions as clv
import heritage
import hybrid
import keyword_coder as kc
import pid_matrix as pm

ROOT = kc.ROOT
OUT = ROOT / "docs" / "methods_comparison"
METHODS = ["A", "A+", "A-form", "Heritage", "Hybrid", "Hybrid + Heritage"]
ARTICLES = {
    "Courchaton": {"path": cc.ARTICLE, "insee": "70178", "rev": "234797520", "reference": cc.REFERENCE},
    "Lyon": {"path": clv.LYON, "insee": "69123", "rev": "241583218", "review": clv.REVIEW},
    "Fontainebleau": {"path": ROOT / "data" / "reference" / "fontainebleau_fr_240633341.json", "insee": "77186",
                      "rev": "240633341"},
}
REVISIONS = {name: a["rev"] for name, a in ARTICLES.items()}


def load_articles() -> dict:
    return {name: cc.load_sentences(a["path"], a["insee"]) for name, a in ARTICLES.items()}


def run_all(sentences: pd.DataFrame, kw: dict, judge=None, workers: int = 4) -> tuple:
    """({method: spans}, {method: seconds}, hybrid audit or None, note on Hybrid)."""
    runs, secs = {}, {}
    for method, label in cc.METHOD_LABELS.items():
        t0 = time.perf_counter()
        runs[label] = kc.code_sentences(sentences, kw, method)
        secs[label] = time.perf_counter() - t0
    t0 = time.perf_counter()
    runs["Heritage"] = heritage.inherit_links(runs["A-form"], sentences)
    secs["Heritage"] = secs["A-form"] + time.perf_counter() - t0
    audit, note = None, ""
    if judge is not None:
        try:
            t0 = time.perf_counter()
            runs["Hybrid"], audit = hybrid.hybrid_spans(runs["A-form"], sentences, judge, workers)
            secs["Hybrid"] = secs["A-form"] + time.perf_counter() - t0
            runs["Hybrid + Heritage"] = heritage.inherit_links(runs["Hybrid"], sentences)
            secs["Hybrid + Heritage"] = secs["Hybrid"]
        except (hybrid.MissingAnswers, hybrid.JudgeUnavailable) as e:
            note = str(e)
    return runs, secs, audit, note


def prf(found: int, n_pred: int, n_ref: int) -> dict:
    p = found / n_pred if n_pred else float("nan")
    r = found / n_ref if n_ref else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else 0.0
    return {"P": p, "R": r, "F1": f}


def reference_rows(article: str, ref: pd.DataFrame, ref_spans: pd.DataFrame, runs: dict, secs: dict) -> list:
    n = len(ref)
    union = {i for i in range(n) if ref.at[i, "human_a"] or ref.at[i, "human_b"]}
    consensus = {i for i in range(n) if ref.at[i, "human_a"] and ref.at[i, "human_b"]}
    ref_cells = pm.cell_set(ref_spans)
    rows = []
    for label, spans in runs.items():
        cells, span_rows, _ = cc.align(ref, spans)
        found = {i for i, c in enumerate(cells) if c == "✓"}
        u = cc.scores(found, len(spans), sum(1 for r in span_rows if r & union), union)
        c = cc.scores(found, len(spans), sum(1 for r in span_rows if r & consensus), consensus)
        cs = pm.cell_set(spans)
        pid = prf(len(cs & ref_cells), len(cs), len(ref_cells))
        rows.append({"article": article, "method": label, "spans": len(spans), "seconds": secs[label],
                     "responses": int(spans["code"].isin(kc.RESPONSE_CODES).sum()),
                     "union_found": u["found"], "union_words": len(union), "union_extra": u["extra"],
                     "union_P": u["P"], "union_R": u["R"], "union_F1": u["F1"], "consensus_F1": c["F1"],
                     "pid_cells": len(cs), "pid_ref_cells": len(ref_cells), "pid_found": len(cs & ref_cells),
                     "pid_P": pid["P"], "pid_R": pid["R"], "pid_F1": pid["F1"]})
    return rows


def article_rows(article: str, runs: dict, secs: dict, n_sentences: int, review: pd.DataFrame = None) -> list:
    """Counts for an article without human reference; precision of the
    environment spans on the review sample when there is one."""
    key = ["sentence_id", "start", "end", "code"]
    rows = []
    for label, spans in runs.items():
        m = pm.pid_matrix(spans, n_sentences)
        counts = spans["code"].value_counts()
        core = sum(m["cells"][(e, r)]["sentences"] for e in kc.ENV_CODES for r in kc.RESPONSE_CODES)
        row = {"article": article, "method": label, "spans": len(spans), "seconds": secs[label],
               **{c: int(counts.get(c, 0)) for c in kc.CODES},
               "responses": int(spans["code"].isin(kc.RESPONSE_CODES).sum()),
               "pid_sentences": m["linked_sentences"], "pid_cells": core,
               "unlinked_sentences": m["unlinked_sentences"], "inherited_sentences": m["inherited_sentences"],
               "env_review_n": 0, "env_review_valid": 0}
        if review is not None:
            coded = set(map(tuple, spans[key].itertuples(index=False, name=None)))
            member = review[[tuple(r) in coded for r in review[key].itertuples(index=False, name=None)]]
            env = member[member["code"].isin(kc.ENV_CODES)]
            row.update({"env_review_n": len(env), "env_review_valid": int(env["valid"].sum())})
        rows.append(row)
    return rows


# --- PDF ----------------------------------------------------------------------------------

def write_pdf(path: Path, crows: list, orows: list, audits: dict, inherited: dict, notes: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold = "Helvetica", "Helvetica-Bold"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        for b, i in ((0, 0), (1, 0), (0, 1), (1, 1)):
            addMapping("DejaVu", b, i, "DejaVu-Bold" if b else "DejaVu")
        regular, bold = "DejaVu", "DejaVu-Bold"
    ink, grey, head = colors.HexColor("#1a1a1a"), colors.HexColor("#5f6368"), colors.HexColor("#e6ebf2")
    new_bg, rule = colors.HexColor("#eef4fb"), colors.HexColor("#9aa3ad")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=14, leading=18, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.3, leading=10.8, textColor=grey),
        "h": ParagraphStyle("h", fontName=bold, fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=4),
        "body": ParagraphStyle("b", fontName=regular, fontSize=8.8, leading=11.9),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7.2, leading=9.2, textColor=grey),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.3, leading=8.9),
        "hdr": ParagraphStyle("r", fontName=bold, fontSize=7.4, leading=8.9),
    }

    def table(data, widths, extra=(), align_from=1):
        data = [[Paragraph(str(h), st["hdr"]) for h in data[0]]] + data[1:]
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.6),
                               ("BACKGROUND", (0, 0), (-1, 0), head), ("GRID", (0, 0), (-1, -1), 0.4, rule),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (align_from, 1), (-1, -1), "CENTER"),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]
                              + list(extra)))
        return t

    def pct(x):
        return "–" if x != x else f"{100 * x:.0f} %"

    def new_rows(rows, offset=1):
        return [("BACKGROUND", (0, i + offset), (-1, i + offset), new_bg)
                for i, r in enumerate(rows) if r["method"] in ("Heritage", "Hybrid", "Hybrid + Heritage")]

    story = [Paragraph(notes["title"], st["title"]), Paragraph(notes["subtitle"], st["sub"]), Spacer(1, 6)]
    story.append(table([["Method", "Environments (N, C, B)", "Responses (E, A, R)", "PID links"],
                        *[[m, Paragraph(a, st["cell"]), Paragraph(b, st["cell"]), Paragraph(c, st["cell"])]
                          for m, a, b, c in notes["methods"]]],
                       [2.6, 4.6, 5.0, 5.6], extra=[("BACKGROUND", (0, 4), (-1, -1), new_bg)], align_from=9))
    if notes.get("hybrid_status"):
        story += [Spacer(1, 4), Paragraph(notes["hybrid_status"], st["body"])]

    # article with a human reference
    story.append(Paragraph("Courchaton: against the human reference", st["h"]))
    data = [["Method", "Spans", "Resp.", "Found (union)", "Extra", "F1 union", "F1 cons.",
             "PID cells", "PID found", "PID F1"]]
    for r in crows:
        data.append([r["method"], r["spans"], r["responses"], f"{r['union_found']}/{r['union_words']}",
                     r["union_extra"], f"{r['union_F1']:.2f}", f"{r['consensus_F1']:.2f}", r["pid_cells"],
                     f"{r['pid_found']}/{r['pid_ref_cells']}", f"{r['pid_F1']:.2f}"])
    story.append(table(data, [3.1, 1.4, 1.4, 2.2, 1.3, 1.6, 1.6, 1.6, 1.7, 1.5], new_rows(crows)))
    story += [Spacer(1, 3), Paragraph(notes["courchaton"], st["body"])]

    # articles without reference
    names = list(dict.fromkeys(r["article"] for r in orows))
    story.append(Paragraph(f"{' and '.join(names)}: spans, responses and PID cells (no human reference)", st["h"]))
    data = [["Article", "Method", "Spans", "E", "A", "R", "Sentences with a PID cell", "PID cells (9 cells)",
             "Unlinked resp. (sent.)", "Inherited links (sent.)", "Env. precision (sample)"]]
    extra = new_rows(orows)
    for i, r in enumerate(orows):
        envp = (f"{pct(r['env_review_valid'] / r['env_review_n'])} ({r['env_review_valid']}/{r['env_review_n']})"
                if r["env_review_n"] else "–")
        data.append([r["article"] if i == 0 or orows[i - 1]["article"] != r["article"] else "", r["method"],
                     r["spans"], r["E"], r["A"], r["R"], r["pid_sentences"], r["pid_cells"],
                     r["unlinked_sentences"], r["inherited_sentences"], envp])
        if i and orows[i - 1]["article"] != r["article"]:
            extra.append(("LINEABOVE", (0, i + 1), (-1, i + 1), 1.2, ink))
    story.append(table(data, [2.5, 2.7, 1.3, 0.75, 0.75, 0.75, 1.8, 1.5, 1.7, 1.7, 2.3], extra, align_from=2))
    story += [Spacer(1, 3), Paragraph(notes["others"], st["body"])]

    # Hybrid detail, one block per article
    for article, audit in audits.items():
        if audit is None or not len(audit):
            continue
        block = [Paragraph(f"What the LLM decided on {article} (Hybrid)", st["h"])]
        data = [["Code", "Candidates", "Kept", "Dropped", "Kept, links narrowed", "Kept, no environment"]]
        for code in kc.RESPONSE_CODES:
            a = audit[audit["code"] == code]
            kept = a[a["valid"] == True]                                              # noqa: E712
            narrowed = sum(1 for x, y in zip(kept["pid_a_form"], kept["pid_hybrid"])
                           if pm.links(y) != pm.links(x) and pm.links(y))
            data.append([code, len(a), len(kept), int((a["valid"] == False).sum()),           # noqa: E712
                         narrowed, int((kept["pid_hybrid"].isin(["", "0"])).sum())])
        block.append(table(data, [1.4, 2.2, 1.6, 1.8, 3.4, 3.4]))
        story.append(KeepTogether(block))
        dropped = Counter(f"{e} ({c})" for e, c, v in zip(audit["entry"], audit["code"], audit["valid"]) if v is False)
        kept = Counter(f"{e} ({c})" for e, c, v in zip(audit["entry"], audit["code"], audit["valid"]) if v is True)
        story += [Spacer(1, 3),
                  Paragraph("<b>Dropped</b>: " + ", ".join(f"{w} {n}" for w, n in dropped.most_common(18)) + ".",
                            st["body"]), Spacer(1, 2),
                  Paragraph("<b>Kept</b>: " + ", ".join(f"{w} {n}" for w, n in kept.most_common(18)) + ".",
                            st["body"]), Spacer(1, 4)]
        ex = audit[audit["valid"] == True].head(12)                                       # noqa: E712
        data = [["Word", "Code", "Linked to", "Reason given by the LLM"]]
        for r in ex.itertuples():
            data.append([r.text, r.code, Paragraph(r.linked_words or "no environment", st["cell"]),
                         Paragraph(r.reason, st["cell"])])
        story += [Paragraph("Examples of kept responses (first 12 in the article)", st["body"]), Spacer(1, 2),
                  table(data, [2.6, 1.2, 4.5, 9.5], align_from=1)]

    # Heritage detail
    story.append(Paragraph("Links inherited from the previous sentence (Heritage)", st["h"]))
    data = [["Article", "Word", "Code", "Inherited from the previous sentence", "Kept by Hybrid", "Sentence"]]
    for article, rows in inherited.items():
        for r in rows:
            data.append([article, r["text"], r["code"], Paragraph(r["inherited"], st["cell"]), r["hybrid"],
                         Paragraph(r["sentence"][:170], st["cell"])])
    if len(data) == 1:
        data.append(["–", "–", "–", "none", "–", ""])
    story.append(table(data, [2.1, 2.3, 1.3, 3.6, 1.8, 6.9], align_from=2))
    story += [Spacer(1, 3), Paragraph(notes["heritage"], st["body"])]

    story += [Paragraph("Caution", st["h"])] + [Paragraph(t, st["body"]) for t in notes["caution"]]
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.4 * cm, title="Keyword methods on the pilot articles",
                            author="Desirable Cities (UTSEUS EG01)")
    try:
        doc.build(story)
    except PermissionError:
        sys.exit(f"cannot write {path}: the file is open in another program (PDF viewer). Close it and run again.")


# --- main ---------------------------------------------------------------------------------

def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=hybrid.MODEL, help="LLM of the Hybrid method (cache key)")
    ap.add_argument("--effort", default=hybrid.EFFORT)
    ap.add_argument("--cache", default=str(hybrid.CACHE))
    ap.add_argument("--offline", action="store_true", help="Hybrid: cached answers only, no API call")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    kw = kc.load_list()
    judge = hybrid.make_judge(args.model, args.effort, Path(args.cache), args.offline)
    articles = load_articles()
    runs, audits, notes_missing, crows, orows = {}, {}, {}, [], []
    for name, sentences in articles.items():
        conf = ARTICLES[name]
        runs[name], secs, audits[name], notes_missing[name] = run_all(sentences, kw, judge, args.workers)
        if "reference" in conf:
            ref = cc.load_reference(conf["reference"], sentences)
            crows += reference_rows(name, ref, pm.reference_spans(ref), runs[name], secs)
        else:
            review = pd.read_csv(conf["review"]) if "review" in conf else None
            orows += article_rows(name, runs[name], secs, len(sentences), review)

    texts = {sid: t for s in articles.values() for sid, t in zip(s["sentence_id"], s["text"])}
    hybrid_ran = all("Hybrid" in r for r in runs.values())
    missing = next((m for m in notes_missing.values() if m), "")
    inherited = {}
    for name, r in runs.items():
        s = r["Heritage"]
        s = s[s["link"] == "inherited"]
        kept = set(zip(r["Hybrid"]["sentence_id"], r["Hybrid"]["start"], r["Hybrid"]["code"])) if "Hybrid" in r else None
        inherited[name] = [{"text": x.text, "code": x.code, "sentence": texts[x.sentence_id],
                            "inherited": " · ".join(f"{c} {', '.join(w)}" for c, w in
                                                    heritage.parse_inherited(x.inherited).items()),
                            "hybrid": "–" if kept is None else
                            ("yes" if (x.sentence_id, x.start, x.code) in kept else "no")}
                           for x in s.itertuples()]
    all_inherited = [x for rows in inherited.values() for x in rows]
    n_kept = sum(x["hybrid"] == "yes" for x in all_inherited)
    by_article = Counter(name for name, rows in inherited.items() for _ in rows)

    is_session = args.model.startswith("session:")
    model_text = (f"answers written by {args.model.split(':', 1)[1]} inside a Claude Code session with the prompt "
                  f"{hybrid.PROMPT_VERSION} (PREVIEW, not an API run)" if is_session else
                  f"{args.model}, effort {args.effort}, prompt {hybrid.PROMPT_VERSION}")
    review = pd.read_csv(clv.REVIEW)
    resp_review = review[review["code"].isin(kc.RESPONSE_CODES)]
    candidates = {r["article"]: r["responses"] for r in orows if r["method"] == "A-form"}
    names = " · ".join(f"{n} rev. {a['rev']}" for n, a in ARTICLES.items())
    notes = {
        "title": "Keyword methods on " + ", ".join(ARTICLES) + ": A, A+, A-form, Heritage, Hybrid",
        "subtitle": f"Keyword list v3 · rules for manual coding v2 · {names} · Hybrid: {model_text} · "
                    f"{date.today().strftime('%d %B %Y').lstrip('0')}",
        "methods": [
            ("A", "Koinos tags, as written", "Koinos tags, as written", "every environment of the sentence"),
            ("A+", "full list, as written", "full list, as written", "every environment of the sentence"),
            ("A-form", "list + rules v2 (forms, homonyms, names)", "same, form test only (no D4/D6)",
             "every environment of the sentence (D7)"),
            ("Heritage", "as A-form", "as A-form",
             "as A-form; a response with no environment inherits those of the previous sentence when its "
             "sentence refers back (y, là, celui-ci, sentence-initial Il/Elle…)"),
            ("Hybrid", "as A-form", "A-form candidates checked by an LLM (D4, D6); invalid ones dropped",
             "chosen by the LLM among the environment words of the sentence"),
            ("Hybrid + Heritage", "as A-form", "as Hybrid", "as Hybrid, then inheritance as Heritage"),
        ],
        "hybrid_status": ("" if hybrid_ran else
                          f"<b>Hybrid was not run</b>: {missing}. Run python src/compare_methods.py with an "
                          "Anthropic credential (ANTHROPIC_API_KEY or ant auth login)."),
        "courchaton": "Courchaton is development data: the rules and A-form were tuned on it. Its reference has a "
                      "single response, célèbre (R) linked to vergers and vignes (N): the PID columns compare the "
                      "cells (sentence × environment × response) of each method with that one cell.",
        "others": f"Env. precision = share of the environment spans of the Lyon review sample (200 random spans "
                  f"judged by Claude against the rules) that are valid; it is the same for every method built on "
                  f"A-form, which keep its environments. Fontainebleau has no sample. The response spans are not "
                  f"scored: in the Lyon sample only {int(resp_review['valid'].sum())} of the {len(resp_review)} "
                  f"response spans were valid, and the Hybrid's judge is the same model as the reviewer, so a score "
                  f"would not be independent. Fontainebleau was used earlier as a smoke test of A-form (a few "
                  f"exclusions come from it), so it is not entirely unseen.",
        "heritage": f"Heritage only acts on a response that has no environment in its own sentence. It adds "
                    f"{len(all_inherited)} link(s): "
                    + ", ".join(f"{by_article.get(n, 0)} in {n}" for n in ARTICLES)
                    + (f"; the Hybrid keeps {n_kept} of these {len(all_inherited)} responses." if hybrid_ran else ".")
                    + " Most unlinked responses are false ones (projet, travail, critique for a person), or their "
                    "sentence refers back with a word that is not a marker (cette pratique), or the previous "
                    "sentence has no environment word, so they inherit nothing.",
        "caution": [
            ("<b>The Hybrid figures are a preview.</b> No API credential was available, so the LLM answers were "
             "written by the same model (Claude Opus 5.5) inside the Claude Code session, following the prompt of "
             "hybrid.py word for word, and stored in the cache under the model id "
             f"'{args.model}'. They are not reproducible like an API run, and the same model reviewed the Lyon "
             "sample. Rerun with a credential before quoting them." if is_session else
             "The Hybrid answers are stored in data/llm/hybrid_answers.jsonl with the exact request, model and "
             "prompt version, so the run can be audited and repeated."),
            "Lyon and Fontainebleau have no human coding, so no method can be scored on their responses or PID "
            "cells. The fastest way to measure Hybrid and Heritage is a human judgment of the response "
            "candidates (" + ", ".join(f"{n}: {k} spans" for n, k in candidates.items())
            + "): valid or not, and linked to which environment.",
        ],
    }
    if not hybrid_ran:
        notes["caution"] = notes["caution"][1:]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(crows + orows).to_csv(OUT.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    for name, audit in audits.items():
        if audit is not None and len(audit) and "reference" not in ARTICLES[name]:
            audit.to_csv(OUT.parent / f"hybrid_audit_{name.lower()}.csv", index=False, encoding="utf-8-sig")
    write_pdf(OUT.with_suffix(".pdf"), crows, orows, {n: a for n, a in audits.items() if "reference" not in
                                                       ARTICLES[n]}, inherited, notes)
    print(f"-> {OUT}.pdf / .csv" + ("" if hybrid_ran else f"  (Hybrid not run: {missing})"))
    for r in crows:
        print(f"  {r['article']:<13} {r['method']:<18} spans {r['spans']:>4}  F1 union {r['union_F1']:.2f}"
              f"  PID cells {r['pid_cells']}  PID F1 {r['pid_F1']:.2f}")
    for r in orows:
        print(f"  {r['article']:<13} {r['method']:<18} spans {r['spans']:>4}  E/A/R {r['E']}/{r['A']}/{r['R']}"
              f"  PID sentences {r['pid_sentences']:>3}  cells {r['pid_cells']:>3}  inherited {r['inherited_sentences']}")

    pm.pilot_report(judge=judge, workers=args.workers, hybrid_label=model_text)


if __name__ == "__main__":
    main()
