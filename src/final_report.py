"""Write docs/results_benchmark.pdf: the five coding methods, what each relies on, and how they compare in
quality, cost and time on Courchaton, Lyon and Fontainebleau.

The reference is IA · Opus 5.5 on every article. The human codings only test it:
    Courchaton  two coders (union), docs/benchmark.csv
    Lyon        two coders who split the article, data/reference/lyon_fr_241583218_human.csv; scored as given
                and after correcting two unambiguous slips (possessive "son", "été" after avoir) with the rules
                of the manual

Reads the outputs of src/benchmark.py (run it first): docs/benchmark.csv, docs/benchmark_spans.csv,
docs/benchmark_costs.csv. Writes docs/results_benchmark.pdf, docs/results_benchmark_chart.png,
docs/results_vs_opus.csv and docs/lyon_human_comparison.csv.

Usage:
    python src/final_report.py
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import compare_coders as cc
import compare_methods as methods_mod
import keyword_coder as kc

ROOT = kc.ROOT
DOCS = ROOT / "docs"
OUT = DOCS / "results_benchmark.pdf"
HUMAN = ROOT / "data" / "reference" / "lyon_fr_241583218_human.csv"
REF = "IA · Opus 5.5"
HYB = "Hybrid · Haiku 5.5"
HUM = "Human coding"
METHODS = ["Naive", "Upgrade", "Upgrade +", HYB, REF]
ARTICLES = ["Courchaton", "Lyon", "Fontainebleau"]
PARTS = (("all", None), ("env", kc.ENV_CODES), ("resp", kc.RESPONSE_CODES)) + tuple((c, [c]) for c in kc.CODES)
BLUE, ORANGE, AQUA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#1a1a1a", "#5f6368", "#e3e6ea"


# --- measures --------------------------------------------------------------------------------

def index(spans: pd.DataFrame) -> dict:
    idx = {}
    for sid, code, s, e in zip(spans["sentence_id"], spans["code"], spans["start"], spans["end"]):
        idx.setdefault((sid, code), []).append((s, e))
    return idx


def share_covered(a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Share of the spans of a that a span of b overlaps with the same code."""
    if not len(a):
        return float("nan")
    idx = index(b)
    hit = sum(any(s < e2 and s2 < e for s2, e2 in idx.get((sid, code), []))
              for sid, code, s, e in zip(a["sentence_id"], a["code"], a["start"], a["end"]))
    return hit / len(a)


def versus(method: pd.DataFrame, ref: pd.DataFrame, codes=None) -> dict:
    """Precision, recall and F1 of `method` against `ref` (same word region, same code)."""
    if codes:
        method, ref = method[method["code"].isin(codes)], ref[ref["code"].isin(codes)]
    r, p = share_covered(ref, method), share_covered(method, ref)
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return {"recall": r, "precision": p, "f1": f, "n": len(method), "n_ref": len(ref)}


def corrected_human(human: pd.DataFrame, texts: dict) -> tuple:
    """The human coding without its two unambiguous slips against rule I4 of the manual: the possessive
    'son' (no determiner before it) and 'été' as the participle of être (a form of avoir before it), tested
    with keyword_coder.require_ok. Returns (corrected spans, removed spans)."""
    drop = []
    for i, r in human.iterrows():
        text = texts[r["sentence_id"]]
        if r["entry"] == "son" and not kc.require_ok("det", text, r["start"]):
            drop.append(i)
        elif r["entry"] == "été" and not kc.require_ok("ete", text, r["start"]):
            drop.append(i)
    return human.drop(index=drop), human.loc[drop]


def load() -> dict:
    bench = pd.read_csv(DOCS / "benchmark.csv")
    spans = pd.read_csv(DOCS / "benchmark_spans.csv", dtype={"pid": str})
    costs = pd.read_csv(DOCS / "benchmark_costs.csv")

    # the reference: IA · Opus on every article
    vs_opus, rows = {}, []
    for article in ARTICLES:
        s = spans[spans["article"] == article]
        ref = s[s["coder"] == REF]
        for m in METHODS[:-1]:
            ms = s[s["coder"] == m]
            if ms.empty or ref.empty:
                continue
            for part, codes in PARTS:
                v = versus(ms, ref, codes)
                vs_opus[(article, m, part)] = v
                rows.append({"article": article, "method": m, "part": part, **v})
    pd.DataFrame(rows).to_csv(DOCS / "results_vs_opus.csv", index=False, encoding="utf-8-sig")

    # the test of the reference: the human coding of Lyon
    human = pd.read_csv(HUMAN, dtype={"pid": str})
    lyon = methods_mod.load_articles()["Lyon"]
    fixed, removed = corrected_human(human, dict(zip(lyon["sentence_id"], lyon["text"])))
    vs_human, rows = {}, []
    s = spans[spans["article"] == "Lyon"]
    for m in METHODS:
        ms = s[s["coder"] == m]
        for ref_name, ref in (("raw", human), ("corrected", fixed)):
            for part, codes in PARTS:
                v = versus(ms, ref, codes)
                vs_human[(m, ref_name, part)] = v
                rows.append({"method": m, "reference": ref_name, "part": part, **v})
    pd.DataFrame(rows).to_csv(DOCS / "lyon_human_comparison.csv", index=False, encoding="utf-8-sig")

    import pid_matrix as pm

    cour = methods_mod.load_articles()["Courchaton"]
    human_cour = pm.reference_spans(cc.load_reference(methods_mod.ARTICLES["Courchaton"]["reference"], cour))
    for article, hs in (("Courchaton", human_cour), ("Lyon", human)):
        ref = spans[(spans["article"] == article) & (spans["coder"] == REF)]
        for part, codes in PARTS:
            vs_opus[(article, HUM, part)] = versus(hs, ref, codes)

    opus = s[s["coder"] == REF]
    idx = index(opus)
    missed = human[[not any(a < e and st < b for a, b in idx.get((sid, c), []))
                     for sid, c, st, e in zip(human["sentence_id"], human["code"], human["start"], human["end"])]]
    slips_missed = missed.index.isin(removed.index).sum()
    return {"bench": bench, "costs": costs, "human": human, "removed": removed, "vs_opus": vs_opus,
            "vs_human": vs_human, "opus_missed": len(missed), "slips_missed": int(slips_missed)}


# --- chart -----------------------------------------------------------------------------------

def chart(d: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    methods = METHODS[:-1]
    series = (("Courchaton", AQUA), ("Lyon", BLUE), ("Fontainebleau", ORANGE))
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.3), sharey=True)
    for ax, (part, title) in zip(axes, (("all", "All words"), ("resp", "Responses only (E, A, R)"))):
        h = 0.26
        for k, (article, color) in enumerate(series):
            vals = [d["vs_opus"].get((article, m, part), {}).get("f1", float("nan")) for m in methods]
            pos = [i + (k - 1) * (h + 0.02) for i in range(len(methods))]
            bars = ax.barh(pos, vals, height=h, color=color, label=article, zorder=2)
            for b, v in zip(bars, vals):
                if v == v:
                    ax.text(v + 0.012, b.get_y() + b.get_height() / 2, f"{v:.2f}", va="center", fontsize=6.8,
                            color=INK)
        ax.set_title(title, fontsize=9.5, color=INK, loc="left")
        ax.set_xlim(0, 1.1)
        ax.set_yticks(range(len(methods)))
        ax.set_yticklabels(methods, fontsize=8.5, color=INK)
        ax.invert_yaxis()
        ax.tick_params(axis="x", labelsize=7.5, colors=MUTED, length=0)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.set_xlabel("F1 against IA · Opus 5.5 (reference)", fontsize=8, color=MUTED)
    handles, labels_ = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_, fontsize=8, frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=200)
    plt.close(fig)


# --- PDF -------------------------------------------------------------------------------------

def write_pdf(d: dict, path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (CondPageBreak, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    regular, bold = "Helvetica", "Helvetica-Bold"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        for b_, i_ in ((0, 0), (1, 0), (0, 1), (1, 1)):
            addMapping("DejaVu", b_, i_, "DejaVu-Bold" if b_ else "DejaVu")
        regular, bold = "DejaVu", "DejaVu-Bold"
    ink, grey, head = colors.HexColor(INK), colors.HexColor(MUTED), colors.HexColor("#e6ebf2")
    rule, accent, soft = colors.HexColor("#9aa3ad"), colors.HexColor("#1c5cab"), colors.HexColor("#f3f6fa")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=17, leading=21, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.5, leading=11, textColor=grey),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=12.5, leading=16, spaceBefore=11, spaceAfter=4,
                             textColor=accent),
        "body": ParagraphStyle("b", fontName=regular, fontSize=9, leading=12.4, textColor=ink, spaceAfter=3),
        "bullet": ParagraphStyle("u", fontName=regular, fontSize=9, leading=12.4, textColor=ink, leftIndent=12,
                                 bulletIndent=2, spaceAfter=2),
        "key": ParagraphStyle("k", fontName=regular, fontSize=9.2, leading=12.8, textColor=ink, leftIndent=12,
                              bulletIndent=2, spaceAfter=3),
        "box": ParagraphStyle("x", fontName=regular, fontSize=8.6, leading=11.6, textColor=ink, backColor=soft,
                              borderPadding=(5, 7, 5, 7), spaceBefore=4, spaceAfter=8),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.6, leading=9.4, textColor=ink),
        "hdr": ParagraphStyle("r", fontName=bold, fontSize=7.6, leading=9.4, textColor=ink),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7.4, leading=9.6, textColor=grey, spaceAfter=4),
    }

    def P(t, s="body"):
        return Paragraph(t, st[s])

    def bullets(items, style="bullet"):
        return [Paragraph(t, st[style], bulletText="•") for t in items]

    def table(data, widths, extra=(), align_from=1):
        data = [[Paragraph(str(h_), st["hdr"]) for h_ in data[0]]] + data[1:]
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                               ("BACKGROUND", (0, 0), (-1, 0), head), ("GRID", (0, 0), (-1, -1), 0.4, rule),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (align_from, 1), (-1, -1), "CENTER"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
                              + list(extra)))
        return t

    def pct(x):
        return "–" if x != x else f"{100 * x:.0f} %"

    bench, costs, vo, vh = d["bench"], d["costs"], d["vs_opus"], d["vs_human"]

    def b(article, coder, key):
        r = bench[(bench["article"] == article) & (bench["coder"] == coder)]
        return r.iloc[0][key] if len(r) and key in r and r.iloc[0][key] == r.iloc[0][key] else float("nan")

    def cost_of(method):
        key = {HYB: ("Haiku 5.5", "Hybrid"), REF: ("Opus 5.5", "IA")}.get(method, ("—", method))
        r = costs[(costs["model"] == key[0]) & (costs["method"] == key[1])]
        return (r.iloc[0]["cost"], r.iloc[0]["seconds"], int(r.iloc[0]["requests"])) if len(r) else (0.0, 0.0, 0)

    def o(article, m, part="all", k="f1"):
        return vo.get((article, m, part), {}).get(k, float("nan"))

    def h(m, part="all", k="f1", ref="raw"):
        return vh.get((m, ref, part), {}).get(k, float("nan"))

    ia_cost, ia_time, ia_req = cost_of(REF)
    hy_cost, _, hy_req = cost_of(HYB)
    human, removed = d["human"], d["removed"]
    n_son = int((removed["entry"] == "son").sum())
    n_ete = int((removed["entry"] == "été").sum())
    L, F = "Lyon", "Fontainebleau"

    story = [
        Paragraph("Coding commune articles with the Desirable Cities framework: five methods compared",
                  st["title"]), Spacer(1, 3),
        P(f"Desirable Cities · UTSEUS EG01 · keyword list v3 · rules for manual coding v2 · Courchaton rev. "
          f"234797520 · Lyon rev. 241583218 · Fontainebleau rev. 240633341 · "
          f"{date.today().strftime('%d %B %Y').lstrip('0')}", "sub"), Spacer(1, 6),
        P("Each method reads the sentences of a French Wikipedia article and marks the words of the framework: "
          "three <b>environments</b> (N natural, C cultural, B constructural) and three <b>responses</b> of people "
          "(E emotions, A actions, R reflections). The <b>reference is IA · Opus 5.5</b>, a large LLM that codes "
          "the article like an expert coder; the human codings of Courchaton and Lyon are used to test it. Three "
          "keyword methods and a hybrid with a small LLM are compared with this reference, on their quality, "
          "their cost and their time."),
        Paragraph("Key results", st["h1"]),
    ]
    story += bullets([
        f"<b>The reference holds against the humans.</b> On Lyon, Opus agrees with the human coding at F1 "
        f"{h(REF):.2f} ({h(REF, ref='corrected'):.2f} once {n_son + n_ete} clear human slips are removed), "
        f"responses {h(REF, 'resp'):.2f}; on Courchaton it finds {int(b('Courchaton', REF, 'found'))} of the 50 "
        f"human words with no extra word. It is the closest of the five methods to the humans.",
        f"<b>The keyword method with rules gets most of the way for free.</b> Against Opus, Upgrade + reaches F1 "
        f"{o(L, 'Upgrade +'):.2f} on Lyon and {o(F, 'Upgrade +'):.2f} on Fontainebleau (environments "
        f"{o(L, 'Upgrade +', 'env'):.2f} and {o(F, 'Upgrade +', 'env'):.2f}), in seconds; Naive stays at "
        f"{o(L, 'Naive'):.2f} and {o(F, 'Naive'):.2f}.",
        f"<b>The responses make the difference.</b> Keyword methods code every response word: against Opus, "
        f"Upgrade + has a response precision of {pct(o(L, 'Upgrade +', 'resp', 'precision'))} on Lyon. The Hybrid "
        f"with Haiku raises it to {pct(o(L, HYB, 'resp', 'precision'))} but drops real responses too (recall "
        f"{pct(o(L, HYB, 'resp', 'recall'))}): response F1 {o(L, 'Upgrade +', 'resp'):.2f} → "
        f"{o(L, HYB, 'resp'):.2f} on Lyon, {o(F, 'Upgrade +', 'resp'):.2f} → {o(F, HYB, 'resp'):.2f} on "
        f"Fontainebleau.",
        f"<b>Cost and time.</b> Keyword methods: free, seconds. Hybrid with Haiku: ${hy_cost:.2f} for the three "
        f"articles. Opus: ${ia_cost:.2f} ({ia_req} requests, {ia_time / 60:.0f} min of API calls), i.e. about "
        f"$0.002 per sentence.",
    ], "key")

    story.append(Paragraph("The five methods and what they rely on", st["h1"]))
    rows = [["Method", "Relies on", "How it works", "Needs"],
            ["Naive", "Keyword list v3 (341 words)",
             "Looks for each list word as written (whole word, optional final s/x). No rule, no exclusion.",
             "Nothing"],
            ["Upgrade", "List v3 + rules for manual coding v2 + exclusions written on Courchaton",
             "Generates the forms of each word (plural, feminine, conjugation, same-stem words); skips proper "
             "names; removes listed homonyms and fixed expressions (il a été élu, son maire, prendre place…).",
             "Nothing"],
            ["Upgrade +", "Upgrade + the exclusions written on Lyon",
             "Same 341 words; adds the exclusions found on Lyon (fleurs de lys, Michelin stars, places assises, "
             "permis de construire, verbs in the third person only…).", "Nothing"],
            [HYB, "Upgrade + and a small LLM (Claude Haiku 5.5)",
             "Keeps the environments of Upgrade +; sends each sentence with a response word to the LLM, which "
             "says whether people really feel, do or think it (rules D4, D6) and drops it otherwise.",
             "API key; one short request per sentence with a response"],
            [f"{REF} (reference)", "A large LLM (Claude Opus 5.5) with the manual and list v3",
             "Codes the whole article like an expert coder, 20 sentences per request: decides itself every form "
             "and derived word of the list, and judges homonyms and names from the context.",
             "API key; one long request per 20 sentences"]]
    data = [rows[0]] + [[P(f"<b>{r[0]}</b>", "cell")] + [P(x, "cell") for x in r[1:]] for r in rows[1:]]
    story.append(table(data, [2.7, 3.7, 7.6, 3.4], align_from=9))
    story.append(P("Both LLM methods receive the same precisions on rules D4 and D6, and their answers follow a fixed "
                   "JSON schema. Prompts: docs/llm_prompts.md. Every answer is cached with its request in data/llm/, "
                   "so the runs can be audited and repeated at no cost.", "note"))

    story.append(Paragraph("Why Opus is the reference, and how it was tested", st["h1"]))
    story += bullets([
        "Hand coding a whole article is long and error-prone: the Lyon coders split the article in two halves "
        f"(sentences 0–599 and 600–1,493), and their coding contains clear slips against the manual itself: "
        f"{n_son} possessive <i>son</i> (<i>son territoire</i>) and {n_ete} <i>été</i> after <i>avoir</i> "
        f"(<i>a été construit</i>), the very examples the manual excludes.",
        f"Opus applies the same manual and list to every article, the same way. Against the human coding of "
        f"Lyon ({len(human):,} words) it reaches precision {pct(h(REF, 'all', 'precision'))} and recall "
        f"{pct(h(REF, 'all', 'recall'))}; of the {d['opus_missed']} human words it does not code, "
        f"{d['slips_missed']} are those slips. Its responses agree at F1 {h(REF, 'resp'):.2f}.",
        "Every other method is scored against Opus on the three articles: precision = share of its words that "
        "Opus also codes, recall = share of the Opus words it finds (same word region, same code), F1 = their "
        "harmonic mean.",
    ])

    img = DOCS / "results_benchmark_chart.png"
    chart(d, img)
    story += [CondPageBreak(10 * cm), Paragraph("How close each method gets to the reference", st["h1"]),
              Image(str(img), width=17.4 * cm, height=17.4 * cm * 3.3 / 7.6), Spacer(1, 2),
              P("F1 against IA · Opus 5.5 (same word region and same code). Right: responses only, the part of the "
                "coding that needs a judgment of meaning. Courchaton has a single response.", "note")]

    story.append(Paragraph("Quality, cost and time", st["h1"]))
    data = [["Method", "Courch. F1", "Lyon F1", "Font. F1", "Lyon env. F1", "Lyon resp. F1 (P / R)",
             "Font. resp. F1", "Cost, 3 articles ($)", "Time (s)"]]
    for m in METHODS[:-1] + [HUM, REF]:
        c, t, _ = cost_of(m)
        if m == REF:
            data.append([P(f"<b>{m}</b>", "cell"), "ref.", "ref.", "ref.", "ref.", "reference", "ref.", f"{c:.2f}",
                         f"{t:.0f}"])
            continue
        if m == HUM:
            data.append([P(f"<b>{m}</b>", "cell"), f"{o('Courchaton', m):.2f}", f"{o(L, m):.2f}", "–",
                         f"{o(L, m, 'env'):.2f}",
                         f"{o(L, m, 'resp'):.2f} ({pct(o(L, m, 'resp', 'precision'))} / "
                         f"{pct(o(L, m, 'resp', 'recall'))})", "–", "–", "1200–1500*"])
            continue
        data.append([P(f"<b>{m}</b>", "cell"), f"{o('Courchaton', m):.2f}", f"{o(L, m):.2f}", f"{o(F, m):.2f}",
                     f"{o(L, m, 'env'):.2f}",
                     f"{o(L, m, 'resp'):.2f} ({pct(o(L, m, 'resp', 'precision'))} / "
                     f"{pct(o(L, m, 'resp', 'recall'))})",
                     f"{o(F, m, 'resp'):.2f}", f"{c:.2f}",
                     "n/r" if (t == 0 and m == HYB) else f"{t:.1f}" if t < 10 else f"{t:.0f}"])
    story.append(table(data, [2.8, 1.6, 1.3, 1.3, 1.5, 3.2, 1.4, 1.6, 1.6]))
    story.append(P("All F1 are against IA · Opus 5.5. Human coding: two coders (union) on Courchaton, two coders "
                   "on two halves of the article on Lyon, as given (no correction); not available for Fontainebleau; "
                   "* about 20 to 25 min per coder on Courchaton (38 sentences), Lyon not recorded. Time: computing time for the keyword methods; sum of the API "
                   "call durations for the LLM methods (run 4 to 6 at a time, so the wait is shorter); n/r = not "
                   "recorded (the Hybrid answers were obtained before call durations were logged). Costs come from "
                   "the token counts returned by the API (cache writes counted as plain input).", "note"))

    data = [["Method"] + list(kc.CODES) + ["All"]]
    for m in METHODS[:-1] + [HUM]:
        data.append([m] + [f"{o(L, m, c):.2f}" for c in kc.CODES] + [f"{o(L, m):.2f}"])
    story += [Spacer(1, 4), KeepTogether([P("<b>F1 per code against the reference, Lyon</b>"),
                                          table(data, [3.4] + [1.6] * 7)])]

    story.append(Paragraph("What it means", st["h1"]))
    story += bullets([
        "<b>Environments</b> (most of the coding) are found almost the same way by every method with rules: a "
        "closed list with forms and exclusions is enough, and it costs nothing.",
        "<b>Responses</b> need meaning (does someone really feel, act or think?). Keyword methods code every "
        "response word, true or false; a small LLM as a filter is too strict and also removes true ones; the "
        "large LLM, which reads each sentence, gets both right.",
        f"<b>For all communes</b>: Upgrade + for the environments at no cost, and Opus where responses matter or "
        f"on a sample of communes (about $0.002 per sentence). The Hybrid with Haiku gives mixed results on "
        f"responses (better on Lyon, {o(L, 'Upgrade +', 'resp'):.2f} → {o(L, HYB, 'resp'):.2f}; worse on "
        f"Fontainebleau, {o(F, 'Upgrade +', 'resp'):.2f} → {o(F, HYB, 'resp'):.2f}): a stronger judge or a "
        f"clearer prompt on borderline cases is the next thing to test.",
        f"<b>The Lyon exclusions</b> (Upgrade + over Upgrade) change little: F1 {o(L, 'Upgrade'):.2f} → "
        f"{o(L, 'Upgrade +'):.2f} on Lyon, {o(F, 'Upgrade'):.2f} → {o(F, 'Upgrade +'):.2f} on Fontainebleau.",
    ])
    story.append(Paragraph("Limits", st["h1"]))
    story += bullets([
        "Opus is tested on two articles only (Courchaton, the article the rules were written on, and Lyon); its "
        "remaining disagreements with the humans are not all human slips.",
        "Opus was run once: the variation between repeated runs is not measured; a second run would show how "
        "stable the reference is.",
        "Upgrade + and list v4 were built by looking at Lyon, which favours them slightly on Lyon.",
        "No PID matrix in this comparison: only words and codes.",
    ])
    story += [Spacer(1, 4), Paragraph(
        "Reproduce: python src/benchmark.py --hybrid-models claude-haiku-5-5 --ia-models claude-opus-5-5 "
        "(cached answers cost nothing), then python src/final_report.py. Scores: docs/results_vs_opus.csv, "
        "docs/lyon_human_comparison.csv; detailed tables: docs/benchmark.pdf.", st["box"])]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.7 * cm, rightMargin=1.7 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title="Five coding methods compared",
                            author="Desirable Cities (UTSEUS EG01)")
    try:
        doc.build(story)
    except PermissionError:
        sys.exit(f"cannot write {path}: the file is open in another program (PDF viewer). Close it and run again.")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    d = load()
    write_pdf(d, OUT)
    print(f"-> {OUT}")
    print(f"  Opus vs humans (Lyon): F1 {d['vs_human'][(REF, 'raw', 'all')]['f1']:.2f}, misses "
          f"{d['opus_missed']} human words of which {d['slips_missed']} slips")
    for (article, m, part), v in d["vs_opus"].items():
        if part in ("all", "resp"):
            print(f"  {article:<13} {m:<20} {part:<4} F1 {v['f1']:.2f} P {v['precision']:.2f} R {v['recall']:.2f}")


if __name__ == "__main__":
    main()
