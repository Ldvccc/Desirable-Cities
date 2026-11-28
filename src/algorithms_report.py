"""Write docs/algorithms.pdf: how each keyword-coding algorithm works and where it fails.

The figures are read from the reports already produced, so that the PDF follows
the latest runs (for instance after the Hybrid method is run through the API):
    docs/methods_comparison.csv        (python src/compare_methods.py)
    docs/list_versions_comparison.csv  (python src/compare_list_versions.py)
    data/llm/hybrid_answers.jsonl      (which model answered for the Hybrid method)

Usage:
    python src/algorithms_report.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

import compare_coders as cc
import compare_methods as methods_mod
import hybrid
import keyword_coder as kc

ROOT = kc.ROOT
OUT = ROOT / "docs" / "algorithms.pdf"


def load_figures() -> dict:
    m = pd.read_csv(ROOT / "docs" / "methods_comparison.csv")
    lv = pd.read_csv(ROOT / "docs" / "list_versions_comparison.csv")
    f = {}
    for r in m.to_dict("records"):
        f[(r["article"], r["method"])] = r
    for r in lv[(lv["article"] == "Lyon") & (lv["list"] == "v3")].to_dict("records"):
        f[("precision", r["method"])] = (r["precision"], r["precision_lo"], r["precision_hi"])
    models = set()
    if hybrid.CACHE.exists():
        for line in hybrid.CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                models.add(json.loads(line)["model"])
    f["hybrid_models"] = models
    review = pd.read_csv(ROOT / "data" / "reference" / "lyon_fr_241583218_review_sample.csv")
    resp = review[review["code"].isin(kc.RESPONSE_CODES)]
    f["review_resp"] = (int(resp["valid"].sum()), len(resp))
    return f


def write_pdf(path: Path, f: dict) -> None:
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    regular, bold, italic = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        for b, i in ((0, 0), (1, 0), (0, 1), (1, 1)):
            addMapping("DejaVu", b, i, "DejaVu-Bold" if b else "DejaVu")
        regular, bold, italic = "DejaVu", "DejaVu-Bold", "DejaVu"
    ink, grey, head = colors.HexColor("#1a1a1a"), colors.HexColor("#5f6368"), colors.HexColor("#e6ebf2")
    rule, accent, soft = colors.HexColor("#9aa3ad"), colors.HexColor("#1c5cab"), colors.HexColor("#f3f6fa")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=17, leading=21, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.6, leading=11.2, textColor=grey),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=13, leading=17, spaceBefore=12, spaceAfter=3,
                             textColor=accent),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=9.6, leading=12.5, spaceBefore=6, spaceAfter=2,
                             textColor=ink),
        "body": ParagraphStyle("b", fontName=regular, fontSize=9, leading=12.4, textColor=ink, spaceAfter=3),
        "bullet": ParagraphStyle("u", fontName=regular, fontSize=9, leading=12.2, textColor=ink, leftIndent=12,
                                 bulletIndent=2, spaceAfter=1.5),
        "example": ParagraphStyle("e", fontName=regular, fontSize=8.6, leading=11.6, textColor=ink, leftIndent=8,
                                  borderPadding=(4, 6, 4, 6), backColor=soft, spaceBefore=6, spaceAfter=7),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.6, leading=9.4, textColor=ink),
        "hdr": ParagraphStyle("r", fontName=bold, fontSize=7.6, leading=9.4, textColor=ink),
        "verdict": ParagraphStyle("v", fontName=bold, fontSize=9, leading=12.4, textColor=accent, spaceBefore=3,
                                  spaceAfter=2),
    }

    def P(text, style="body"):
        return Paragraph(text, st[style])

    def bullets(items):
        return [Paragraph(t, st["bullet"], bulletText="•") for t in items]

    def pct(x, digits=0):
        return f"{100 * x:.{digits}f} %"

    def g(article, method, key):
        return f[(article, method)][key]

    def prec(method):
        p, lo, hi = f[("precision", method)]
        return f"{pct(p)} ({100 * lo:.0f}–{100 * hi:.0f})"

    session = all(m.startswith("session:") for m in f["hybrid_models"]) and f["hybrid_models"]
    hybrid_flag = " (preview)" if session else ""
    rv, rn = f["review_resp"]

    def section(title, lead, how, example, results, limits, verdict):
        block = [CondPageBreak(5 * cm), Paragraph(title, st["h1"]), P(lead)]
        out = [KeepTogether(block), P("How it works", "h2")]
        out += how if isinstance(how, list) else [P(how)]
        out += [P("Example", "h2"), Paragraph(example, st["example"]), P("Results on the pilot articles", "h2")]
        out += bullets(results)
        out += [P("Limits", "h2")] + bullets(limits)
        out += [Paragraph(verdict, st["verdict"])]
        return out

    articles = " · ".join(f"{n} rev. {a['rev']}" for n, a in methods_mod.ARTICLES.items())
    story = [
        Paragraph("Keyword coding algorithms: how each works and where it fails", st["title"]),
        Spacer(1, 3),
        P(f"Desirable Cities · UTSEUS EG01 · keyword list v3 · rules for manual coding v2 · {articles} · "
          f"{date.today().strftime('%d %B %Y').lstrip('0')}", "sub"),
        Spacer(1, 8),
        P("Every algorithm reads the sentences of a Wikipedia article and marks <b>spans</b> (a word or a fixed "
          "expression of the list), each with one code: N natural, C cultural, B constructural (the environments), "
          "E emotions, A actions, R reflections (the responses). Each response is then <b>linked</b> to "
          "environments; a link is a <b>PID cell</b> of the 3 × 3 matrix of the framework (e.g. N × A). The six "
          "algorithms below build on each other: A and A+ are the naive baselines of the paper, A-form applies the "
          "coding rules, Heritage and Hybrid change how responses are kept and linked."),
        P("They were compared on three pilot articles: <b>Courchaton</b>, with a human reference of 50 words "
          "(but the rules were tuned on it, so it is development data), and <b>Lyon</b> and <b>Fontainebleau</b>, "
          "which have no human coding yet. Detailed figures: docs/methods_comparison.pdf; matrices: "
          "docs/pid_matrices.pdf."),
        Paragraph("At a glance", st["h1"]),
    ]
    rows = [["Algorithm", "Finds words with", "Response check", "Links responses to", "F1",
             "Lyon: est. precision", "Lyon: PID sent.", "Verdict"]]
    verdicts = {
        "A": "Too thin for encyclopedic text; framework baseline",
        "A+": "Naive baseline of the paper",
        "A-form": "Main keyword method; reliable for environments only",
        "Heritage": "Correct but almost never applies; drop",
        "Hybrid": "Most promising for PID cells; to run and measure",
        "Hybrid + Heritage": "Same as Hybrid; no reason to keep both",
    }
    finds = {"A": "158 Koinos tags, as written", "A+": "341 list entries, as written",
             "A-form": "list + forms, homonyms, names", "Heritage": "as A-form", "Hybrid": "as A-form",
             "Hybrid + Heritage": "as A-form"}
    checks = {"A": "no", "A+": "no", "A-form": "no (form only)", "Heritage": "no", "Hybrid": "yes, by an LLM",
              "Hybrid + Heritage": "yes, by an LLM"}
    links = {"A": "all envs of the sentence", "A+": "all envs of the sentence", "A-form": "all envs of the sentence",
             "Heritage": "+ previous sentence", "Hybrid": "chosen by the LLM", "Hybrid + Heritage": "LLM + previous"}
    for method in methods_mod.METHODS:
        p = prec(method) if ("precision", method) in f else "env. " + pct(
            g("Lyon", method, "env_review_valid") / g("Lyon", method, "env_review_n"))
        rows.append([P(method, "hdr"), P(finds[method], "cell"), P(checks[method], "cell"), P(links[method], "cell"),
                     f"{g('Courchaton', method, 'union_F1'):.2f}", P(p, "cell"),
                     f"{int(g('Lyon', method, 'pid_sentences'))}" + (hybrid_flag if "Hybrid" in method else ""),
                     P(verdicts[method], "cell")])
    t = Table([[P(h, "hdr") for h in rows[0]]] + rows[1:],
              colWidths=[c * cm for c in (2.0, 2.4, 1.9, 2.2, 1.6, 2.2, 1.9, 3.3)], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("FONTSIZE", (0, 0), (-1, -1), 7.6),
                           ("BACKGROUND", (0, 0), (-1, 0), head), ("GRID", (0, 0), (-1, -1), 0.4, rule),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (4, 1), (4, -1), "CENTER"),
                           ("ALIGN", (6, 1), (6, -1), "CENTER"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story += [t, Spacer(1, 3), P(
        "F1 = Courchaton, against the union of the two human coders (50 words). Lyon: PID sent. = sentences "
        "with a PID cell. Lyon precision = share of valid "
        "spans in a random sample of 200 spans reviewed by Claude (95 % interval; not a human reference); for the "
        "methods built on A-form after the sample was drawn, the precision of their environment spans is given "
        "(they keep A-form's environments). " + ("Hybrid figures are a preview: see its section." if session else ""),
        "sub")]

    # --- A --------------------------------------------------------------------------------
    story += section(
        "A · Koinos tags, naive",
        "The tags of the framework's own tagging system, and nothing else.",
        "The list is the 158 Koinos tags of the thesis (entries <i>src K</i> of list v3), each rendered by one "
        "French term. Each term is searched as written: whole word, case-insensitive, optional final <i>s</i> or "
        "<i>x</i>. No rule is applied. Every response is linked to every environment of its sentence.",
        "« Il a été élu maire » → <b>été</b> coded N (the season). « une église » → nothing: <i>église</i> is not a "
        "Koinos tag.",
        [f"Courchaton: {int(g('Courchaton', 'A', 'union_found'))} of the 50 reference words, "
         f"{int(g('Courchaton', 'A', 'union_extra'))} wrong ones, F1 {g('Courchaton', 'A', 'union_F1'):.2f}.",
         f"Lyon: {int(g('Lyon', 'A', 'spans'))} spans, estimated precision {prec('A')}; "
         f"Fontainebleau: {int(g('Fontainebleau', 'A', 'spans'))} spans.",
         f"Almost no responses ({int(g('Lyon', 'A', 'responses'))} in Lyon, "
         f"{int(g('Fontainebleau', 'A', 'responses'))} in Fontainebleau), hence almost no PID cell."],
        ["<b>Too thin for encyclopedic text</b>: no common buildings (église, mairie, école), no relief, history "
         "or heritage, which make up most of a commune article.",
         "<b>No reflections at all</b>: Koinos records reflections as free text, so the code R is never found.",
         "<b>Only the exact term</b>: feminine forms, conjugations and derived words are missed (<i>culturelle</i>, "
         "<i>climatiques</i>, <i>forestier</i>).",
         "<b>Homonyms and names are coded</b>: <i>a été</i>, <i>fiscalité propre</i>, <i>bassin houiller</i>, "
         "<i>Arbonne-la-Forêt</i>.",
         "<b>Links without meaning</b>: every response × every environment of the sentence."],
        "Use: a baseline that shows what the framework's own tags capture, reported apart from the extended list.")

    # --- A+ -------------------------------------------------------------------------------
    story += section(
        "A+ · Full list, naive",
        "The same matcher on the whole keyword list v3.",
        "The list is the 341 entries of list v3: Koinos tags, Emotion-naire Card elements, names of categories, "
        "136 extensions (buildings, relief, history, negative emotions) and 20 reflection markers. Matching and "
        "links are those of A.",
        "« la région culturelle » → nothing (<i>culturel</i> is in the list, its feminine is not matched). "
        "« selon Météo-France » → <b>Météo</b> coded N (part of a name).",
        [f"Courchaton: {int(g('Courchaton', 'A+', 'union_found'))} of 50 words, "
         f"{int(g('Courchaton', 'A+', 'union_extra'))} wrong ones, F1 {g('Courchaton', 'A+', 'union_F1'):.2f}.",
         f"Lyon: {int(g('Lyon', 'A+', 'spans'))} spans, estimated precision {prec('A+')}, "
         f"{int(g('Lyon', 'A+', 'responses'))} responses, PID cells in {int(g('Lyon', 'A+', 'pid_sentences'))} "
         f"sentences; Fontainebleau: {int(g('Fontainebleau', 'A+', 'spans'))} spans."],
        ["<b>Same matching limits as A</b>: no forms beyond a final s/x, homonyms and names coded.",
         "<b>Responses on their form only</b>: every listed response word counts, whoever it is about.",
         "<b>Closed list</b>: a synonym or a more specific word is not coded (<i>fleuve</i>, <i>basilique</i>)."],
        "Use: the naive baseline of the paper (§5.3), to show what the coding rules add.")

    # --- A-form ---------------------------------------------------------------------------
    story += section(
        "A-form · List + coding rules",
        "The keyword method that applies the rules for manual coding v2, word by word, like a human coder.",
        bullets([
            "<b>Forms (rule I1)</b>: for each entry, generate its plurals, feminines, the conjugated forms of "
            "<i>-er</i> verbs and the same-stem words written in the list encoding (<i>forêt</i> → <i>forestier</i>).",
            "<b>Filters</b>: a capitalised word inside a sentence, or a word hyphenated to one, is part of a proper "
            "name (I5); per-entry exclusions remove fixed expressions and homonyms (I4); <i>été</i> after "
            "<i>avoir</i> is the verb; <i>son</i> needs a determiner; reflexive verbs need <i>se</i>; sound, smell "
            "and feeling words decide the code of <i>calme</i>, <i>voitures</i>, <i>restaurants</i> (D1); every "
            "°C value is N (I6).",
            "<b>Overlaps (I3)</b>: the longest span wins.",
            "<b>Links (D7)</b>: each response is linked to every environment present in its sentence.",
        ]),
        "« Il a été élu » → nothing. « un climat tempéré à été frais » → <b>climat</b> N, <b>été</b> N. "
        "« la forêt de Fontainebleau » → <b>forêt</b> N. « 9,9 °C » → N.",
        [f"Courchaton: all 50 reference words, no wrong one, F1 {g('Courchaton', 'A-form', 'union_F1'):.2f} "
         f"(consensus {g('Courchaton', 'A-form', 'consensus_F1'):.2f}).",
         f"Lyon: {int(g('Lyon', 'A-form', 'spans'))} spans, estimated precision {prec('A-form')}, environments "
         f"{pct(g('Lyon', 'A-form', 'env_review_valid') / g('Lyon', 'A-form', 'env_review_n'))} "
         f"({int(g('Lyon', 'A-form', 'env_review_valid'))}/{int(g('Lyon', 'A-form', 'env_review_n'))}); "
         f"{int(g('Lyon', 'A-form', 'responses'))} responses, PID cells in "
         f"{int(g('Lyon', 'A-form', 'pid_sentences'))} sentences.",
         f"Fontainebleau: {int(g('Fontainebleau', 'A-form', 'spans'))} spans, "
         f"{int(g('Fontainebleau', 'A-form', 'responses'))} responses, PID cells in "
         f"{int(g('Fontainebleau', 'A-form', 'pid_sentences'))} sentences."],
        [f"<b>Responses are not checked (rules D4, D6)</b>: a response word counts even when nobody feels, does or "
         f"thinks anything about the place: <i>célèbre chirurgien</i>, <i>projet de tramway</i>, <i>radio proposant "
         f"du jazz</i>, <i>Maison de la danse</i>. In the Lyon sample, only {rv} of {rn} response spans were valid: "
         f"the PID cells of A-form are an upper bound.",
         "<b>Links without syntax</b>: a response is linked to every environment of its sentence, even those it "
         "has nothing to do with.",
         "<b>Homonyms are hand-written</b>: only the exclusions in the list are known, and each new article brings "
         "new ones (Lyon: <i>fleurs de lys</i>, Michelin <i>étoiles</i>; Fontainebleau: <i>ouvrage d'art</i>). The "
         "proper-name rule relies on capital letters: in <i>Office national des forêts</i>, <b>forêts</b> is coded N.",
         "<b>Closed list</b> (rule I1): <i>fleuve</i>, <i>basilique</i>, <i>aqueduc</i> are not coded with list v3, "
         "however central to the article.",
         "<b>Not yet tested</b>: the rules and the encoding were tuned on Courchaton, whose perfect score is not a "
         "test; Lyon's precision comes from a review by Claude, not by humans, and recall is unknown.",
         "French only; errors of the sentence splitter propagate."],
        "Use: the main keyword method. Trust its environment profile; read its response cells as an upper bound.")

    # --- Heritage -------------------------------------------------------------------------
    story += section(
        "Heritage · Links inherited from the previous sentence",
        "A-form, plus a link to the previous sentence when the response refers back to a place named there.",
        "Spans are those of A-form. A response with no environment in its own sentence inherits all the "
        "environments of the previous sentence (same section) when its sentence refers back: a place pronoun "
        "(<i>y</i>, not <i>il y a</i>; <i>là</i>; <i>celui-ci</i>; <i>ce lieu</i>…) or a sentence-initial "
        "<i>Il</i>, <i>Elle</i>, <i>Ils</i>, <i>Elles</i> that is not impersonal. Inherited links are flagged.",
        "« La basilique est un des repères les plus visibles… <b>religieuse</b> de Lyon. » / « <b>Elle</b> est "
        "fréquentée chaque année par plus d'un million de <b>visiteurs</b>. » → <i>visiteurs</i> (A) inherits C "
        "from the previous sentence: cell C × A.",
        [f"Lyon: links inherited in {int(g('Lyon', 'Heritage', 'inherited_sentences'))} sentences (PID cells in "
         f"{int(g('Lyon', 'Heritage', 'pid_sentences'))} sentences instead of "
         f"{int(g('Lyon', 'A-form', 'pid_sentences'))}); all are correct, and the Hybrid keeps them.",
         f"Courchaton: {int(g('Courchaton', 'Heritage', 'pid_cells'))} cell, unchanged; Fontainebleau: "
         f"{int(g('Fontainebleau', 'Heritage', 'inherited_sentences'))} inherited link."],
        ["<b>It almost never applies</b>: Wikipedia names the place again rather than writing <i>on s'y "
         "promène</i>, and most responses without an environment are false ones (<i>projet</i>, <i>critique</i> "
         "for a person) that nothing links to a place.",
         "<b>The previous sentence must contain a list word</b>: « Le comte d'Artois <b>y</b> fit courir… » follows "
         "a sentence without one, so nothing is inherited.",
         "<b>Narrow markers</b>: « <b>Cette pratique</b>, devenue emblématique » refers to the streets of the "
         "previous sentence but is not a marker; widening the markers would add false links.",
         "<b>Il/Elle may be a person</b>, and all the environments of the previous sentence are inherited, not "
         "the antecedent alone.",
         "<b>Against rule D7</b>: human coders link a response only within its sentence, so every inherited link "
         "would count as an error against the human reference."],
        "Use: drop it from the main methods and mention it as a tested idea (a negative result). If links across "
        "sentences are wanted, rule D7 must change first, and the Hybrid is better placed to make them.")

    # --- Hybrid ---------------------------------------------------------------------------
    hyb_lead = ("A-form for the environments, and an LLM that checks every response and chooses its links." +
                (" <b>The figures below are a preview</b>: no API key was available, so the LLM answers were "
                 "written by Claude Opus 5.5 inside a Claude Code session with the exact prompt of the method; "
                 "they must be rerun through the API before being quoted." if session else ""))
    story += section(
        "Hybrid · A-form + LLM check of the responses",
        hyb_lead,
        bullets([
            "Environments are kept exactly as A-form codes them.",
            "Each sentence with at least one response candidate is sent once to the LLM, with the previous "
            "sentence (to understand <i>il</i>, <i>elle</i>, <i>y</i>), the section title, the candidates (word, "
            "code, list entry) and the environment words of the sentence (with ids). The instructions are rules "
            "D4, D6 and D7 of the manual.",
            "The answer is JSON (fixed schema): for each candidate, <i>valid</i>, <i>links</i> (ids of environment "
            "words of the same sentence) and a reason of at most 12 words. Invalid responses are dropped; valid "
            "ones get the LLM's links. A refusal or an error keeps the A-form coding, flagged.",
            f"Model {hybrid.MODEL}, effort {hybrid.EFFORT}, prompt {hybrid.PROMPT_VERSION}; every answer is cached "
            "with its exact request (data/llm/hybrid_answers.jsonl) so that a run can be audited and repeated. "
            "The LLM never adds a word: the list stays closed.",
        ]),
        "Kept: « la tour Part-Dieu, <b>surnommée</b> « le crayon » par les Lyonnais » (R, linked to "
        "<i>quartier</i>); « Les championnats d'Europe de <b>patinage</b> artistique se sont déroulés dans la "
        "<i>ville</i> » (A). Dropped: « radio locale commerciale <b>proposant</b> des hits », « le docteur "
        "Dubernard, <b>célèbre</b> chirurgien lyonnais », « Maison de la <b>danse</b> ».",
        [f"Lyon{hybrid_flag}: {int(g('Lyon', 'Hybrid', 'responses'))} of "
         f"{int(g('Lyon', 'A-form', 'responses'))} response candidates kept; PID cells in "
         f"{int(g('Lyon', 'Hybrid', 'pid_sentences'))} sentences instead of "
         f"{int(g('Lyon', 'A-form', 'pid_sentences'))}. Dropped: <i>projet</i>, <i>proposer</i>, <i>danse</i> as "
         "an art or a name, <i>action</i>…; kept: nicknames, reputations, real visitors.",
         f"Fontainebleau{hybrid_flag}: {int(g('Fontainebleau', 'Hybrid', 'responses'))} of "
         f"{int(g('Fontainebleau', 'A-form', 'responses'))} kept (royal hunts and climbing in the forest, "
         f"visitors, the forest's reputation); PID cells in {int(g('Fontainebleau', 'Hybrid', 'pid_sentences'))} "
         f"sentences instead of {int(g('Fontainebleau', 'A-form', 'pid_sentences'))}.",
         "Courchaton: unchanged (its single response, <i>célèbre</i>, is kept and linked to N)."],
        (["<b>A preview, not a run</b>: the answers were written in a Claude Code session, not obtained through "
          "the API; they are not reproducible as such."] if session else []) + [
         "<b>Not measured yet</b>: no human has judged the response candidates, and the Lyon review sample was "
         "made by the same model, so there is no independent score of the Hybrid.",
         "<b>It cannot add what A-form missed</b>: recall is bounded by A-form's candidates (closed list, forms).",
         "<b>Environment errors stay</b>: <i>forêts</i> in <i>Office national des forêts</i>, heraldic "
         "<i>fleurs de lys</i> (list v3) are still coded N.",
         "<b>Borderline cases depend on the prompt</b>: a facility name (<i>site d'escalade</i>, <i>sentier de "
         "grande randonnée</i>, <i>piste de ski</i>), dancers, charity <i>actions</i>; another model or prompt may "
         "decide otherwise, so these cases must be written into the prompt and the manual alike.",
         "<b>Cost, time and dependency</b>: one API call per sentence with a candidate, a credential, a provider "
         "and a model version; outputs can vary between runs, so the paper protocol asks for fixed versions and "
         "repeated runs."],
        "Use: the candidate method for the PID cells. Run it through the API, then measure it on a human "
        "judgment of the response candidates and on the human coding of Lyon.")

    # --- Hybrid + Heritage ----------------------------------------------------------------
    story += [CondPageBreak(4 * cm), Paragraph("Hybrid + Heritage", st["h1"]),
              P(f"The Hybrid, then the inheritance of Heritage on the responses it keeps. It differs from the Hybrid "
                f"only where Heritage acts: {int(g('Lyon', 'Hybrid + Heritage', 'pid_sentences'))} sentences with a "
                f"PID cell in Lyon instead of {int(g('Lyon', 'Hybrid', 'pid_sentences'))}, nothing elsewhere. It "
                f"has the limits of both."),
              Paragraph("Use: no reason to keep it apart from the Hybrid.", st["verdict"])]

    # --- common limits --------------------------------------------------------------------
    story += [CondPageBreak(6 * cm), Paragraph("Limits shared by all the algorithms", st["h1"])] + bullets([
        "<b>What the text can show</b>: a Wikipedia article is written in a neutral style; it states what stands "
        "in a place far more than what people feel or do there. Responses are rare whatever the method, and the "
        "matrices describe how a commune is presented, not how it is lived.",
        "<b>Small and partial references</b>: Courchaton has 50 reference words and a single response, and served "
        "to tune the rules. The human coding of Lyon is in progress, on revision 241194072, while the algorithms "
        "read revision 241583218 (three small edits apart). Fontainebleau has no human coding and served as an "
        "early smoke test.",
        "<b>The sentence is the unit</b>: links never cross sentences (except Heritage), and the matrix counts "
        "sentences, so long articles and standard paragraphs (climate, land cover) weigh on the profile.",
        "<b>The list decides what can be found</b>: everything depends on list v3 (one French term per tag); "
        "list v4, a proposal, changes the figures (docs/keyword_lists.md).",
        "<b>French only</b>: other language editions need their own lists and rules.",
    ])

    story += [KeepTogether([Paragraph("How to run", st["h1"]), Paragraph(
        "python src/keyword_coder.py --method a | a_plus | a_form<br/>"
        "python src/hybrid.py --sentences &lt;sentences.parquet&gt;   (needs ANTHROPIC_API_KEY; --offline: cache "
        "only)<br/>"
        "python src/heritage.py --spans &lt;spans.csv&gt; --sentences &lt;sentences.parquet&gt;<br/>"
        "python src/compare_methods.py   (all methods on the pilot articles, matrices included)<br/>"
        "python src/algorithms_report.py   (this document)", st["example"]),
        P("Earlier prototype, kept for reference: src/classify_keywords.py coded whole sentences with lexicon v0 "
          "(several French terms per tag, 1 November); it was replaced by word-level coding with list v3.", "sub")])]

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=1.7 * cm, rightMargin=1.7 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title="Keyword coding algorithms", author="Desirable Cities (UTSEUS EG01)")
    try:
        doc.build(story)
    except PermissionError:
        sys.exit(f"cannot write {path}: the file is open in another program (PDF viewer). Close it and run again.")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    write_pdf(OUT, load_figures())
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
