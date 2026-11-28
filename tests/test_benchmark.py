"""Tests of the benchmark coders: the Upgrade + list and the IA (LLM) coder. No network."""
import pandas as pd
import pytest

import benchmark as bm
import keyword_coder as kc
import llm_coder


@pytest.fixture(scope="module")
def lists():
    v3 = kc.load_list()
    v4 = kc.load_list(kc.ROOT / "schema" / "keyword_list_v4.yaml")
    return v3, v4, bm.upgrade_plus_list(v3, v4)


def spans(text, kw, method="a_form"):
    return [(s["text"], s["code"]) for s in kc.code_sentence(text, kc.build_matchers(kw, method), method)]


def test_upgrade_plus_keeps_the_341_words_of_v3(lists):
    v3, _, up = lists
    words = lambda kw: [(e["section"], e["tag"], e["fr"]) for e in kc.iter_entries(kw)]      # noqa: E731
    assert words(up) == words(v3)
    assert up["encoding"] == {"third_person_only": True}
    assert "encoding" not in v3                                              # list v3 itself is untouched


def test_upgrade_plus_has_the_lyon_exclusions_but_no_new_word(lists):
    v3, _, up = lists
    assert ("fleurs", "N") in spans("trois fleurs de lys d'or", v3)
    assert spans("trois fleurs de lys d'or", up) == []
    assert spans("des joues de porc", up) == []                              # third-person verbs only
    assert spans("Le fleuve traverse la ville.", up) == [("ville", "B")]     # v4 additions are not used
    assert ("projet", "R") in spans("Le projet de tramway.", up)            # v4 removals are not applied


def test_ia_requests_and_spans():
    s = pd.DataFrame({"sentence_id": ["s0", "s1"], "text": ["Le parc et le parc.", "On s'y promène."],
                      "section_titre": ["", "Géographie"]})
    batches = llm_coder.build_requests(s, "Test", batch=1)
    assert len(batches) == 2 and batches[1][1]["sentences"][0] == {"i": 0, "section": "Géographie",
                                                                    "text": "On s'y promène."}
    answers = [{"spans": [{"i": 0, "word": "parc", "code": "B", "entry": "parc", "links": []},
                          {"i": 0, "word": "parc", "code": "B", "entry": "parc", "links": []},
                          {"i": 0, "word": "jardin", "code": "B", "entry": "jardin", "links": []}]},
               {"spans": [{"i": 0, "word": "promène", "code": "A", "entry": "se promener", "links": []}]}]
    out, lost = llm_coder.to_spans(batches, answers, dict(zip(s["sentence_id"], s["text"])))
    assert lost == 1                                                         # 'jardin' is not in the sentence
    assert list(zip(out["sentence_id"], out["start"], out["code"], out["pid"])) == [
        ("s0", 3, "B", ""), ("s0", 14, "B", ""), ("s1", 7, "A", "0")]


def test_ia_prompt_contains_the_manual_and_the_list(lists):
    v3, _, _ = lists
    prompt = llm_coder.system_prompt(v3)
    assert "I1. Form" in prompt and "D7. PID cells" in prompt
    assert "How the algorithm applies" not in prompt                        # coders do not see the algorithm notes
    assert "forêt" in prompt and "célèbre" in prompt


def test_overlap_agreement():
    a = pd.DataFrame({"sentence_id": ["s", "s"], "code": ["B", "N"], "start": [0, 10], "end": [4, 15]})
    b = pd.DataFrame({"sentence_id": ["s"], "code": ["B"], "start": [2], "end": [6]})
    assert bm.agreement(a, b) == 0.5 and bm.agreement(b, a) == 1.0
