import pandas as pd
import pytest

import classify_keywords as ck
import schema_utils as su


@pytest.fixture(scope="module")
def lexicon():
    return su.load_lexicon()


@pytest.fixture(scope="module")
def matchers(lexicon):
    return ck.build_matchers(lexicon)


def cats(labels, key):
    return [x["category"] for x in labels[key]]


def test_term_pattern_whole_words_plural_and_apostrophe():
    p = ck.term_pattern("cours d'eau")
    assert p.search("Deux cours d’eau traversent la commune")
    assert ck.term_pattern("forêt").search("Les Forêts domaniales")
    assert not ck.term_pattern("art").search("le départ du train")
    assert ck.term_pattern("rue piétonne").search("une rue  piétonne animée")


def test_english_forms():
    assert ck.english_forms("square/plaza") == ["square", "plaza"]
    assert ck.english_forms("river") == ["river"]


def test_french_sentence(matchers):
    labels = ck.classify_sentence(
        "Cette forêt, où les Parisiens aiment se promener, est un lieu réputé pour l'escalade.",
        "fr", matchers)
    assert cats(labels, "environments") == ["natural"]
    assert "action" in cats(labels, "responses") and "reflection" in cats(labels, "responses")
    assert {"environment": "natural", "response": "reflection"} in labels["pid_cells"]
    assert len(labels["pid_cells"]) == len(labels["environments"]) * len(labels["responses"])


def test_english_sentence(matchers):
    labels = ck.classify_sentence("The forest is popular among climbers who enjoy walking.", "en", matchers)
    assert "natural" in cats(labels, "environments")
    assert "action" in cats(labels, "responses")


def test_nothing_found(matchers):
    labels = ck.classify_sentence("Les scrutins européens voient la droite arriver en tête.", "fr", matchers)
    assert labels["environments"] == [] and labels["responses"] == [] and labels["pid_cells"] == []
    assert labels["register"] == "descriptive"


def test_naive_errors_are_kept(matchers):
    """Known weaknesses of the baseline: they are what algorithm B must fix."""
    labels = ck.classify_sentence("Le maire a été réélu.", "fr", matchers)
    assert cats(labels, "environments") == ["natural"]           # "été" read as the season


def test_register_markers(matchers):
    assert ck.classify_sentence("Une légende raconte que le roi s'y perdit.", "fr", matchers)["register"] == "imaginary"
    assert ck.classify_sentence("La ville a reçu le label Ville d'art et d'histoire.", "fr",
                                matchers)["register"] == "spectacle"


def test_evidence_is_copied_from_the_sentence(matchers):
    text = "La Seine et ses QUAIS accueillent des promeneurs."
    labels = ck.classify_sentence(text, "fr", matchers)
    for x in labels["environments"] + labels["responses"]:
        assert x["evidence"] in text


def sentences_df():
    return pd.DataFrame([
        {"sentence_id": "77186-fr-1-s0", "insee": "77186", "langue": "fr", "revision_id": 1, "index": 0,
         "section_titre": "", "section_type": "intro",
         "text": "On aime se promener dans la forêt, un lieu réputé.", "n_mots": 10},
        {"sentence_id": "77186-fr-1-s1", "insee": "77186", "langue": "fr", "revision_id": 1, "index": 1,
         "section_titre": "Politique", "section_type": "politics",
         "text": "Le conseil municipal compte 33 membres.", "n_mots": 6},
        {"sentence_id": "2A004-en-7-s0", "insee": "2A004", "langue": "en", "revision_id": 7, "index": 0,
         "section_titre": "", "section_type": "intro",
         "text": "Ajaccio has a beach where people swim.", "n_mots": 7},
    ])


def test_annotate_produces_valid_records(lexicon):
    records = ck.annotate(sentences_df(), lexicon, today="2026-11-12")
    assert su.validate_records(records, lexicon=lexicon) == {}
    assert records[0]["annotator"] == {"kind": "keywords", "id": "lexicon_naive",
                                       "lexicon_version": str(lexicon["version"]), "date": "2026-11-12"}


def test_flat_table_and_pid_matrix(lexicon):
    records = ck.annotate(sentences_df(), lexicon, today="2026-11-12")
    flat = ck.flat_table(records)
    assert list(flat["sentence_id"]) == list(sentences_df()["sentence_id"])
    matrix = ck.pid_matrix(records)
    assert list(matrix.index) == ["natural", "cultural", "constructural"]
    assert list(matrix.columns) == ["emotion", "action", "reflection", "none"]
    assert matrix.loc["natural", "action"] > 0
    assert (matrix.values <= 100).all()


def test_public_space_type(matchers):
    labels = ck.classify_sentence("La place d'Armes est bordée de cafés.", "fr", matchers)
    assert labels["public_space_types"] == ["public_square"]
