import pandas as pd
import pytest

import split_sentences as ss


@pytest.mark.parametrize("text, expected", [
    ("La ville fut fondée en 43 av. J.-C. par Plancus. Elle devint capitale.",
     ["La ville fut fondée en 43 av. J.-C. par Plancus.", "Elle devint capitale."]),
    ("La région est occupée dès 600 av. J.-C. Les Romains s'y installent.",
     ["La région est occupée dès 600 av. J.-C.", "Les Romains s'y installent."]),
    ("M. Dupont est maire. J. Martin lui succède.",
     ["M. Dupont est maire.", "J. Martin lui succède."]),
    ("Soit env. 85 hab./km2. Elle est traversée par la R.N. 7, etc. Le climat est doux.",
     ["Soit env. 85 hab./km2.", "Elle est traversée par la R.N. 7, etc.", "Le climat est doux."]),
    ("Voir p. 12 et t. II. Bâtie au XIIe s. L'église fut agrandie.",
     ["Voir p. 12 et t. II.", "Bâtie au XIIe s.", "L'église fut agrandie."]),
    ("Est-ce une ville ? Non ! C'est un village... Il est petit.",
     ["Est-ce une ville ?", "Non !", "C'est un village...", "Il est petit."]),
    ("« La ville est belle. Elle est grande », écrit Stendhal. Il y revint.",
     ["« La ville est belle. Elle est grande », écrit Stendhal.", "Il y revint."]),
    ("L'église (XIIe s. Elle est romane) est classée. Le château aussi.",
     ["L'église (XIIe s. Elle est romane) est classée.", "Le château aussi."]),
    ("Elle compte 522 250 hab. en 2020. 12 ans plus tôt, elle en comptait moins.",
     ["Elle compte 522 250 hab. en 2020.", "12 ans plus tôt, elle en comptait moins."]),
    ("église Saint-Pierre, du XIIe siècle", ["église Saint-Pierre, du XIIe siècle"]),
    ("", []),
])
def test_split_french(text, expected):
    assert ss.split_paragraph(text, "fr") == expected


@pytest.mark.parametrize("text, expected", [
    ("Lyon is approx. 470 km from Paris. It was founded in 43 B.C. as Lugdunum.",
     ["Lyon is approx. 470 km from Paris.", "It was founded in 43 B.C. as Lugdunum."]),
    ("St. John's Cathedral is old. Mr. Smith of the U.S. Army visited it. See No. 5.",
     ["St. John's Cathedral is old.", "Mr. Smith of the U.S. Army visited it.", "See No. 5."]),
])
def test_split_english(text, expected):
    assert ss.split_paragraph(text, "en") == expected


def test_split_chinese_and_generic():
    assert ss.split_paragraph("里昂是法国的城市。它很美！", "zh") == ["里昂是法国的城市。", "它很美！"]
    assert ss.split_paragraph("Die Stadt liegt am Rhein. Dr. Müller war Bürgermeister.", "de") == [
        "Die Stadt liegt am Rhein.", "Dr. Müller war Bürgermeister."]


def test_split_is_lossless():
    """No character is lost: joining the sentences gives the text back."""
    text = "La ville est ancienne. Elle fut fondée en 43 av. J.-C. par M. Plancus ! Voir p. 12."
    assert " ".join(ss.split_paragraph(text, "fr")) == text


def test_split_text_drops_lines_without_letters():
    assert ss.split_text("Première ligne.\n\n1789\n---\n- église romane", "fr") == [
        "Première ligne.", "- église romane"]


def article(texte, insee="2A004", langue="fr", revision_id=123456):
    return {"insee": insee, "langue": langue, "revision_id": revision_id, "texte": texte}


TEXTE = ("Ajaccio est une commune. Elle est en Corse.\n\n== Histoire ==\nFondée en 1492. Elle grandit.\n\n"
         "=== Moyen Âge ===\nUn château.\n\n== Notes et références ==\nNote 1. Note 2.\n\n=== Liens ===\nUn lien.")


def test_article_sentences_ids_sections_and_skip():
    rows = ss.article_sentences(article(TEXTE))
    assert [r["text"] for r in rows] == ["Ajaccio est une commune.", "Elle est en Corse.",
                                         "Fondée en 1492.", "Elle grandit.", "Un château."]
    assert [r["sentence_id"] for r in rows] == [f"2A004-fr-123456-s{i}" for i in range(5)]
    assert [r["section_type"] for r in rows] == ["intro", "intro", "history", "history", "history"]
    assert rows[4]["section_titre"] == "Moyen Âge"
    assert rows[0]["n_mots"] == 4


def test_build_and_check_sentences_follow_the_schema():
    import json
    import re
    import schema_utils as su
    corpus = pd.DataFrame([article(TEXTE), article("Ajaccio is a commune. It is in Corsica.", langue="en",
                                                   revision_id=99)])
    sentences = ss.build_sentences(corpus)
    ss.check_sentences(sentences, corpus)
    schema = su.load_schema()
    pattern = schema["properties"]["sentence_id"]["pattern"]
    assert all(re.fullmatch(pattern, s) for s in sentences["sentence_id"])
    assert set(sentences["section_type"]) <= set(schema["properties"]["section_type"]["enum"])
    assert len(sentences) == 7


def test_empty_article_gives_no_sentence():
    assert ss.article_sentences(article("")) == []


def test_stats_shares_sum_to_100():
    corpus = pd.DataFrame([article(TEXTE)])
    table = ss.stats(ss.build_sentences(corpus))
    assert table["phrases"].sum() == 5
    assert round(table["part_pct"].sum()) == 100
