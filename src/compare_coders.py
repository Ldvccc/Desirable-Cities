"""Compare the keyword coding of the human coders, the AI and algorithm A
(variants A, A+, A-form) on one pilot article, word by word.

Input : data/reference/courchaton_fr_234797520.json   MediaWiki API answer (the coded revision)
        data/reference/courchaton_fr_reference.csv    one row per word coded by a human or the AI:
                                                      n, word, keyword, code, human_a, human_b, ai
Output: docs/courchaton_comparison.pdf   the comparison table (summary, agreement, word by word)
        docs/courchaton_comparison.csv   the word-by-word table

The reference words are located in the article in reading order. A method
finds a reference word when one of its spans overlaps it with the same code.

Usage:
    python src/compare_coders.py
    python src/compare_coders.py --article <api.json> --reference <ref.csv> --out docs/<name>
"""
import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

import keyword_coder as kc
import split_sentences as ss
import wikipedia_text as wt

ROOT = Path(__file__).resolve().parent.parent
ARTICLE = ROOT / "data" / "reference" / "courchaton_fr_234797520.json"
REFERENCE = ROOT / "data" / "reference" / "courchaton_fr_reference.csv"
OUT = ROOT / "docs" / "courchaton_comparison"

METHOD_LABELS = {"a": "A", "a_plus": "A+", "a_form": "A-form"}
METHOD_NAMES = {"a": "Algorithm A (Koinos tags, naive)",
                "a_plus": "Algorithm A+ (full list v3, naive)",
                "a_form": "Algorithm A-form (list v3 + rules v2)"}
HUMAN_INFO = {"human_a": ("Human A (reference)", "≈ 20 min", "–"),
              "human_b": ("Human B (reference)", "≈ 25 min", "–"),
              "ai": ("AI (Claude, API)", "≈ 1–3 min*", "≈ 30–60 k**")}


# --- data ----------------------------------------------------------------------------

def load_sentences(article: Path, insee: str = "00000") -> pd.DataFrame:
    data = json.loads(article.read_text(encoding="utf-8"))
    record = wt.parse_api_response(data, "")
    row = wt.build_row({"insee": insee, "qid": "", "langue": "fr", "url": ""}, record, None)
    return pd.DataFrame(ss.article_sentences(row))


def load_reference(path: Path, sentences: pd.DataFrame) -> pd.DataFrame:
    """Reference rows with their position (sentence_id, start, end), found in
    reading order."""
    ref = pd.read_csv(path, dtype={"word": str})
    texts, ids = list(sentences["text"]), list(sentences["sentence_id"])
    si, pos, located = 0, 0, []
    for r in ref.itertuples(index=False):
        pattern = re.compile(rf"(?<!\w){re.escape(r.word)}(?!\w)")
        while True:
            if si >= len(texts):
                raise ValueError(f"reference word #{r.n} {r.word!r} not found after the previous one")
            m = pattern.search(texts[si], pos)
            if m:
                located.append({"sentence_id": ids[si], "start": m.start(), "end": m.end()})
                pos = m.end()
                break
            si, pos = si + 1, 0
    ref = pd.concat([ref, pd.DataFrame(located)], axis=1)
    ref["base_code"] = ref["code"].str.split(">").str[0]
    return ref


def overlaps(a, b) -> bool:
    return a["sentence_id"] == b["sentence_id"] and a["start"] < b["end"] and b["start"] < a["end"]


def align(ref: pd.DataFrame, spans: pd.DataFrame):
    """Cell of each reference row ('✓', another code, or '✗'), the set of
    reference rows each span matches, and the spans that match no row."""
    rows = ref.to_dict("records")
    cells, span_rows, extra = [], [], []
    span_list = spans.to_dict("records")
    for s in span_list:
        span_rows.append({i for i, r in enumerate(rows) if overlaps(r, s) and s["code"] == r["base_code"]})
    for i, r in enumerate(rows):
        hits = [s for s in span_list if overlaps(r, s)]
        if any(s["code"] == r["base_code"] for s in hits):
            cells.append("✓")
        elif hits:
            cells.append(hits[0]["code"])
        else:
            cells.append("✗")
    for s, matched in zip(span_list, span_rows):
        if not any(overlaps(r, s) for r in rows):
            extra.append(s)
    return cells, span_rows, extra


def scores(found_rows: set, n_pred: int, matched_pred: int, subset: set) -> dict:
    tp_ref = len(found_rows & subset)
    p = matched_pred / n_pred if n_pred else 0.0
    r = tp_ref / len(subset) if subset else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"found": tp_ref, "extra": n_pred - matched_pred, "P": p, "R": r, "F1": f}


def compare(article: Path, reference: Path) -> dict:
    kw = kc.load_list()
    sentences = load_sentences(article)
    ref = load_reference(reference, sentences)
    n = len(ref)
    subsets = {
        "Human A": {i for i in range(n) if ref.at[i, "human_a"]},
        "Human B": {i for i in range(n) if ref.at[i, "human_b"]},
        "Union (A or B)": {i for i in range(n) if ref.at[i, "human_a"] or ref.at[i, "human_b"]},
        "Consensus (A and B)": {i for i in range(n) if ref.at[i, "human_a"] and ref.at[i, "human_b"]},
    }
    results = {}
    for method in kc.METHODS:
        t0 = time.perf_counter()
        spans = kc.code_sentences(sentences, kw, method)
        elapsed = time.perf_counter() - t0
        cells, span_rows, extra = align(ref, spans)
        results[method] = {"spans": spans, "time": elapsed, "cells": cells, "extra": extra,
                           "span_rows": span_rows}
    agreement = []
    ai_rows = {i for i in range(n) if ref.at[i, "ai"]}
    for name, subset in subsets.items():
        ai_found = ai_rows & subset
        p = len(ai_found) / len(ai_rows)
        r = len(ai_found) / len(subset)
        agreement.append({"reference": name, "words": len(subset), "coder": "AI", "found": len(ai_found),
                          "extra": len(ai_rows - subset), "P": p, "R": r, "F1": 2 * p * r / (p + r),
                          "extra_words": [ref.at[i, "word"] for i in sorted(ai_rows - subset)]})
        for method, res in results.items():
            found_rows = {i for i, c in enumerate(res["cells"]) if c == "✓"}
            matched_pred = sum(1 for rows in res["span_rows"] if rows & subset)
            sc = scores(found_rows, len(res["spans"]), matched_pred, subset)
            extra_words = [s["text"] for s, rows in zip(res["spans"].to_dict("records"), res["span_rows"])
                           if not rows & subset]
            agreement.append({"reference": name, "words": len(subset), "coder": METHOD_LABELS[method],
                              **sc, "extra_words": extra_words})
    return {"sentences": sentences, "ref": ref, "results": results, "agreement": agreement}


def summary_rows(cmp: dict) -> list:
    ref = cmp["ref"]
    rows = []
    for col, (label, t, tokens) in HUMAN_INFO.items():
        coded = ref[ref[col] == 1]
        counts = coded["base_code"].value_counts()
        rows.append([label, t, tokens, len(coded)] + [int(counts.get(c, 0)) for c in kc.CODES])
    for method, res in cmp["results"].items():
        counts = res["spans"]["code"].value_counts()
        rows.append([METHOD_NAMES[method], f"{res['time']:.2f} s†", "0", len(res["spans"])]
                    + [int(counts.get(c, 0)) for c in kc.CODES])
    return rows


def context(text: str, start: int, end: int) -> str:
    """The span with one word on each side: 'ont été menées', 'Météo-France'."""
    left = re.search(r"(?:\S+\s+)?\S*$", text[:start]).group(0)
    right = re.match(r"\S*(?:\s+\S+)?", text[end:]).group(0)
    return (left + text[start:end] + right).strip(" ,;:.()«»")


def with_counts(words: list) -> str:
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return ", ".join(w + (f" ×{n}" if n > 1 else "") for w, n in counts.items())


def detail_table(cmp: dict) -> pd.DataFrame:
    """Word-by-word table: the reference rows, then the words coded by an
    algorithm only."""
    ref, results = cmp["ref"], cmp["results"]
    mark = {1: "✓", 0: "✗"}
    rows = []
    for i, r in ref.iterrows():
        rows.append({"#": int(r["n"]), "word": r["word"], "keyword": r["keyword"], "code": r["code"],
                     "Human A": mark[int(r["human_a"])], "Human B": mark[int(r["human_b"])], "AI": mark[int(r["ai"])],
                     **{METHOD_LABELS[m]: results[m]["cells"][i] for m in kc.METHODS},
                     "disagree": int(r["human_a"]) != int(r["human_b"]), "algo_only": False})
    sentence_order = {sid: k for k, sid in enumerate(cmp["sentences"]["sentence_id"])}
    texts = dict(zip(cmp["sentences"]["sentence_id"], cmp["sentences"]["text"]))
    extra = {}
    for m in kc.METHODS:
        for s in results[m]["extra"]:
            key = (sentence_order[s["sentence_id"]], s["start"], s["end"])
            item = extra.setdefault(key, {"word": s["text"], "keyword": s["entry"], "codes": {},
                                          "context": context(texts[s["sentence_id"]], s["start"], s["end"])})
            item["codes"][METHOD_LABELS[m]] = s["code"] + (f">{s['pid']}" if s["pid"] else "")
    for k, (key, item) in enumerate(sorted(extra.items()), start=len(ref) + 1):
        codes = list(dict.fromkeys(item["codes"].values()))
        rows.append({"#": k, "word": item["word"], "context": item["context"], "keyword": item["keyword"],
                     "code": " / ".join(codes),
                     "Human A": "✗", "Human B": "✗", "AI": "✗",
                     **{lab: ("✓" if lab in item["codes"] else "✗") for lab in METHOD_LABELS.values()},
                     "disagree": False, "algo_only": True})
    return pd.DataFrame(rows)


# --- PDF -----------------------------------------------------------------------------

def find_font():
    """A TrueType font with ✓ ✗ − ≈ (DejaVu Sans). None -> Helvetica + ASCII marks."""
    candidates = []
    try:
        import matplotlib
        base = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
        candidates.append((base / "DejaVuSans.ttf", base / "DejaVuSans-Bold.ttf"))
    except ImportError:
        pass
    candidates += [(Path("C:/Windows/Fonts/DejaVuSans.ttf"), Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf")),
                   (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            return regular, bold
    return None


def pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def write_pdf(cmp: dict, detail: pd.DataFrame, path: Path, article_label: str) -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    fonts = find_font()
    if fonts:
        from reportlab.lib.fonts import addMapping
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        oblique = fonts[0].with_name("DejaVuSans-Oblique.ttf")
        italic = "DejaVu"
        if oblique.exists():
            pdfmetrics.registerFont(TTFont("DejaVu-Oblique", str(oblique)))
            italic = "DejaVu-Oblique"
        addMapping("DejaVu", 0, 0, "DejaVu")
        addMapping("DejaVu", 1, 0, "DejaVu-Bold")
        addMapping("DejaVu", 0, 1, italic)
        addMapping("DejaVu", 1, 1, "DejaVu-Bold")
        regular, bold = "DejaVu", "DejaVu-Bold"
    else:
        regular, bold = "Helvetica", "Helvetica-Bold"
        detail = detail.replace({"✓": "yes", "✗": "-"})

    ink, grey, head = colors.HexColor("#1a1a1a"), colors.HexColor("#666666"), colors.HexColor("#e6ebf2")
    yellow, red, green = colors.HexColor("#fdf5dc"), colors.HexColor("#f6d5d5"), colors.HexColor("#eaf4ea")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=13.5, leading=17, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.5, leading=11, textColor=grey),
        "h": ParagraphStyle("h", fontName=bold, fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=5),
        "body": ParagraphStyle("b", fontName=regular, fontSize=9, leading=12.2, alignment=TA_LEFT),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7, leading=9, textColor=grey),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.6, leading=9.2),
    }
    base_style = [
        ("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("FONTNAME", (0, 0), (-1, 0), bold), ("BACKGROUND", (0, 0), (-1, 0), head),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa3ad")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]
    story = [
        Paragraph("Courchaton – keyword coding: humans, AI and algorithm A", st["title"]),
        Paragraph(f"Rules: <i>Rules for manual coding v2</i> · List: <i>keyword list v3</i> · Article: {article_label}"
                  f" · {date.today().strftime('%d %B %Y').lstrip('0')}", st["sub"]),
        Spacer(1, 6),
        Paragraph("The two human coders are the reference. The AI coding and the three variants of algorithm A are "
                  "compared with each of them, with their union (word coded by at least one human) and with their "
                  "consensus (word coded by both). <b>A</b> uses the Koinos tags only and <b>A+</b> the full list; "
                  "both look up the list term as written (whole word, optional plural s/x) and apply no rule. "
                  "<b>A-form</b> applies the list v3 with the rules v2 (forms I1, span I3, homonyms I4, proper names "
                  "I5, °C values I6, every occurrence I8, context D1, PID link D7).", st["body"]),
        Paragraph("Summary", st["h"]),
    ]

    srows = summary_rows(cmp)
    data = [["Coder", "Time", "Tokens", "Total"] + list(kc.CODES)] + srows
    t = Table(data, colWidths=[6.3 * cm, 1.9 * cm, 2.0 * cm, 1.2 * cm] + [0.9 * cm] * 6, hAlign="LEFT")
    style = base_style + [("ALIGN", (3, 1), (-1, -1), "CENTER"), ("ALIGN", (3, 0), (-1, 0), "CENTER"),
                          ("BACKGROUND", (0, 3), (-1, 3), green), ("BACKGROUND", (0, 6), (-1, 6), green)]
    t.setStyle(TableStyle(style))
    story += [t, Spacer(1, 3), Paragraph(
        "* and ** Estimates for a single API call with the 3 PDFs (16 pages) and a prompt that includes the coding "
        "decisions (see the original table). † Measured run time of the Python code on a laptop for the "
        f"{len(cmp['sentences'])} sentences of the article, including the compilation of the list; no API call, "
        "no token, no cost.", st["note"])]

    story.append(Paragraph("AI and algorithms against the human references", st["h"]))
    data = [["Reference", "Words", "Coder", "Found", "Not in reference", "Precision", "Recall", "F1"]]
    style = list(base_style) + [("ALIGN", (1, 1), (1, -1), "CENTER"), ("ALIGN", (3, 1), (-1, -1), "CENTER")]
    for k, a in enumerate(cmp["agreement"]):
        first = k % 4 == 0
        extra = str(a["extra"])
        if a["extra_words"] and len(set(a["extra_words"])) <= 6:
            extra += ": " + with_counts(a["extra_words"])
        data.append([a["reference"] if first else "", str(a["words"]) if first else "", a["coder"],
                     f"{a['found']} ({pct(a['R'])})", Paragraph(extra, st["cell"]),
                     pct(a["P"]), pct(a["R"]), f"{a['F1']:.2f}"])
        row = len(data) - 1
        if first and row > 1:
            style.append(("LINEABOVE", (0, row), (-1, row), 1.1, ink))
        if a["coder"] == "A-form":
            style.append(("BACKGROUND", (2, row), (-1, row), green))
    t = Table(data, colWidths=[3.4 * cm, 1.2 * cm, 1.5 * cm, 1.9 * cm, 5.0 * cm, 1.6 * cm, 1.4 * cm, 1.1 * cm],
              hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle(style))
    story += [t, Spacer(1, 4)]
    for paragraph in reading(cmp):
        story.append(Paragraph(paragraph, st["body"]))
        story.append(Spacer(1, 3))

    story += [PageBreak(), Paragraph("Word-by-word detail", st["h"])]
    labels = list(METHOD_LABELS.values())
    header = ["#", "Word in the text", "Keyword (list)", "Code", "Human A", "Human B", "AI"] + labels
    data = [header]
    style = list(base_style) + [("ALIGN", (3, 0), (-1, -1), "CENTER"), ("ALIGN", (0, 0), (0, -1), "RIGHT")]
    first_extra = None
    for _, r in detail.iterrows():
        if r["algo_only"] and first_extra is None:
            data.append(["", "Coded by an algorithm only (by no human and not by the AI)"]
                        + [""] * (len(header) - 2))
            first_extra = len(data) - 1
            style += [("SPAN", (1, first_extra), (-1, first_extra)),
                      ("FONTNAME", (0, first_extra), (-1, first_extra), bold),
                      ("BACKGROUND", (0, first_extra), (-1, first_extra), head),
                      ("ALIGN", (1, first_extra), (-1, first_extra), "LEFT")]
        word = r["word"]
        if r["algo_only"] and r.get("context") and r["context"] != r["word"]:
            word = Paragraph(f"{r['word']} <font color='#666666' size='6.5'>({r['context']})</font>", st["cell"])
        data.append([str(r["#"]), word, r["keyword"], r["code"], r["Human A"], r["Human B"], r["AI"]]
                    + [r[lab] for lab in labels])
        row = len(data) - 1
        if r["disagree"]:
            style.append(("BACKGROUND", (0, row), (3, row), yellow))
        for col in range(4, len(header)):
            coded = data[row][col] in ("✓", "yes")
            if r["algo_only"]:
                if col >= 7 and coded:                   # an algorithm codes a word nobody coded
                    style.append(("BACKGROUND", (col, row), (col, row), red))
            elif not coded:
                style.append(("BACKGROUND", (col, row), (col, row), red))
            elif col == len(header) - 1:
                style.append(("BACKGROUND", (col, row), (col, row), green))
    totals = ["", "Total", "", ""] + [str(int((detail[c] == "✓").sum())) for c in ("Human A", "Human B", "AI")]
    totals += [str(len(cmp["results"][m]["spans"])) for m in kc.METHODS]
    data.append(totals)
    style += [("FONTNAME", (0, len(data) - 1), (-1, len(data) - 1), bold),
              ("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), head)]
    t = Table(data, colWidths=[0.8 * cm, 3.9 * cm, 2.8 * cm, 1.1 * cm] + [1.6 * cm] * 3 + [1.3 * cm] * 3,
              hAlign="CENTER", repeatRows=1)
    t.setStyle(TableStyle(style))
    story += [t, Spacer(1, 4), Paragraph(
        "Yellow rows: words on which the two human coders disagree. A, A+, A-form: ✓ = the algorithm codes this "
        "word with the reference code; a letter = it codes the word with another code; ✗ = it does not code it. "
        "Red cell = disagreement with the reference (a word missed, or a word coded that nobody coded). "
        "Total of an algorithm = all the spans it codes, including the words below the reference.", st["note"])]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Courchaton keyword coding: humans, AI and algorithm A",
                            author="Desirable Cities (UTSEUS EG01)")
    doc.build(story)


def reading(cmp: dict) -> list:
    """Short text under the agreement table, written from the numbers."""
    by = {(a["reference"], a["coder"]): a for a in cmp["agreement"]}
    union, cons = "Union (A or B)", "Consensus (A and B)"
    n_union = by[(union, "AI")]["words"]
    form_u, plus_u, a_u = by[(union, "A-form")], by[(union, "A+")], by[(union, "A")]
    ref, cells = cmp["ref"], cmp["results"]["a_plus"]["cells"]
    missed = list(dict.fromkeys(w for w, c in zip(ref["word"], cells) if c != "✓"))
    extra = list(dict.fromkeys(plus_u["extra_words"]))

    def some(words, k=6):
        return ", ".join(words[:k]) + ("…" if len(words) > k else "") if words else "none"

    out = [
        f"On the union of the two human codings ({n_union} words), algorithm A finds {a_u['found']} words "
        f"(F1 {a_u['F1']:.2f}) and A+ {plus_u['found']} (F1 {plus_u['F1']:.2f}). The naive matcher misses "
        f"{len(missed)} distinct words ({some(missed)}) and codes {plus_u['extra']} span(s) outside the union "
        f"({some(extra)}). "
        f"A-form finds {form_u['found']} words with {form_u['extra']} word(s) outside the union "
        f"(F1 {form_u['F1']:.2f}); against the consensus its F1 is {by[(cons, 'A-form')]['F1']:.2f}, like the AI "
        f"({by[(cons, 'AI')]['F1']:.2f}), because it also codes the words on which the humans disagree.",
        "<b>Caution.</b> Courchaton is a development article: several examples of the rules v2 (I1, I4, I5, I6) "
        "come from it, and the encoding of the list (forms, exclusions) was checked on it. This score shows that "
        "A-form applies the rules consistently; it is not an estimate of its accuracy on unseen text. "
        "Lyon, coded independently, is the test (paper §5.1).",
    ]
    return out


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--article", default=str(ARTICLE))
    ap.add_argument("--reference", default=str(REFERENCE))
    ap.add_argument("--out", default=str(OUT), help="output path without extension (.pdf and .csv)")
    ap.add_argument("--label", default="fr.wikipedia rev. 234797520")
    args = ap.parse_args()

    cmp = compare(Path(args.article), Path(args.reference))
    detail = detail_table(cmp)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    detail.drop(columns=["disagree", "algo_only"]).to_csv(out.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    write_pdf(cmp, detail, out.with_suffix(".pdf"), args.label)

    print(f"{len(cmp['sentences'])} sentences, {len(cmp['ref'])} reference words -> {out}.pdf / .csv")
    for row in summary_rows(cmp):
        print(f"  {row[0]:<40} total {row[3]:>3}  " + " ".join(f"{c} {v}" for c, v in zip(kc.CODES, row[4:])))
    for a in cmp["agreement"]:
        print(f"  {a['reference']:<20} {a['coder']:<7} found {a['found']:>2}/{a['words']}  extra {a['extra']:>2}"
              f"  P {a['P']:.2f} R {a['R']:.2f} F1 {a['F1']:.2f}")


if __name__ == "__main__":
    main()
