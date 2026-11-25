"""PID matrices: the 3 x 3 matrix of environments x responses of the framework.

The Cities' PIDs (Villar 2025, §16.4) cross the three environments (N natural,
C cultural, B constructural) with the three responses (E emotions, A actions,
R reflections). As in the paper (§5.2 c and Figure 2), a PID cell is counted
at sentence level: a sentence contains the cell N x A when one of its A spans
is linked to N (rule D7). For each of the nine cells the matrix gives the
number and the share of sentences that contain it, with the keywords found
(list entries and number of spans), and two margins:

    no response      sentences with this environment and no response at all
    no environment   sentences with this response linked to no environment

Links: the algorithms link a response to every environment of its sentence
(field `pid` of keyword_coder.py); the human reference gives the link
explicitly ("R>N") and falls back on the same rule otherwise.

Usage:
    python src/pid_matrix.py
        pilot articles: Courchaton (human reference and A, A+, A-form) and Lyon
        (A, A+, A-form), lists v3 and v4
        -> docs/pid_matrices.pdf   one matrix per method and article (list v3)
           docs/pid_matrices.csv   every cell of every matrix, lists v3 and v4
    python src/pid_matrix.py --spans data/processed/spans_a_form.csv --sentences data/processed/sentences_500.parquet
        one matrix per article (insee, langue) of a corpus coded by keyword_coder.py
        -> data/processed/pid_matrices_a_form.csv (default: next to the spans file)
"""
import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

import keyword_coder as kc

ROOT = kc.ROOT
OUT = ROOT / "docs" / "pid_matrices"

ENVS, RESPONSES, NONE = kc.ENV_CODES, kc.RESPONSE_CODES, "-"
ROWS, COLS = ENVS + (NONE,), RESPONSES + (NONE,)
# entry names shown in the matrices
SHORT = {"any value in °C (rule I6)": "°C value", "value in °C": "°C value"}
NAMES = {"N": "Natural", "C": "Cultural", "B": "Constructural", "E": "Emotions", "A": "Actions",
         "R": "Reflections"}


# --- computation --------------------------------------------------------------------

def links(pid) -> set:
    """'N,B' -> {'N', 'B'}; '0', '' or NaN -> set()."""
    return {c for c in str(pid).split(",") if c in ENVS} if isinstance(pid, str) else set()


def pid_matrix(spans: pd.DataFrame, n_sentences: int) -> dict:
    """Sentence-level PID matrix of one article.

    spans: one row per span with sentence_id, code, pid, entry.
    Returns {n_sentences, spans, cells, env_sentences, response_sentences,
    env_only_sentences, linked_sentences, unlinked_sentences};
    cells[(row, col)] = {sentences, response: Counter, environment: Counter}
    for row in N, C, B, '-' and col in E, A, R, '-'."""
    cells = {(r, c): {"sentences": 0, "response": Counter(), "environment": Counter()} for r in ROWS for c in COLS}
    env_sentences, response_sentences, covered = Counter(), Counter(), 0
    env_only = linked = unlinked = 0
    for _, g in spans.groupby("sentence_id", sort=False):
        covered += 1
        envs = {}
        responses = []
        for code, entry, pid in zip(g["code"], g["entry"], g["pid"]):
            entry = SHORT.get(entry, entry)
            if code in ENVS:
                envs.setdefault(code, []).append(entry)
            elif code in RESPONSES:
                responses.append((code, entry, links(pid)))
        present = set()
        for code, entry, targets in responses:
            for env in (targets & envs.keys()) or {NONE}:
                present.add((env, code))
                cells[(env, code)]["response"][entry] += 1
        if not responses:
            present |= {(env, NONE) for env in envs}
        for env, code in present:
            cells[(env, code)]["sentences"] += 1
            if env != NONE:
                cells[(env, code)]["environment"].update(envs[env])
        env_sentences.update(envs.keys())
        response_sentences.update({code for code, _, _ in responses})
        env_only += bool(envs) and not responses
        linked += any(env != NONE and code != NONE for env, code in present)
        unlinked += any(env == NONE for env, _ in present)
    cells[(NONE, NONE)]["sentences"] = n_sentences - covered
    return {"n_sentences": n_sentences, "spans": len(spans), "cells": cells, "env_sentences": env_sentences,
            "response_sentences": response_sentences, "env_only_sentences": env_only,
            "linked_sentences": linked, "unlinked_sentences": unlinked}


def keywords(counter: Counter, k: int = None) -> str:
    """'célèbre 2; réputé 1' (most frequent first, ties in alphabetical order)."""
    items = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    return "; ".join(f"{w} {n}" for w, n in items[:k])


def matrix_rows(m: dict, **labels) -> list:
    """One row per cell (16), for a CSV."""
    n = m["n_sentences"]
    rows = []
    for (env, resp), cell in m["cells"].items():
        rows.append({**labels, "environment": env, "response": resp, "sentences": cell["sentences"],
                     "share": cell["sentences"] / n if n else 0.0,
                     "response_keywords": keywords(cell["response"]),
                     "environment_keywords": keywords(cell["environment"])})
    return rows


def profile(m: dict) -> dict:
    """Shares of the sentences of the article: with each code, with an
    environment and no response, with a PID cell, with an unlinked response."""
    n = m["n_sentences"] or 1
    out = {c: m["env_sentences"][c] / n for c in ENVS}
    out.update({c: m["response_sentences"][c] / n for c in RESPONSES})
    out["env_only"] = m["env_only_sentences"] / n
    out["linked"] = m["linked_sentences"] / n
    out["unlinked"] = m["unlinked_sentences"] / n
    return out


def reference_spans(ref: pd.DataFrame) -> pd.DataFrame:
    """Spans of a human reference (compare_coders.load_reference): code 'R>N'
    = R linked to N; a response without explicit link is linked to the
    environments of its sentence (rule D7)."""
    rows = []
    for r in ref.itertuples(index=False):
        code, _, link = str(r.code).partition(">")
        rows.append({"sentence_id": r.sentence_id, "start": r.start, "end": r.end, "text": r.word, "code": code,
                     "entry": r.keyword, "link": link})
    spans = pd.DataFrame(rows)
    envs = spans[spans["code"].isin(ENVS)].groupby("sentence_id")["code"].agg(set).to_dict()
    pids = []
    for s in spans.itertuples(index=False):
        if s.code not in RESPONSES:
            pids.append("")
        elif s.link:
            pids.append(s.link)
        else:
            pids.append(",".join(c for c in ENVS if c in envs.get(s.sentence_id, set())) or "0")
    return spans.assign(pid=pids).drop(columns="link")


def koinos_share(spans: pd.DataFrame, kw: dict) -> float:
    """Share of spans whose list entry is a Koinos tag (src K)."""
    if not len(spans):
        return float("nan")
    if "src" in spans:
        src = spans["src"]
    else:
        by_fr = {e["fr"]: e["src"] for e in kc.iter_entries(kw)}
        by_fr.update({"value in °C": "K"})
        src = spans["entry"].map(by_fr)
    return float((src == "K").mean())


def corpus_matrices(spans: pd.DataFrame, sentences: pd.DataFrame) -> pd.DataFrame:
    """One matrix per article (insee, langue) of a coded corpus, as cell rows."""
    article = sentences.set_index("sentence_id")[["insee", "langue"]]
    spans = spans.join(article, on="sentence_id")
    by_article = dict(tuple(spans.groupby(["insee", "langue"], sort=False)))
    rows = []
    for (insee, langue), sents in sentences.groupby(["insee", "langue"], sort=True):
        part = by_article.get((insee, langue), spans.iloc[0:0])
        rows += matrix_rows(pid_matrix(part, len(sents)), insee=insee, langue=langue)
    return pd.DataFrame(rows)


# --- PDF ----------------------------------------------------------------------------

SCALE_MAX = 0.05            # shade of a PID cell: 0 -> white, >= 5 % of the sentences -> darkest


def write_pdf(path: Path, blocks: list, summary: list, comparison: tuple, notes: dict) -> None:
    """blocks: [(title, subtitle, matrix, koinos share)]; summary: rows of the
    first table; comparison: (column labels, {(row, col): [values]})."""
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    import compare_coders as cc

    regular, bold = "Helvetica", "Helvetica-Bold"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        for b, i in ((0, 0), (1, 0), (0, 1), (1, 1)):
            addMapping("DejaVu", b, i, "DejaVu-Bold" if b else "DejaVu")
        regular, bold = "DejaVu", "DejaVu-Bold"

    ink, muted, rule = colors.HexColor("#1a1a1a"), colors.HexColor("#5f6368"), colors.HexColor("#9aa3ad")
    head, margin_bg = colors.HexColor("#e6ebf2"), colors.HexColor("#f3f3f1")
    low, high = colors.HexColor("#ffffff"), colors.HexColor("#86b6ef")    # sequential blue, step 250 at the top
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=15, leading=19, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.5, leading=11, textColor=muted),
        "h": ParagraphStyle("h", fontName=bold, fontSize=12, leading=15, spaceBefore=8, spaceAfter=4, textColor=ink),
        "body": ParagraphStyle("b", fontName=regular, fontSize=8.8, leading=11.8, textColor=ink),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7.4, leading=9.4, textColor=muted),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.4, leading=9.2, textColor=ink),
        "num": ParagraphStyle("u", fontName=regular, fontSize=7.8, leading=9.6, textColor=ink),
        "hdr": ParagraphStyle("r", fontName=regular, fontSize=7.6, leading=9.4, textColor=ink),
    }

    def shade(share: float):
        t = max(0.0, min(1.0, share / SCALE_MAX))
        return colors.Color(low.red + (high.red - low.red) * t, low.green + (high.green - low.green) * t,
                            low.blue + (high.blue - low.blue) * t)

    def pct(x: float, digits: int = 1) -> str:
        if x != x:
            return "–"
        return f"{100 * x:.{digits}f} %".replace(".0 %", " %") if digits else f"{100 * x:.0f} %"

    def sentences(k: int, n: int) -> str:
        return f"{k} sentence{'' if k == 1 else 's'} ({pct(k / n)})"

    def words(counter: Counter, k: int = 6) -> str:
        items = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
        text = ", ".join(f"{w} {n}" for w, n in items[:k])
        if len(items) > k:
            text += f", <font color='#5f6368'>+{len(items) - k} more</font>"
        return text

    def cell_paragraph(m, env, resp):
        cell, n = m["cells"][(env, resp)], m["n_sentences"]
        if cell["sentences"] == 0:
            return Paragraph("<font color='#9aa3ad'>–</font>", st["num"])
        lines = [f"<b>{cell['sentences']}</b> sentence{'' if cell['sentences'] == 1 else 's'} · "
                 f"{pct(cell['sentences'] / n)}"]
        if resp != NONE and cell["response"]:
            lines.append(f"<b>{resp}</b>: {words(cell['response'])}")
        if env != NONE and cell["environment"]:
            lines.append(f"<b>{env}</b>: {words(cell['environment'])}")
        if env == NONE and resp == NONE:
            lines = [f"<b>{cell['sentences']}</b> sentences · {pct(cell['sentences'] / n)}",
                     "<font color='#5f6368'>no keyword at all</font>"]
        return Paragraph("<br/>".join(lines), st["cell"])

    def matrix_table(m):
        n = m["n_sentences"]
        header = [Paragraph("", st["hdr"])]
        for r in RESPONSES:
            header.append(Paragraph(f"<b>{r} · {NAMES[r]}</b><br/>{sentences(m['response_sentences'][r], n)}",
                                    st["hdr"]))
        header.append(Paragraph("<b>No response</b><br/>environment only", st["hdr"]))
        data = [header]
        for env in ROWS:
            if env == NONE:
                row = [Paragraph("<b>No environment</b><br/>response not linked", st["hdr"])]
            else:
                row = [Paragraph(f"<b>{env} · {NAMES[env]}</b><br/>{sentences(m['env_sentences'][env], n)}",
                                 st["hdr"])]
            row += [cell_paragraph(m, env, resp) for resp in COLS]
            data.append(row)
        widths = [3.8, 6.15, 6.15, 6.15, 4.6]
        style = [("GRID", (0, 0), (-1, -1), 0.5, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("BACKGROUND", (0, 0), (-1, 0), head), ("BACKGROUND", (0, 1), (0, -1), head),
                 ("BACKGROUND", (-1, 1), (-1, -1), margin_bg), ("BACKGROUND", (1, -1), (-1, -1), margin_bg),
                 ("LINEBELOW", (0, 3), (-1, 3), 1.2, ink), ("LINEAFTER", (3, 0), (3, -1), 1.2, ink),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                 ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
        for i, env in enumerate(ENVS, start=1):
            for j, resp in enumerate(RESPONSES, start=1):
                style.append(("BACKGROUND", (j, i), (j, i), shade(m["cells"][(env, resp)]["sentences"] / n)))
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return t

    def simple_table(data, widths, align_from=1, extra=()):
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.8),
                               ("FONTNAME", (0, 0), (-1, 0), bold), ("BACKGROUND", (0, 0), (-1, 0), head),
                               ("GRID", (0, 0), (-1, -1), 0.4, rule), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ALIGN", (align_from, 0), (-1, -1), "CENTER"),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]
                              + list(extra)))
        return t

    steps = 6
    legend_row = Table([["Shade of the nine PID cells (share of the sentences of the article):", "0"]
                        + [""] * steps + [f"≥ {pct(SCALE_MAX, 0)}"]],
                       colWidths=[9.4 * cm, 0.5 * cm] + [0.8 * cm] * steps + [1.4 * cm], rowHeights=[0.4 * cm],
                       hAlign="LEFT")
    legend_row.setStyle(TableStyle(
        [("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.2),
         ("TEXTCOLOR", (0, 0), (-1, -1), muted), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
         ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
         ("BOX", (2, 0), (steps + 1, 0), 0.4, rule)]
        + [("BACKGROUND", (2 + i, 0), (2 + i, 0), shade(SCALE_MAX * i / (steps - 1))) for i in range(steps)]))

    story = [Paragraph("PID matrices of Courchaton and Lyon", st["title"]),
             Paragraph(notes["subtitle"], st["sub"]), Spacer(1, 6)]
    for text in notes["intro"]:
        story += [Paragraph(text, st["body"]), Spacer(1, 3)]
    story.append(Paragraph("Profiles", st["h"]))
    summary = [[Paragraph(f"<b>{h}</b>", st["hdr"]) for h in summary[0]]] + summary[1:]
    story.append(simple_table(summary, [2.1, 4.1, 1.4, 1.5, 1.4, 1.4, 1.4, 1.4, 1.4, 1.4, 2.1, 1.7, 2.1],
                              align_from=2))
    story += [Spacer(1, 3), Paragraph(notes["summary"], st["note"]), Spacer(1, 4)]
    for text in notes["caution"]:
        story += [Paragraph(text, st["body"]), Spacer(1, 3)]

    current = None
    for title, subtitle, m in blocks:
        article = title.split(" · ")[0]
        if article != current:
            story.append(PageBreak())
            current = article
        else:
            story.append(CondPageBreak(9 * cm))
        story.append(KeepTogether([Paragraph(title, st["h"]), Paragraph(subtitle, st["sub"]), Spacer(1, 4),
                                   matrix_table(m), Spacer(1, 3), legend_row, Spacer(1, 10)]))

    labels, values = comparison                      # labels: [(group, column label)]
    story += [PageBreak(), Paragraph("All methods and both lists: sentences per cell", st["h"]),
              Paragraph(notes["comparison"], st["body"]), Spacer(1, 5)]
    groups = list(dict.fromkeys(g for g, _ in labels))
    centred = ParagraphStyle("hc", parent=st["hdr"], alignment=1)
    data = [["Cell"] + [""] * len(labels), [""] + [Paragraph(f"<b>{l}</b>", centred) for _, l in labels]]
    shaded = [("BACKGROUND", (0, 1), (-1, 1), head), ("FONTNAME", (0, 1), (-1, 1), bold),
              ("SPAN", (0, 0), (0, 1)), ("VALIGN", (0, 0), (0, 1), "BOTTOM")]
    for g in groups:
        first = 1 + [x for x, _ in labels].index(g)
        last = first + sum(1 for x, _ in labels if x == g) - 1
        data[0][first] = g
        shaded += [("SPAN", (first, 0), (last, 0)), ("LINEBEFORE", (first, 0), (first, -1), 1.2, ink)]
    for env in ROWS:
        for resp in COLS:
            if env == NONE and resp == NONE:
                continue
            name = (f"{env} × {resp}" if NONE not in (env, resp) else
                    f"{env} only" if resp == NONE else f"{resp}, no environment")
            data.append([name] + values[(env, resp)])
            if NONE in (env, resp):
                shaded.append(("BACKGROUND", (0, len(data) - 1), (-1, len(data) - 1), margin_bg))
    story.append(simple_table(data, [3.2] + [2.1] * len(labels), extra=shaded))
    story += [Spacer(1, 3), Paragraph(notes["comparison_note"], st["note"])]

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=1.4 * cm, rightMargin=1.4 * cm,
                            topMargin=1.2 * cm, bottomMargin=1.2 * cm, title="PID matrices of Courchaton and Lyon",
                            author="Desirable Cities (UTSEUS EG01)")
    doc.build(story)


# --- pilot report ---------------------------------------------------------------------

def pilot_report(out: Path = OUT) -> None:
    import compare_coders as cc
    import compare_list_versions as clv

    labels = cc.METHOD_LABELS
    lists = {lab: kc.load_list(p) for lab, p in clv.LISTS.items()}
    articles = {"Courchaton": cc.load_sentences(cc.ARTICLE, "70178"), "Lyon": cc.load_sentences(clv.LYON, "69123")}
    revisions = {"Courchaton": "234797520", "Lyon": "241583218"}

    matrices, rows = {}, []
    for article, sentences in articles.items():
        n = len(sentences)
        coders = []
        if article == "Courchaton":
            ref = reference_spans(cc.load_reference(cc.REFERENCE, sentences))
            coders.append(("reference", "Human reference (A or B)", "v3", ref))
        runs = clv.run(sentences, lists)
        for lab in lists:
            for method in kc.METHODS:
                coders.append((method, labels[method], lab, runs[(lab, method)][0]))
        for key, name, lab, spans in coders:
            m = pid_matrix(spans, n)
            share = koinos_share(spans, lists[lab])
            matrices[(article, key, lab)] = (name, m, share)
            rows += matrix_rows(m, article=article, revision=revisions[article], coder=name, list=lab)

    summary = [["Article", "Coder", "Spans", "Koinos", "N", "C", "B", "E", "A", "R", "Env., no resp.",
                "PID cell", "Resp., no env."]]
    blocks = []
    for (article, key, lab), (name, m, share) in matrices.items():
        if lab != "v3":
            continue
        p = profile(m)
        summary.append([article, name, m["spans"], "–" if share != share else f"{100 * share:.0f} %"]
                       + [f"{100 * p[c]:.0f} %" for c in ENVS] + [f"{100 * p[c]:.1f} %" for c in RESPONSES]
                       + [f"{100 * p['env_only']:.0f} %", f"{100 * p['linked']:.1f} %",
                          f"{100 * p['unlinked']:.1f} %"])
        method_text = {
            "reference": "Union of the two human coders (rules v2, list v3); links given by the coders (R>N).",
            "a": "Algorithm A: Koinos tags only, naive matching; every response linked to every environment of its "
                 "sentence.",
            "a_plus": "Algorithm A+: full list v3, naive matching; same links as A.",
            "a_form": "Algorithm A-form: list v3 + rules v2 (forms, homonyms, proper names); links by rule D7. "
                      "Rule D4/D6 (people really feel, act, think) is not applied.",
        }[key]
        sub = (f"fr.wikipedia rev. {revisions[article]} · {m['n_sentences']} sentences · {m['spans']} spans · "
               f"{method_text}")
        blocks.append((f"{article} · {name}", sub, m))

    columns = [("Courchaton", "reference", "v3", "Reference")]
    for article in articles:
        for key, lab in (("a", "v3"), ("a_plus", "v3"), ("a_form", "v3"), ("a_plus", "v4"), ("a_form", "v4")):
            columns.append((article, key, lab, labels[key] + ("" if key == "a" else f" {lab}")))
    values = {}
    for env in ROWS:
        for resp in COLS:
            values[(env, resp)] = [matrices[(a, k, l)][1]["cells"][(env, resp)]["sentences"] for a, k, l, _ in columns]
    if any(matrices[(a, "a", "v3")][1]["cells"] != matrices[(a, "a", "v4")][1]["cells"] for a in articles):
        raise RuntimeError("method A should not depend on the list version (same Koinos tags in v3 and v4)")

    review = pd.read_csv(clv.REVIEW)
    resp_review = review[review["code"].isin(RESPONSES)]
    notes = {
        "subtitle": f"Keyword list v3 · rules for manual coding v2 · Courchaton rev. 234797520 ({len(articles['Courchaton'])} "
                    f"sentences) · Lyon rev. 241583218 ({len(articles['Lyon'])} sentences) · "
                    f"{date.today().strftime('%d %B %Y').lstrip('0')}",
        "intro": [
            "The framework crosses the three <b>environments</b> (N natural, C cultural, B constructural) with the "
            "three <b>responses</b> (E emotions, A actions, R reflections); each crossing is a <b>PID cell</b>. As in "
            "the paper (§5.2 c, Figure 2), cells are counted in <b>sentences</b>: a sentence contains the cell N × A "
            "when one of its action spans is linked to a natural span (rule D7). Each cell gives the number and share "
            "of sentences that contain it, then the keywords found, by list entry with their number of spans: first "
            "the response words, then the environment words they are linked to.",
            "Two margins complete the 3 × 3 matrix: <b>No response</b> (sentences with that environment and no "
            "response at all, i.e. pure description) and <b>No environment</b> (responses linked to no environment). "
            "Row and column headers give the share of sentences with each environment and each response. One matrix "
            "per article and per coder follows, with list v3; the last page compares all methods with lists v3 and v4.",
        ],
        "summary": "Share of the sentences of the article that contain at least one span of each code. Koinos = share "
                   "of spans whose list entry is a Koinos tag (paper, §6.4). Env., no resp. = sentences with an "
                   "environment and no response; PID cell = sentences with a response linked to an environment; "
                   "Resp., no env. = sentences with a response linked to no environment.",
        "caution": [
            f"<b>How far to trust the response cells.</b> No algorithm applies rule D4/D6 (an emotion or action counts "
            f"only when people experience it, a reflection only when the text reports what people think of the place): "
            f"responses are matched on their form only, and linked to every environment of their sentence. In the "
            f"Lyon review sample, {int(resp_review['valid'].sum())} of the {len(resp_review)} response spans were "
            f"valid (environments: {int(review[review['code'].isin(ENVS)]['valid'].sum())} of "
            f"{int(review['code'].isin(ENVS).sum())}). The nine PID cells of the algorithms are therefore an upper "
            f"bound, mostly made of false responses (célèbre for a person, projet, proposer); the environment profile "
            f"is much more reliable. The Courchaton reference, which contains a single response, shows what the "
            f"human coding gives.",
            "Lyon has no human coding yet (its coders work on rev. 241194072 of 9 November, three small edits "
            "before the revision used here). Courchaton is development data: the rules were refined on it.",
        ],
        "comparison": "Number of sentences containing each cell, for every coder and both lists (A is the same with "
                      "both lists: the Koinos tags did not change). List v4 is a proposal built from these two "
                      "articles, so its figures here are not a test.",
        "comparison_note": "N only, C only, B only = sentences with that environment and no response; "
                           "E/A/R, no environment = responses linked to no environment. Every cell of every matrix, "
                           "with its keywords, is in docs/pid_matrices.csv.",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    write_pdf(out.with_suffix(".pdf"), blocks, summary, ([(c[0], c[3]) for c in columns], values), notes)
    print(f"-> {out}.pdf / .csv")
    for (article, key, lab), (name, m, share) in matrices.items():
        core = {f"{e}x{r}": m["cells"][(e, r)]["sentences"] for e in ENVS for r in RESPONSES}
        print(f"  {article:<10} {lab} {name:<26} sentences {m['n_sentences']:>4}  PID cells {m['linked_sentences']:>3}"
              f"  " + " ".join(f"{k}={v}" for k, v in core.items() if v))


# --- CLI ------------------------------------------------------------------------------

def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spans", help="spans CSV written by keyword_coder.py (corpus mode)")
    ap.add_argument("--sentences", help="sentences parquet the spans come from (corpus mode)")
    ap.add_argument("--out", help="output CSV (corpus mode) or report path without extension (pilot mode)")
    args = ap.parse_args()
    if not args.spans and not args.sentences:
        pilot_report(Path(args.out) if args.out else OUT)
        return
    if not (args.spans and args.sentences):
        sys.exit("corpus mode needs both --spans and --sentences")
    spans = pd.read_csv(args.spans, dtype={"pid": str})
    sentences = pd.read_parquet(args.sentences)
    table = corpus_matrices(spans, sentences)
    out = Path(args.out or Path(args.spans).with_name(Path(args.spans).stem.replace("spans", "pid_matrices") + ".csv"))
    table.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{table[['insee', 'langue']].drop_duplicates().shape[0]} articles, {len(table)} cells -> {out}")


if __name__ == "__main__":
    main()
