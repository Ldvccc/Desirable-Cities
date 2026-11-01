import copy
import json

import pytest
from jsonschema import Draft202012Validator

import schema_utils as su

EXAMPLES = su.ROOT / "schema" / "examples" / "examples_fr.json"
SOURCES_OK = {"thesis", "extension", "proposal"}


@pytest.fixture(scope="module")
def lexicon():
    return su.load_lexicon()


@pytest.fixture(scope="module")
def schema():
    return su.load_schema()


@pytest.fixture(scope="module")
def examples():
    return json.loads(EXAMPLES.read_text(encoding="utf-8"))


# --- lexicon -----------------------------------------------------------------

def test_lexicon_has_the_six_categories(lexicon):
    assert tuple(lexicon["environments"]) == su.ENVIRONMENTS
    assert tuple(lexicon["responses"]) == su.RESPONSES


def test_every_subcategory_is_sourced(lexicon):
    for group in ("environments", "responses"):
        for cat in lexicon[group].values():
            for sub in cat["subcategories"]:
                assert sub["source"] in lexicon["sources"], sub["id"]
                assert sub["status"] in SOURCES_OK, sub["id"]
                assert sub.get("ref"), sub["id"]


def test_every_term_has_french_forms(lexicon):
    for t in su.iter_terms(lexicon):
        assert t["fr"], t["tag"]
        assert all(f == f.lower() for f in t["fr"]), t["tag"]


def test_tags_are_unique(lexicon):
    tags = [t["tag"] for t in su.iter_terms(lexicon)]
    assert len(tags) == len(set(tags))


def test_reflections_have_no_thesis_terms(lexicon):
    """The thesis gives no keyword list for reflections (p. 380, p. 537)."""
    statuses = {t["status"] for t in su.iter_terms(lexicon) if t["category"] == "reflection"}
    assert statuses == {"proposal"}


def test_nine_public_space_types(lexicon, schema):
    ids = [t["id"] for t in lexicon["facets"]["public_space_types"]["types"]]
    assert len(ids) == 9
    assert ids == schema["properties"]["public_space_types"]["items"]["enum"]


def test_slug():
    assert su.slug("square/plaza") == "square_plaza"
    assert su.slug("stars-full") == "stars_full"
    assert su.slug("Working out") == "working_out"


# --- schema ------------------------------------------------------------------

def test_schema_is_valid_json_schema(schema):
    Draft202012Validator.check_schema(schema)


def test_examples_are_valid(examples, schema, lexicon):
    assert su.validate_records(examples, schema, lexicon) == {}


def test_missing_field_is_rejected(examples, schema, lexicon):
    rec = copy.deepcopy(examples[0])
    del rec["annotator"]
    assert su.validate_records([rec], schema, lexicon)


def test_unknown_category_is_rejected(examples, schema, lexicon):
    rec = copy.deepcopy(examples[0])
    rec["environments"][0]["category"] = "built"
    assert su.validate_records([rec], schema, lexicon)


def test_llm_run_needs_model_and_prompt_version(examples, schema, lexicon):
    rec = copy.deepcopy(examples[0])
    rec["annotator"] = {"kind": "llm", "id": "deepseek-chat", "date": "2026-11-01"}
    assert su.validate_records([rec], schema, lexicon)
    rec["annotator"].update(model_version="deepseek-chat-2026-10", prompt_version="p1")
    assert su.validate_records([rec], schema, lexicon) == {}


# --- consistency checks ------------------------------------------------------

def test_evidence_must_come_from_the_sentence(examples, lexicon):
    rec = copy.deepcopy(examples[0])
    rec["environments"][0]["evidence"] = "la Loire"
    errs = su.check_consistency(rec, su.valid_tags(lexicon))
    assert any("evidence" in e for e in errs)


def test_pid_cell_needs_both_labels(examples, lexicon):
    rec = copy.deepcopy(examples[0])            # natural only, no response
    rec["pid_cells"] = [{"environment": "natural", "response": "emotion"}]
    errs = su.check_consistency(rec, su.valid_tags(lexicon))
    assert any("absent response" in e for e in errs)


def test_tag_must_match_category(examples, lexicon):
    rec = copy.deepcopy(examples[0])
    rec["environments"][0]["tags"] = ["cultural.atmosphere.sacred"]
    errs = su.check_consistency(rec, su.valid_tags(lexicon))
    assert any("does not belong" in e for e in errs)


def test_unknown_tag_is_rejected(examples, lexicon):
    rec = copy.deepcopy(examples[0])
    rec["environments"][0]["tags"] = ["natural.water_features.ocean_liner"]
    errs = su.check_consistency(rec, su.valid_tags(lexicon))
    assert any("unknown tag" in e for e in errs)
