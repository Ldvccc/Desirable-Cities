import json

import pandas as pd
import pytest

import wikipedia_text as wt

EXTRACT = ("Fontainebleau est une commune française.\n\n\n== Géographie ==\n\n\n=== Localisation ===\n"
           "La ville est en Seine-et-Marne.\n\n\n=== Climat ===\nClimat océanique.\n\n\n== Histoire ==\n"
           "Le château date du XIIe siècle.\n\n\n== Population et société ==\n\n\n=== Démographie ===\n"
           "15 000 habitants.\n\n\n=== Santé ===\nUn hôpital.\n\n\n== Culture locale et patrimoine ==\n\n\n"
           "=== Lieux et monuments ===\nLe château.\n\n\n=== Personnalités liées à la commune ===\n"
           "Napoléon.\n\n\n== Voir aussi ==\n\n\n=== Bibliographie ===\nUn livre.\n\n\n=== Articles connexes ===\n")

API_ANSWER = {"batchcomplete": True, "query": {"pages": [{
    "pageid": 1, "ns": 0, "title": "Fontainebleau", "extract": EXTRACT,
    "revisions": [{"revid": 987654, "parentid": 1, "timestamp": "2026-10-30T10:00:00Z"}]}]}}
API_MISSING = {"batchcomplete": True, "query": {"pages": [{"title": "Xyz", "missing": True}]}}


@pytest.mark.parametrize("title, langue, expected", [
    ("Géographie", "fr", "geography"),
    ("Histoire", "fr", "history"),
    ("Politique et administration", "fr", "politics"),
    ("Population et société", "fr", "other"),
    ("Démographie", "fr", "demography"),
    ("Culture locale et patrimoine", "fr", "culture"),
    ("Lieux et monuments", "fr", "heritage"),
    ("Patrimoine naturel", "fr", "geography"),
    ("Personnalités liées à la commune", "fr", "personalities"),
    ("Voies de communication et transports", "fr", "transport"),
    ("Enseignement", "fr", "education"),
    ("Sports", "fr", "sport"),
    ("Économie", "fr", "economy"),
    ("Héraldique", "fr", "culture"),
    ("Notes et références", "fr", "skip"),
    ("Liens externes", "fr", "skip"),
    ("Toponymie", "fr", None),
    ("History", "en", "history"),
    ("Sights", "en", "heritage"),
    ("Notable people", "en", "personalities"),
    ("See also", "en", "skip"),
    ("References", "en", "skip"),
    ("Transport", "en", "transport"),
    ("Geschichte", "de", None),
])
def test_classify_section(title, langue, expected):
    assert wt.classify_section(title, langue) == expected


def test_clean_text_normalises_spaces_and_blank_lines():
    assert wt.clean_text("Une  commune française \n\n\n\n== Titre ==\r\n") == \
        "Une commune française\n\n== Titre =="


def test_parse_sections_structure_and_inheritance():
    sections = wt.parse_sections(wt.clean_text(EXTRACT), "fr")
    got = [(s["titre"], s["niveau"], s["type"]) for s in sections]
    assert got == [
        ("", 1, "intro"),
        ("Géographie", 2, "geography"),
        ("Localisation", 3, "geography"),
        ("Climat", 3, "geography"),
        ("Histoire", 2, "history"),
        ("Population et société", 2, "other"),
        ("Démographie", 3, "demography"),
        ("Santé", 3, "other"),                       # no rule: inherits the parent
        ("Culture locale et patrimoine", 2, "culture"),
        ("Lieux et monuments", 3, "heritage"),
        ("Personnalités liées à la commune", 3, "personalities"),
        ("Voir aussi", 2, "skip"),
        ("Bibliographie", 3, "skip"),
        ("Articles connexes", 3, "skip"),
    ]
    assert sections[0]["texte"] == "Fontainebleau est une commune française."
    assert sections[4]["texte"] == "Le château date du XIIe siècle."


def test_parse_sections_without_heading():
    sections = wt.parse_sections("Une seule phrase.", "fr")
    assert len(sections) == 1 and sections[0]["type"] == "intro"


def test_subsection_of_skip_stays_skipped_and_level_resets():
    sections = wt.parse_sections("== Références ==\n=== Histoire ===\nx\n== Histoire ==\ny", "fr")
    assert [s["type"] for s in sections] == ["intro", "skip", "skip", "history"]


def test_unknown_language_gives_other():
    sections = wt.parse_sections("Intro.\n\n== Geschichte ==\nText.", "de")
    assert [s["type"] for s in sections] == ["intro", "other"]


def test_parse_api_response():
    rec = wt.parse_api_response(API_ANSWER, "Fontainebleau")
    assert rec["missing"] is False
    assert rec["revision_id"] == 987654
    assert rec["revision_date"] == "2026-10-30T10:00:00Z"
    assert rec["texte"] == EXTRACT
    missing = wt.parse_api_response(API_MISSING, "Xyz")
    assert missing["missing"] is True and missing["texte"] is None
    assert wt.parse_api_response({"batchcomplete": True}, "Xyz")["missing"] is True


def titles_df():
    return pd.DataFrame([
        {"insee": "77186", "qid": "Q1", "langue": "fr", "titre": "Fontainebleau",
         "url": "https://fr.wikipedia.org/wiki/Fontainebleau"},
        {"insee": "77186", "qid": "Q1", "langue": "en", "titre": "Fontainebleau",
         "url": "https://en.wikipedia.org/wiki/Fontainebleau"},
        {"insee": "2A004", "qid": "Q2", "langue": "fr", "titre": "Ajaccio",
         "url": "https://fr.wikipedia.org/wiki/Ajaccio"},
    ])


def communes_df():
    return pd.DataFrame([
        {"insee": "77186", "qid": "Q1", "name": "Fontainebleau", "pop": 15000.0, "lat": 48.4, "lon": 2.7,
         "departement": "77", "taille": "10000-49999"},
        {"insee": "2A004", "qid": "Q2", "name": "Ajaccio", "pop": None, "lat": None, "lon": 8.7,
         "departement": "2A", "taille": ">=50000"},
    ])


def records():
    ok = wt.parse_api_response(API_ANSWER, "Fontainebleau")
    ok["date_extraction"] = "2026-11-10"
    short = dict(ok, texte="Ajaccio.", revision_id=5)
    return {("77186", "fr"): ok, ("77186", "en"): wt.parse_api_response(API_MISSING, "Fontainebleau"),
            ("2A004", "fr"): short}


def test_build_corpus_follows_the_data_contract():
    corpus = wt.build_corpus(titles_df(), communes_df(), records())
    wt.check_corpus(corpus, titles_df())
    assert list(zip(corpus["insee"], corpus["langue"])) == [("2A004", "fr"), ("77186", "fr")]   # missing: no row
    row = corpus[corpus["insee"] == "77186"].iloc[0]
    for col in ["insee", "qid", "langue", "titre", "url", "texte", "sections", "longueur",
                "population", "lat", "lon", "revision_id", "revision_date", "date_extraction"]:
        assert col in corpus.columns
    assert row["longueur"] == len(row["texte"])
    assert " " not in row["texte"] and "== Histoire ==" in row["texte"]
    assert row["population"] == 15000 and row["revision_id"] == 987654
    assert row["sections"][1] == {"titre": "Géographie", "niveau": 2, "type": "geography"}
    ajaccio = corpus[corpus["insee"] == "2A004"].iloc[0]
    assert pd.isna(ajaccio["population"]) and pd.isna(ajaccio["lat"])     # unknown stays empty


def test_corpus_survives_a_parquet_round_trip(tmp_path):
    corpus = wt.build_corpus(titles_df(), communes_df(), records())
    path = tmp_path / "corpus.parquet"
    corpus.to_parquet(path, index=False)
    back = pd.read_parquet(path)
    assert back["insee"].tolist() == ["2A004", "77186"]
    assert back.loc[1, "sections"][1]["type"] == "geography"
    assert back.loc[1, "revision_id"] == 987654


def test_coverage_counts_stubs():
    corpus = wt.build_corpus(titles_df(), communes_df(), records())
    cov = wt.coverage(corpus, communes_df())
    assert cov["articles"].sum() == 2
    assert cov.loc[cov["taille"] == ">=50000", "stubs"].iloc[0] == 1


class FakeResponse:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        return FakeResponse(API_ANSWER)


def test_get_page_downloads_once_then_uses_the_cache(tmp_path):
    row = titles_df().iloc[0]
    session = FakeSession()
    rec, fresh = wt.get_page(row, session, str(tmp_path))
    assert fresh and rec["revision_id"] == 987654 and rec["date_extraction"]
    url, params, headers = session.calls[0]
    assert url == "https://fr.wikipedia.org/w/api.php"
    assert params["titles"] == "Fontainebleau" and params["explaintext"] == 1
    assert "DesirableCities" in headers["User-Agent"]
    rec2, fresh2 = wt.get_page(row, session, str(tmp_path))
    assert not fresh2 and rec2 == rec and len(session.calls) == 1
    saved = json.loads((tmp_path / "fr" / "77186.json").read_text(encoding="utf-8"))
    assert saved["titre"] == "Fontainebleau"
    wt.get_page(row, session, str(tmp_path), refresh=True)
    assert len(session.calls) == 2
