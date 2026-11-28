"""Écrit docs/methodes_codage_fr.pdf : présentation en français de chaque méthode de codage (liste utilisée,
règles, étapes, exemples, limites, coût, résultat).

Les exemples des méthodes par mots-clés sont recalculés par le code au moment de la génération ; les chiffres
viennent des rapports existants (lancer avant : python src/benchmark.py ... puis python src/final_report.py).

Usage :
    python src/presentation_fr.py
"""
import sys
from collections import Counter
from datetime import date

import benchmark as bm
import compare_coders as cc
import final_report as fr
import hybrid
import keyword_coder as kc
import llm_coder

ROOT = kc.ROOT
OUT = ROOT / "docs" / "methodes_codage_fr.pdf"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def coded(text: str, kw: dict, method: str) -> str:
    spans = kc.code_sentence(text, kc.build_matchers(kw, method), method)
    return ", ".join(f"<b>{s['text']}</b> {s['code']}" for s in spans) or "<i>rien</i>"


def main() -> None:
    sys.stdout.reconfigure(errors="replace")
    from reportlab.lib import colors
    from reportlab.lib.fonts import addMapping
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (CondPageBreak, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    d = fr.load()
    o = lambda art, m, part="all", k="f1": d["vs_opus"].get((art, m, part), {}).get(k, float("nan"))  # noqa: E731
    costs = d["costs"]

    def cost(model, method):
        r = costs[(costs["model"] == model) & (costs["method"] == method)]
        return (float(r.iloc[0]["cost"]), float(r.iloc[0]["seconds"]), int(r.iloc[0]["requests"])) if len(r) else (0, 0, 0)

    v3 = kc.load_list()
    v4 = kc.load_list(ROOT / "schema" / "keyword_list_v4.yaml")
    up = bm.upgrade_plus_list(v3, v4)
    E3 = list(kc.iter_entries(v3))
    src = Counter(e["src"] for e in E3)
    sec = Counter(e["section"] for e in E3)
    koinos = Counter(e["section"] for e in E3 if e["src"] == "K")
    n_exc3 = sum(len(e.get("exclude", [])) for e in E3)
    n_exc_up = sum(len(e.get("exclude", [])) for e in kc.iter_entries(up))
    n_forms = sum(1 for e in E3 if e.get("forms"))
    n_formes = sum(1 if e["pos"] in ("expr", "value") else sum(len(v) for v in kc.surface_forms(e).values())
                   for e in kc.merge_duplicates(E3))
    n_formes = round(n_formes, -2)
    ia_cost, ia_time, ia_req = cost("Opus 5.5", "IA")
    hy_cost, _, hy_req = cost("Haiku 5.5", "Hybrid")
    t_naive, t_up, t_upp = (cost("—", m)[1] for m in ("Naive", "Upgrade", "Upgrade +"))
    L, F, C = "Lyon", "Fontainebleau", "Courchaton"

    # --- styles ---------------------------------------------------------------------------------
    regular, bold = "Helvetica", "Helvetica-Bold"
    fonts = cc.find_font()
    if fonts:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts[0])))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts[1])))
        for b_, i_ in ((0, 0), (1, 0), (0, 1), (1, 1)):
            addMapping("DejaVu", b_, i_, "DejaVu-Bold" if b_ else "DejaVu")
        regular, bold = "DejaVu", "DejaVu-Bold"
    ink, grey, head = colors.HexColor("#1a1a1a"), colors.HexColor("#5f6368"), colors.HexColor("#e6ebf2")
    rule, accent, soft = colors.HexColor("#9aa3ad"), colors.HexColor("#1c5cab"), colors.HexColor("#f3f6fa")
    st = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=18, leading=22, textColor=ink),
        "sub": ParagraphStyle("s", fontName=regular, fontSize=8.6, leading=11, textColor=grey),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=13.5, leading=17, spaceBefore=10, spaceAfter=4,
                             textColor=accent),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=9.6, leading=12.5, spaceBefore=5, spaceAfter=1.5,
                             textColor=ink),
        "body": ParagraphStyle("b", fontName=regular, fontSize=9.1, leading=12.6, textColor=ink, spaceAfter=3),
        "bullet": ParagraphStyle("u", fontName=regular, fontSize=9, leading=12.3, textColor=ink, leftIndent=12,
                                 bulletIndent=2, spaceAfter=1.5),
        "ex": ParagraphStyle("e", fontName=regular, fontSize=8.6, leading=11.8, textColor=ink, backColor=soft,
                             borderPadding=(4, 6, 4, 6), leftIndent=6, spaceBefore=5, spaceAfter=6),
        "cell": ParagraphStyle("c", fontName=regular, fontSize=7.7, leading=9.5, textColor=ink),
        "hdr": ParagraphStyle("r", fontName=bold, fontSize=7.7, leading=9.5, textColor=ink),
        "note": ParagraphStyle("n", fontName=regular, fontSize=7.5, leading=9.7, textColor=grey, spaceAfter=4),
        "res": ParagraphStyle("v", fontName=bold, fontSize=9, leading=12.4, textColor=accent, spaceBefore=4,
                              spaceAfter=2),
    }

    def P(t, s="body"):
        return Paragraph(t, st[s])

    def bullets(items):
        return [Paragraph(t, st["bullet"], bulletText="•") for t in items]

    def table(data, widths, align_from=1, extra=()):
        data = [[Paragraph(str(h), st["hdr"]) for h in data[0]]] + [
            [x if not isinstance(x, str) else Paragraph(x, st["cell"]) for x in row] for row in data[1:]]
        t = Table(data, colWidths=[w * cm for w in widths], hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), regular), ("BACKGROUND", (0, 0), (-1, 0), head),
                               ("GRID", (0, 0), (-1, -1), 0.4, rule), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4)]
                              + list(extra)))
        return t

    def f2(x):
        return "–" if x != x else f"{x:.2f}".replace(".", ",")

    def card(title, lead, liste, regles, etapes, exemple, limites, cout, resultat):
        out = [CondPageBreak(6 * cm), KeepTogether([Paragraph(title, st["h1"]), P(lead)]),
               P("Liste utilisée", "h2"), P(liste), P("Règles appliquées", "h2")]
        out += bullets(regles) if isinstance(regles, list) else [P(regles)]
        out += [P("Comment ça marche", "h2")] + bullets(etapes)
        out += [P("Exemple", "h2"), Paragraph(exemple, st["ex"]), P("Ce qu'elle ne fait pas", "h2")]
        out += bullets(limites)
        out += [P("Coût et temps", "h2"), P(cout), Paragraph(resultat, st["res"])]
        return out

    today = date.today()
    story = [
        Paragraph("Les méthodes de codage : comment chacune fonctionne", st["title"]), Spacer(1, 3),
        P(f"Desirable Cities · UTSEUS EG01 · liste de mots-clés v3 · règles de codage manuel v2 · "
          f"{today.day} {MOIS[today.month - 1]} {today.year}", "sub"), Spacer(1, 6),
        Paragraph("Ce que toutes les méthodes font", st["h1"]),
        P("Chaque méthode lit les phrases d'un article Wikipédia en français (texte récupéré par l'API de "
          "Wikipédia, découpé en phrases) et repère des <b>mots</b>. À chaque mot, elle donne un <b>code</b> : "
          "trois <b>environnements</b> du cadre de J. Villar — <b>N</b> naturel, <b>C</b> culturel, <b>B</b> "
          "construit — et trois <b>réponses</b> des gens — <b>E</b> émotion, <b>A</b> action, <b>R</b> réflexion. "
          "Chaque réponse est ensuite <b>reliée</b> aux environnements de sa phrase : ce lien forme une case de "
          "la matrice 3 × 3 du cadre (par exemple N × A, « une action dans la nature »)."),
        P("Toutes les méthodes produisent le même résultat — une ligne par mot codé : la phrase, la position du "
          "mot, le mot, son code, ses liens et l'entrée de la liste dont il vient — ce qui permet de les comparer "
          "mot par mot."),
        Paragraph("La liste de mots-clés v3", st["h1"]),
        P(f"Toutes les méthodes s'appuient sur la même liste, écrite par l'équipe et validée avec les encadrants : "
          f"<b>{len(E3)} entrées</b>, un seul mot français par notion. Elle n'est jamais modifiée ; seule la "
          f"façon de reconnaître ses mots change d'une méthode à l'autre."),
    ]
    data = [["Origine des entrées", "Nombre", "Exemples"],
            ["Tags Koinos de la thèse (application Koinos)", str(src["K"]),
             f"hiver, rivière, forêt, musée, place, marcher, joie… (N {koinos['N']}, C {koinos['C']}, "
             f"B {koinos['B']}, E {koinos['E']}, A {koinos['A']})"],
            ["Noms des catégories et sous-catégories", str(src["G"]), "naturel, culturel, météo, transport…"],
            ["Éléments des cartes Emotion-naire", str(src["T"]), "repère, hôtel, restaurants, commerces…"],
            ["Extensions ajoutées par l'équipe", str(src["E"]),
             "église, mairie, école, château, relief, histoire, patrimoine, émotions négatives…"],
            ["Marqueurs de réflexion (la thèse n'en donne pas)", str(src["P"]),
             "célèbre, réputé, surnom, symbole, emblème, critique, projet…"],
            ["Total", str(len(E3)), f"N {sec['N']} · C {sec['C']} · B {sec['B']} · E {sec['E']} · "
                                    f"A {sec['A']} · R {sec['R']}"]]
    story.append(table(data, [6.0, 1.9, 9.5], extra=[("ALIGN", (1, 1), (1, -1), "CENTER"),
                                                     ("BACKGROUND", (0, -1), (-1, -1), soft)]))
    story.append(P(f"À côté de la liste, le fichier schema/keyword_list_v3.yaml contient un « encodage » des "
                   f"règles pour l'ordinateur : les formes dérivées de {n_forms} entrées (forêt → forestier), "
                   f"{n_exc3} expressions à exclure (« il a été élu », « prendre place », « bassin houiller »…), les "
                   f"mots qui demandent un contexte. Il ne change pas la liste, il dit comment la lire.", "note"))

    # overview
    story += [Paragraph("Les six manières de coder, en un coup d'œil", st["h1"])]
    data = [["Méthode", "Liste", "Reconnaît les formes ?", "Évite les pièges ?", "Juge les réponses ?",
             "Coût (3 articles)", "Accord avec Opus, Lyon (F1)"],
            ["Naive", "v3 telle quelle", "non (mot exact, +s/x)", "non", "non", "0 €, secondes", f2(o(L, "Naive"))],
            ["Upgrade", "v3 + encodage Courchaton", "oui", "oui, liste d'exclusions", "non", "0 €, secondes",
             f2(o(L, "Upgrade"))],
            ["Upgrade +", "v3 + exclusions Courchaton et Lyon", "oui", "oui, plus d'exclusions", "non",
             "0 €, secondes", f2(o(L, "Upgrade +"))],
            ["Hybride", "v3 + exclusions (comme Upgrade +)", "oui", "oui", "oui, par Claude Haiku 5.5",
             f"{hy_cost:.2f} $".replace(".", ","), f2(o(L, fr.HYB))],
            ["IA (référence)", "v3 donnée à Claude Opus 5.5 avec le manuel", "oui, elle décide",
             "oui, d'après le sens", "oui", f"{ia_cost:.2f} $, ~{ia_time / 60:.0f} min".replace(".", ","),
             "référence"],
            ["Codage humain", "v3 et le manuel, sur PDF", "oui", "en principe", "oui", "≈ 20–25 min par codeur "
                                                                                    "(Courchaton)",
             f2(o(L, fr.HUM))]]
    story.append(table(data, [2.3, 3.4, 2.2, 2.4, 2.2, 2.6, 2.3],
                       extra=[("ALIGN", (6, 1), (6, -1), "CENTER"), ("BACKGROUND", (0, 5), (-1, 5), soft)]))
    story.append(P("F1 : accord avec la référence (1 = identique). Il combine la part des mots d'Opus que la "
                   "méthode retrouve et la part de ses mots qu'Opus a aussi codés (même mot, même code).", "note"))

    # --- cards -----------------------------------------------------------------------------------
    story.append(PageBreak())
    story += card(
        "1. Naive — chercher les mots tels qu'ils sont écrits",
        "La méthode la plus simple possible : elle sert de point de départ pour mesurer ce qu'apportent les règles.",
        f"La liste v3 complète ({len(E3)} entrées), mot pour mot, sans l'encodage.",
        "Aucune. Les règles du manuel ne sont pas appliquées.",
        ["Pour chaque entrée de la liste, chercher le mot exact dans la phrase : mot entier, sans tenir compte "
         "des majuscules, avec un s ou un x final possible (église → églises).",
         "Chaque mot trouvé reçoit le code de sa catégorie dans la liste.",
         "Chaque réponse (E, A, R) est reliée à tous les environnements de la phrase."],
        f"« Il a été élu maire. » → {coded('Il a été élu maire.', v3, 'a_plus')} : le verbe pris pour la saison.<br/>"
        f"« la région culturelle » → {coded('la région culturelle', v3, 'a_plus')} : le féminin de culturel n'est "
        f"pas reconnu.<br/>« selon Météo-France » → {coded('selon Météo-France', v3, 'a_plus')} : un nom propre "
        f"est codé.",
        ["Ne reconnaît ni les féminins, ni les conjugaisons, ni les mots dérivés (culturelle, climatiques, "
         "forestier).",
         "Code les homonymes (« a été », « fiscalité propre ») et les morceaux de noms propres.",
         "Code toute réponse sans vérifier qu'elle concerne vraiment des gens."],
        f"Gratuit ; {t_naive:.0f} secondes pour les trois articles (environ 1 900 phrases).",
        f"Accord avec Opus : {f2(o(L, 'Naive'))} à Lyon, {f2(o(F, 'Naive'))} à Fontainebleau ; réponses "
        f"{f2(o(L, 'Naive', 'resp'))} à Lyon.")

    story += card(
        "2. Upgrade — appliquer les règles du manuel",
        "Le même principe, mais l'ordinateur applique les règles de codage comme un codeur humain.",
        f"La liste v3 et son encodage : formes dérivées de {n_forms} entrées, {n_exc3} exclusions, contextes. "
        f"Les exclusions ont été écrites en codant Courchaton (et trois d'entre elles lors d'un premier essai "
        f"sur Fontainebleau).",
        ["I1 — formes : pluriels, féminins, conjugaisons et mots de même racine (forêt → forestier).",
         "I3 — l'expression la plus longue l'emporte (« voie ferrée », pas « voie »).",
         "I4 — homonymes et expressions figées exclus (« il a été élu », « prendre place », « son maire »).",
         "I5 — un mot de la liste qui n'est qu'un morceau de nom propre n'est pas codé (Arbonne-la-Forêt).",
         "I6 — toute valeur en °C est codée N.",
         "D1, D2 — le contexte décide pour calme, voitures, restaurants ; montagne est toujours N.",
         "D7 — chaque réponse est reliée aux environnements de sa phrase."],
        [f"Générer toutes les formes de chaque entrée (environ {n_formes:,} formes et expressions).".replace(",", " "),
         "Les chercher dans la phrase, puis écarter les noms propres, les homonymes et les expressions "
         "exclues.",
         "Si deux mots se chevauchent, garder le plus long.",
         "Relier chaque réponse aux environnements de la phrase."],
        f"« Il a été élu maire. » → {coded('Il a été élu maire.', v3, 'a_form')}.<br/>"
        f"« un climat tempéré à été frais » → {coded('un climat tempéré à été frais', v3, 'a_form')}.<br/>"
        f"« Arbonne-la-Forêt » → {coded('Arbonne-la-Forêt', v3, 'a_form')} ; « des températures climatiques » → "
        f"{coded('des températures climatiques', v3, 'a_form')} ; « 9,9 °C » → {coded('9,9 °C', v3, 'a_form')}.",
        ["Ne juge pas le sens : une réponse est codée même si personne ne ressent ni ne fait rien (« célèbre "
         "chirurgien », « projet de tramway », « radio proposant du jazz »).",
         "Ne connaît que les pièges qu'on lui a écrits ; chaque nouvel article en apporte d'autres.",
         "Ne code jamais un synonyme absent de la liste (fleuve, basilique)."],
        f"Gratuit ; {t_up:.0f} secondes pour les trois articles.",
        f"Accord avec Opus : {f2(o(L, 'Upgrade'))} à Lyon, {f2(o(F, 'Upgrade'))} à Fontainebleau ; "
        f"environnements {f2(o(L, 'Upgrade', 'env'))}, réponses {f2(o(L, 'Upgrade', 'resp'))} à Lyon.")

    story += card(
        "3. Upgrade + — ajouter les exclusions trouvées sur Lyon",
        "Upgrade, enrichi des pièges découverts en codant le long article de Lyon.",
        f"Les mêmes {len(E3)} mots de la liste v3 (aucun mot ajouté ni retiré), avec l'encodage de la version v4 : "
        f"{n_exc_up} exclusions au lieu de {n_exc3}, et les verbes reconnus seulement à la 3ᵉ personne.",
        "Les mêmes qu'Upgrade, avec des exclusions en plus : fleurs de lys (blason), étoiles Michelin, "
        "places assises, permis de construire, « inspiré de », travaux (chantier), patinoire (bâtiment)…",
        ["Identique à Upgrade, avec la liste d'exclusions élargie.",
         "Les verbes ne sont reconnus qu'aux formes de 3ᵉ personne, à l'infinitif et aux participes (un article "
         "encyclopédique n'écrit pas « tu joues ») : « joues » n'est plus pris pour jouer."],
        f"« trois fleurs de lys d'or » → Upgrade : {coded('trois fleurs de lys d’or', v3, 'a_form')} ; "
        f"Upgrade + : {coded('trois fleurs de lys d’or', up, 'a_form')}.<br/>"
        f"« des joues de porc » → Upgrade : {coded('des joues de porc', v3, 'a_form')} ; Upgrade + : "
        f"{coded('des joues de porc', up, 'a_form')}.<br/>"
        f"Mais « les journées de chasses » → Upgrade : {coded('les journées de chasses', v3, 'a_form')} ; "
        f"Upgrade + : {coded('les journées de chasses', up, 'a_form')} (une vraie chasse perdue).",
        ["Les mêmes limites qu'Upgrade.",
         "Ses exclusions ont été écrites en regardant Lyon : elles aident peu sur un autre article."],
        f"Gratuit ; {t_upp:.0f} secondes pour les trois articles.",
        f"Accord avec Opus : {f2(o(L, 'Upgrade +'))} à Lyon, {f2(o(F, 'Upgrade +'))} à Fontainebleau ; "
        f"réponses {f2(o(L, 'Upgrade +', 'resp'))} à Lyon.")

    story += card(
        "4. Hybride — Upgrade + et un petit modèle d'IA pour les réponses",
        "Les mots-clés trouvent les environnements ; une IA rapide et bon marché vérifie seulement les réponses.",
        "Les mots trouvés par Upgrade + (liste v3 + toutes les exclusions). L'IA ne peut ni ajouter un mot, ni "
        "changer un code : la liste reste fermée.",
        ["D4 — une émotion ou une action ne compte que si des gens la vivent (pas un nom de bâtiment, pas un "
         "document).",
         "D6 — une réflexion ne compte que si le texte rapporte ce que les gens pensent du lieu (réputation, "
         "surnom, symbole), pas la célébrité d'une personne ni un projet.",
         "D7 — l'IA choisit les mots d'environnement de la phrase auxquels la réponse se rapporte."],
        ["Upgrade + code la phrase.",
         "Chaque phrase qui contient une réponse est envoyée à Claude Haiku 5.5 avec la phrase précédente "
         "(pour comprendre « il », « elle », « y »), les réponses candidates et les mots d'environnement.",
         "Haiku répond dans un format fixe : pour chaque réponse, valide ou non, ses liens, une raison courte.",
         "Les réponses jugées fausses sont retirées ; les environnements ne changent pas."],
        "« la tour Part-Dieu, <b>surnommée</b> « le crayon » par les Lyonnais » → gardée (« surnom donné par "
        "les Lyonnais »).<br/>« radio locale commerciale <b>proposant</b> des hits » → retirée (« une offre, pas "
        "une réflexion »).<br/>« le docteur Dubernard, <b>célèbre</b> chirurgien » → retirée (« célébrité d'une "
        "personne »).<br/>Mais « un château <b>célèbre</b> » → retirée aussi, alors que c'est la réputation du lieu.",
        ["Haiku est trop strict : il retire aussi de vraies réponses (un château célèbre, un site d'escalade).",
         "Ne corrige pas les erreurs sur les environnements, et ne trouve rien qu'Upgrade + aurait manqué."],
        f"{hy_cost:.2f} $ pour les trois articles ({hy_req} requêtes courtes) ; durée des appels non "
        f"mesurée lors de ce lancement.".replace(".", ",", 1),
        f"Accord avec Opus : {f2(o(L, fr.HYB))} à Lyon, {f2(o(F, fr.HYB))} à Fontainebleau ; réponses "
        f"{f2(o(L, fr.HYB, 'resp'))} à Lyon (Upgrade + : {f2(o(L, 'Upgrade +', 'resp'))}) mais "
        f"{f2(o(F, fr.HYB, 'resp'))} à Fontainebleau (Upgrade + : {f2(o(F, 'Upgrade +', 'resp'))}).")

    story += card(
        "5. IA — Claude Opus 5.5 code l'article comme un expert (la référence)",
        "Le grand modèle d'IA lit l'article et code lui-même chaque mot, avec les mêmes documents que les "
        "codeurs humains. C'est la référence à laquelle toutes les autres méthodes sont comparées.",
        "La liste v3 complète, donnée en texte, avec pour chaque entrée les formes dérivées de l'encodage comme "
        "pistes (histoire [historique, historien…]) ; l'IA peut reconnaître d'autres mots de même racine.",
        ["Le manuel de codage v2 en entier (les mêmes règles que les humains).",
         "Les mêmes précisions sur D4 et D6 que l'Hybride.",
         "Une consigne : coder toutes les formes et dérivés de la liste, juger les pièges d'après le sens de la "
         "phrase, et ne pas laisser un mot de côté par prudence."],
        ["L'article est envoyé par paquets de 20 phrases (97 requêtes pour les trois articles).",
         "Claude Opus 5.5 renvoie, dans un format fixe, chaque mot codé : la phrase, le mot tel qu'écrit, son "
         "code, l'entrée de la liste et les liens des réponses.",
         "Chaque mot est retrouvé dans la phrase ; toutes les réponses sont gardées en mémoire (cache) pour "
         "pouvoir vérifier et refaire le calcul sans payer."],
        "« Courchaton était autrefois <b>célèbre</b> pour ses <b>vignes</b> et ses <b>vergers</b> de "
        "mirabelliers. » → célèbre R (lié à N), vignes N (forme de vignoble), vergers N ; mirabelliers, un arbre "
        "précis, n'est pas codé.<br/>« la région culturelle et <b>historique</b> » → historique C (dérivé "
        "d'histoire), que Naive ne trouve pas.",
        ["Il n'a été lancé qu'une fois : sa stabilité d'un lancement à l'autre n'est pas encore mesurée.",
         "Il dépend d'un fournisseur et d'une version de modèle ; il coûte de l'argent et prend du temps.",
         "Il peut lui aussi se tromper : sur Courchaton, il laisse de côté 2 mots (nature, communauté) que "
         "l'un des deux codeurs avait codés."],
        f"{ia_cost:.2f} $ pour les trois articles, soit environ 0,002 $ par phrase ; {ia_time / 60:.0f} minutes "
        f"d'appels cumulés (quelques minutes d'attente en parallèle).".replace(".", ",", 1),
        f"Testé contre les humains : à Lyon, {100 * d['vs_human'][(fr.REF, 'raw', 'all')]['precision']:.0f} % de "
        f"ses mots sont aussi codés par les humains, et il retrouve "
        f"{100 * d['vs_human'][(fr.REF, 'raw', 'all')]['recall']:.0f} % des leurs ; sur Courchaton, 48 mots sur 50, "
        f"aucun en trop.")

    story += card(
        "6. Le codage humain — ce qui sert à tester la référence",
        "Deux codeurs surlignent les mots dans un PDF de l'article en suivant le manuel. Trop long et trop "
        "sujet aux erreurs pour servir de référence, il sert à vérifier qu'Opus code comme un humain attentif.",
        "La liste v3 (PDF) et le manuel de codage v2.",
        "Toutes les règles du manuel, appliquées à la main.",
        ["Courchaton : deux codeurs codent tout l'article (50 mots au total).",
         "Lyon : deux codeurs se partagent l'article (phrases 0 à 599, puis 600 à 1 493) : 1 802 mots.",
         "Fontainebleau : pas de codage humain."],
        f"Des erreurs nettes, contraires au manuel, dans le codage de Lyon : {int((d['removed']['entry'] == 'son').sum())} "
        f"« <b>son</b> » possessifs codés comme un son (« son territoire ») et "
        f"{int((d['removed']['entry'] == 'été').sum())} « <b>été</b> » après avoir codés comme la saison (« a été "
        f"construit »).",
        ["Long : environ 20 à 25 minutes par codeur pour Courchaton (38 phrases) ; Lyon compte 1 494 phrases.",
         "Sur Lyon, chaque partie n'a été codée qu'une fois : l'accord entre codeurs ne peut pas être mesuré."],
        "Du temps humain ; pas de coût d'API.",
        f"Accord avec Opus : {f2(o(C, fr.HUM))} à Courchaton, {f2(o(L, fr.HUM))} à Lyon (réponses "
        f"{f2(o(L, fr.HUM, 'resp'))}).")

    # --- same sentence, all methods, and conclusion ---------------------------------------------
    story += [CondPageBreak(8 * cm), Paragraph("Une même phrase, vue par chaque méthode", st["h1"]),
              P("« Courchaton était autrefois célèbre pour ses vignes et ses vergers de mirabelliers. » — la "
                "référence humaine code célèbre (R, lié à N), vignes et vergers (N).")]
    sent = "Courchaton était autrefois célèbre pour ses vignes et ses vergers de mirabelliers."
    data = [["Méthode", "Mots codés"],
            ["Naive", coded(sent, v3, "a_plus") + " — vignes manqué (forme de vignoble)"],
            ["Upgrade", coded(sent, v3, "a_form")], ["Upgrade +", coded(sent, up, "a_form")],
            ["Hybride", coded(sent, up, "a_form") + " — Haiku garde célèbre"],
            ["IA (Opus)", "<b>célèbre</b> R, <b>vignes</b> N, <b>vergers</b> N"]]
    story.append(table(data, [3.0, 14.4]))

    story += [Paragraph("Ce qu'il faut retenir", st["h1"])]
    story += bullets([
        f"<b>Les environnements</b> (l'essentiel du codage) sont trouvés presque pareil par toutes les méthodes "
        f"avec règles : Upgrade + s'accorde avec Opus à {f2(o(L, 'Upgrade +', 'env'))} à Lyon, gratuitement.",
        f"<b>Les réponses</b> demandent de comprendre le sens. Les mots-clés codent toute réponse, vraie ou "
        f"fausse ({f2(o(L, 'Upgrade +', 'resp'))} à Lyon) ; Haiku en retire trop ; seul Opus les juge bien.",
        f"<b>Pour toutes les communes</b> : Upgrade + pour les environnements, et Opus là où les réponses "
        f"comptent (environ 0,002 $ par phrase), ou sur un échantillon de communes.",
        "<b>Les listes ne changent jamais</b> : chaque amélioration passe par l'encodage des règles (Upgrade, "
        "Upgrade +) ou par la façon de juger (Hybride, IA).",
    ])
    story.append(P("Détails et chiffres : docs/results_benchmark.pdf · prompts exacts : docs/llm_prompts.md · "
                   "différences entre listes : docs/keyword_lists.md.", "note"))

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm,
                            bottomMargin=1.5 * cm, title="Les méthodes de codage",
                            author="Desirable Cities (UTSEUS EG01)")
    try:
        doc.build(story)
    except PermissionError:
        sys.exit(f"impossible d'écrire {OUT} : le fichier est ouvert dans un autre programme. Fermez-le et relancez.")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
