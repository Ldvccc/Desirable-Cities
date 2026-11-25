"""Compare keyword list v3 and v4 on the two pilot articles (Courchaton, Lyon).

For each article, each list and each method (A, A+, A-form):
    Courchaton  against the human reference (coded with list v3)
    Lyon        no human reference yet: number of spans per code, and the
                precision estimated on a random sample of spans reviewed by
                Claude (data/reference/lyon_fr_241583218_review_sample.csv)

Output: docs/list_versions_comparison.pdf   the report
        docs/list_versions_comparison.csv   all the numbers of the report
        docs/lyon_spans.csv                 every span of every method and list on Lyon

Usage:
    python src/compare_list_versions.py
"""
import math
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

import compare_coders as cc
import keyword_coder as kc

ROOT = kc.ROOT
LISTS = {"v3": ROOT / "schema" / "keyword_list_v3.yaml", "v4": ROOT / "schema" / "keyword_list_v4.yaml"}
LYON = ROOT / "data" / "reference" / "lyon_fr_241583218.json"
REVIEW = ROOT / "data" / "reference" / "lyon_fr_241583218_review_sample.csv"
OUT = ROOT / "docs" / "list_versions_comparison"
LYON_SPANS = ROOT / "docs" / "lyon_spans.csv"
LABELS = cc.METHOD_LABELS                                    # a -> A, a_plus -> A+, a_form -> A-form


def wilson(k: int, n: int, z: float = 1.96):
    """95 % Wilson interval of a proportion k/n."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def run(sentences: pd.DataFrame, lists: dict) -> dict:
    """{(list, method): (spans, seconds)}"""
    out = {}
    for lab, kw in lists.items():
        for method in kc.METHODS:
            t0 = time.perf_counter()
            spans = kc.code_sentences(sentences, kw, method)
            out[(lab, method)] = (spans, time.perf_counter() - t0)
    return out


def courchaton_rows(ref: pd.DataFrame, runs: dict) -> list:
    n = len(ref)
    subsets = {"union": {i for i in range(n) if ref.at[i, "human_a"] or ref.at[i, "human_b"]},
               "consensus": {i for i in range(n) if ref.at[i, "human_a"] and ref.at[i, "human_b"]}}
    rows = []
    for (lab, method), (spans, secs) in runs.items():
        cells, span_rows, _ = cc.align(ref, spans)
        found = {i for i, c in enumerate(cells) if c == "✓"}
        row = {"article": "Courchaton", "list": lab, "method": LABELS[method], "spans": len(spans), "seconds": secs}
        for name, subset in subsets.items():
            matched = sum(1 for r in span_rows if r & subset)
            sc = cc.scores(found, len(spans), matched, subset)
            row.update({f"{name}_found": sc["found"], f"{name}_words": len(subset), f"{name}_extra": sc["extra"],
                        f"{name}_P": sc["P"], f"{name}_R": sc["R"], f"{name}_F1": sc["F1"]})
        extra = [s["text"] for s, r in zip(spans.to_dict("records"), span_rows) if not r & subsets["union"]]
        row["extra_words"] = cc.with_counts(extra)
        rows.append(row)
    return rows


def lyon_rows(runs: dict, review: pd.DataFrame) -> list:
    rows = []
    key = ["sentence_id", "start", "end", "code"]
    for (lab, method), (spans, secs) in runs.items():
        coded = set(map(tuple, spans[key].itertuples(index=False, name=None)))
        member = review[[tuple(r) in coded for r in review[key].itertuples(index=False, name=None)]]
        k, n = int(member["valid"].sum()), len(member)
        lo, hi = wilson(k, n)
        p = k / n if n else float("nan")
        counts = spans["code"].value_counts()
        rows.append({"article": "Lyon", "list": lab, "method": LABELS[method], "spans": len(spans), "seconds": secs,
                     **{c: int(counts.get(c, 0)) for c in kc.CODES},
                     "review_n": n, "review_valid": k, "precision": p, "precision_lo": lo, "precision_hi": hi,
                     "valid_spans_est": p * len(spans) if n else float("nan")})
    return rows


def span_diff(a: pd.DataFrame, b: pd.DataFrame) -> tuple:
    """Spans of a not in b and of b not in a (same position and code), by entry."""
    key = ["sentence_id", "start", "end", "code"]
    ka = set(map(tuple, a[key].itertuples(index=False, name=None)))
    kb = set(map(tuple, b[key].itertuples(index=False, name=None)))
    lost = a[[tuple(r) not in kb for r in a[key].itertuples(index=False, name=None)]]
    gained = b[[tuple(r) not in ka for r in b[key].itertuples(index=False, name=None)]]
    return lost, gained


def by_entry(spans: pd.DataFrame, k: int = 14) -> str:
    c = Counter(f"{e} ({code})" for e, code in zip(spans["entry"], spans["code"]))
    return ", ".join(f"{w} {n}" for w, n in c.most_common(k))


def list_summary(lists: dict) -> list:
    rows = []
    for lab, kw in lists.items():
        entries = list(kc.iter_entries(kw))
        counts = Counter(e["section"] for e in entries)
        rows.append([lab, str(kw.get("version")), len(entries)] + [counts.get(c, 0) for c in kc.CODES])
    return rows


# --- PDF -----------------------------------------------------------------------------

def write_pdf(path: Path, lists: dict, crows: list, lrows: list, diff: tuple, changes: dict, counts4: dict,
              review_n: int) -> None:
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold = "Helvetica", "Helvetica-Bold"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        addMapping("DejaVu", 0, 0, "DejaVu")
        addMapping("DejaVu", 1, 0, "DejaVu-Bold")
        addMapping("DejaVu", 0, 1, "DejaVu")
        addMapping("DejaVu", 1, 1, "DejaVu-Bold")
        regular, bold = "DejaVu", "DejaVu-Bold"
    ink, grey, head = colors.HexColor("#1a1a1a"), colors.HexColor("#666666"), colors.HexColor("#e6ebf2")
    green = colors.HexColor("#eaf4ea")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=13.5, leading=17, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.5, leading=11, textColor=grey),
        "h": ParagraphStyle("h", fontName=bold, fontSize=11.5, leading=15, spaceBefore=9, spaceAfter=5),
        "body": ParagraphStyle("b", fontName=regular, fontSize=9, leading=12.2),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7, leading=9, textColor=grey),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.4, leading=9),
    }
    base = [("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.8),
            ("FONTNAME", (0, 0), (-1, 0), bold), ("BACKGROUND", (0, 0), (-1, 0), head),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa3ad")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6)]

    def table(data, widths, extra=(), align_from=1):
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle(base + [("ALIGN", (align_from, 1), (-1, -1), "CENTER"),
                                      ("ALIGN", (align_from, 0), (-1, 0), "CENTER")] + list(extra)))
        return t

    def pct(x):
        return "–" if x != x else f"{100 * x:.0f} %"

    story = [
        Paragraph("Keyword list v3 and v4 on Courchaton and Lyon", st["title"]),
        Paragraph(f"Rules for manual coding v2 · Courchaton rev. 234797520 · Lyon rev. 241583218 · "
                  f"{date.today().strftime('%d %B %Y').lstrip('0')}", st["sub"]),
        Spacer(1, 6),
        Paragraph("List v3 is the list the human coders used. List v4 is a <b>proposal</b> built from what the two "
                  "pilot articles showed: three entries removed, 45 generic words added, and new exclusions for the "
                  "homonyms seen in Lyon (all changes listed at the end). The three methods are run with each list: "
                  "<b>A</b> (Koinos tags, naive), <b>A+</b> (full list, naive) and <b>A-form</b> (list + rules v2).",
                  st["body"]),
        Paragraph("The lists", st["h"]),
        table([["List", "Version", "Entries"] + list(kc.CODES)] + list_summary(lists),
              [1.6, 1.6, 1.6] + [1.2] * 6),
    ]

    # Courchaton
    story.append(Paragraph("Courchaton: against the human reference", st["h"]))
    data = [["List", "Method", "Spans", "Union: found", "Extra", "P", "R", "F1", "Consensus F1"]]
    extra_style = []
    for r in crows:
        data.append([r["list"], r["method"], r["spans"], f"{r['union_found']}/{r['union_words']}", r["union_extra"],
                     pct(r["union_P"]), pct(r["union_R"]), f"{r['union_F1']:.2f}", f"{r['consensus_F1']:.2f}"])
        if r["method"] == "A-form":
            extra_style.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), green))
    story.append(table(data, [1.2, 1.6, 1.3, 2.1, 1.2, 1.4, 1.4, 1.3, 2.2], extra_style))
    form4 = next(r for r in crows if r["list"] == "v4" and r["method"] == "A-form")
    story += [Spacer(1, 3), Paragraph(
        "The reference was coded with list v3, so every word added in v4 counts as an error here by construction. "
        f"A-form with v4 still finds all the reference words; its extra words are words of v4 that v3 did not "
        f"contain: {form4['extra_words'] or 'none'}.", st["body"])]

    # Lyon
    story.append(Paragraph("Lyon: spans and estimated precision", st["h"]))
    data = [["List", "Method", "Spans"] + list(kc.CODES) + ["Sample", "Precision (95 % CI)", "Valid (est.)"]]
    extra_style = []
    for r in lrows:
        ci = "–" if r["review_n"] == 0 else f"{pct(r['precision'])} ({pct(r['precision_lo'])}–{pct(r['precision_hi'])})"
        est = "–" if r["valid_spans_est"] != r["valid_spans_est"] else f"{r['valid_spans_est']:.0f}"
        data.append([r["list"], r["method"], r["spans"]] + [r[c] for c in kc.CODES] + [r["review_n"], ci, est])
        if r["method"] == "A-form":
            extra_style.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), green))
    story.append(table(data, [0.9, 1.4, 1.2] + [0.95] * 6 + [1.4, 3.6, 1.9], extra_style))
    lost, gained = diff
    f3 = next(r for r in lrows if r["list"] == "v3" and r["method"] == "A-form")
    f4 = next(r for r in lrows if r["list"] == "v4" and r["method"] == "A-form")
    story += [Spacer(1, 3), Paragraph(
        f"No human coding of Lyon exists yet. Precision is estimated on a simple random sample of {review_n} spans "
        "drawn from all the spans of the six runs and reviewed by Claude against the rules v2 (a span is valid when "
        "a coder applying the rules would code it with that code); each run is scored on the sampled spans it "
        "contains. <b>This is not a human reference</b>: it gives the order of magnitude, not a result for the paper. "
        f"With v4, A-form codes {f4['spans']} spans instead of {f3['spans']} and its estimated precision goes from "
        f"{pct(f3['precision'])} to {pct(f4['precision'])}.", st["body"]),
        Spacer(1, 3),
        Paragraph(f"<b>A-form, spans lost from v3 to v4</b> ({len(lost)}): {by_entry(lost)}.", st["body"]),
        Spacer(1, 2),
        Paragraph(f"<b>A-form, spans gained from v3 to v4</b> ({len(gained)}): {by_entry(gained)}.", st["body"]),
        Spacer(1, 4),
        Paragraph("<b>Caution.</b> Lyon was used to build v4 (the additions come from its vocabulary and the new "
                  "exclusions from its errors), and the same model reviewed the sample: the Lyon figures for v4 are "
                  "optimistic. A third article, not seen while building v4 and coded by the humans, is needed to "
                  "test it. Recall cannot be estimated without a full coding.", st["body"])]

    # Changes
    story += [PageBreak(), Paragraph("Changes from v3 to v4", st["h"])]
    data = [["Change", "Word", "Code", "Matches", "Reason"]]
    for kind in ("removed", "added"):
        for c in changes.get(kind, []):
            if kind == "removed":
                matches = c.get("evidence", "")
            else:
                ly, co = counts4.get(("Lyon", c["fr"]), 0), counts4.get(("Courchaton", c["fr"]), 0)
                matches = f"{ly} / {co}"
            data.append([kind, c["fr"], c.get("code", ""), Paragraph(str(matches), st["cell"]),
                         Paragraph(c["reason"], st["cell"])])
    for c in changes.get("re-encoded", []):
        data.append(["encoding", c["fr"], "", Paragraph(c.get("evidence", ""), st["cell"]),
                     Paragraph(c["reason"], st["cell"])])
    story.append(table(data, [1.7, 2.4, 1.0, 3.4, 9.3], align_from=2))
    story += [Spacer(1, 3), Paragraph(
        "Matches: removed = matches of A-form with list v3; added = matches of A-form with list v4 (Lyon / "
        "Courchaton); encoding = what was seen in the pilot articles. Every change is in "
        "schema/keyword_list_v4.yaml (field changes) and must be validated by the coders and by the author of the "
        "framework before v4 is used.", st["note"])]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title="Keyword list v3 and v4",
                            author="Desirable Cities (UTSEUS EG01)")
    doc.build(story)


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    lists = {lab: kc.load_list(p) for lab, p in LISTS.items()}

    cour = cc.load_sentences(cc.ARTICLE, "70178")
    ref = cc.load_reference(cc.REFERENCE, cour)
    cruns = run(cour, lists)
    crows = courchaton_rows(ref, cruns)

    lyon = cc.load_sentences(LYON, "69123")
    lruns = run(lyon, lists)
    review = pd.read_csv(REVIEW)
    lrows = lyon_rows(lruns, review)
    diff = span_diff(lruns[("v3", "a_form")][0], lruns[("v4", "a_form")][0])

    counts4 = {}
    for name, runs in (("Lyon", lruns), ("Courchaton", cruns)):
        for e, n in runs[("v4", "a_form")][0]["entry"].value_counts().items():
            counts4[(name, e)] = int(n)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(crows + lrows).to_csv(OUT.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    long = pd.concat([s.assign(list=lab) for (lab, _), (s, _) in lruns.items()])
    long.to_csv(LYON_SPANS, index=False, encoding="utf-8-sig")
    write_pdf(OUT.with_suffix(".pdf"), lists, crows, lrows, diff, lists["v4"].get("changes", {}), counts4, len(review))

    print(f"-> {OUT}.pdf / .csv, {LYON_SPANS}")
    for r in crows:
        print(f"  Courchaton {r['list']} {r['method']:<7} spans {r['spans']:>4}  union {r['union_found']}/{r['union_words']}"
              f" extra {r['union_extra']:>2}  F1 {r['union_F1']:.2f}  consensus F1 {r['consensus_F1']:.2f}")
    for r in lrows:
        print(f"  Lyon       {r['list']} {r['method']:<7} spans {r['spans']:>4}  reviewed {r['review_n']:>3}"
              f"  precision {r['precision']:.2f} [{r['precision_lo']:.2f}-{r['precision_hi']:.2f}]"
              f"  valid≈{r['valid_spans_est']:.0f}")
    print(f"  A-form v3 -> v4 on Lyon: {len(diff[0])} spans lost, {len(diff[1])} gained")


if __name__ == "__main__":
    main()
