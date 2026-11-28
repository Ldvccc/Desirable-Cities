"""Tests of the methods Heritage (inherited links) and Hybrid (LLM check of the
responses). The LLM is replaced by a fake judge: no network call."""
import json

import pandas as pd
import pytest

import heritage
import hybrid
import keyword_coder as kc
import pid_matrix as pm


def sentences(*texts, section="Histoire"):
    return pd.DataFrame({"sentence_id": [f"s{i}" for i in range(len(texts))], "text": list(texts),
                         "insee": "1", "langue": "fr", "section_titre": section})


@pytest.fixture(scope="module")
def kw():
    return kc.load_list()


# --- Heritage ------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("On vient s'y promener le dimanche.", True),
    ("Elle est fréquentée par un million de visiteurs.", True),
    ("Celui-ci attire les promeneurs.", True),
    ("C'est là que les habitants se retrouvent.", True),
    ("Il y a un marché le samedi.", False),
    ("Il est possible qu'il s'agisse d'un lieu de culte.", False),
    ("Il s'agit d'un lieu de culte.", False),
    ("Les touristes visitent le musée, y compris le dimanche.", False),
    ("De là vient son nom.", False),
    ("Lyon attire les touristes.", False),
])
def test_refers_back(text, expected):
    assert heritage.refers_back(text) is expected


def test_inherited_link(kw):
    s = sentences("Le parc borde la rivière.", "On vient s'y promener.")
    spans = kc.code_sentences(s, kw, "a_form")
    assert spans[spans["code"] == "A"]["pid"].tolist() == ["0"]
    out = heritage.inherit_links(spans, s)
    a = out[out["code"] == "A"].iloc[0]
    assert a["link"] == "inherited" and set(a["pid"].split(",")) == {"N", "B"}
    assert heritage.parse_inherited(a["inherited"]) == {"N": ["rivière"], "B": ["parc"]}
    m = pm.pid_matrix(out, len(s))
    assert m["cells"][("B", "A")]["sentences"] == 1 and m["cells"][("B", "A")]["environment"] == {"parc": 1}
    assert m["cells"][("-", "A")]["sentences"] == 0 and m["inherited_sentences"] == 1
    assert m["env_sentences"]["B"] == 1                          # the 2nd sentence does not mention the park
    assert pm.cell_set(out) == {("s1", "N", "A"), ("s1", "B", "A")}


def test_no_inheritance_without_marker_or_across_sections(kw):
    s = sentences("Le parc borde la rivière.", "Les habitants se promènent.")
    out = heritage.inherit_links(kc.code_sentences(s, kw, "a_form"), s)
    assert (out["link"] == "inherited").sum() == 0
    s = sentences("Le parc borde la rivière.", "On vient s'y promener.")
    s.loc[1, "section_titre"] = "Culture"
    out = heritage.inherit_links(kc.code_sentences(s, kw, "a_form"), s)
    assert (out["link"] == "inherited").sum() == 0


def test_heritage_keeps_spans_with_their_own_environment(kw):
    s = sentences("Le parc borde la rivière.", "On s'y promène dans la forêt.")
    spans = kc.code_sentences(s, kw, "a_form")
    out = heritage.inherit_links(spans, s)
    assert (out["link"] == "inherited").sum() == 0
    assert out["pid"].tolist() == spans["pid"].tolist()


# --- Hybrid ----------------------------------------------------------------------------------

class FakeJudge:
    """Declares 'célèbre' invalid when it is about a person, valid otherwise,
    and links every valid response to the first environment word only."""

    def __init__(self):
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        out = []
        for c in request["candidates"]:
            valid = "chirurgien" not in request["sentence"]
            links = [request["environment_words"][0]["id"]] if valid and request["environment_words"] else []
            out.append({"id": c["id"], "valid": valid, "links": links, "reason": "test"})
        return {"status": "checked", "responses": out}


def test_build_requests(kw):
    s = sentences("Le village était célèbre pour ses vignes et ses vergers.", "La mairie est neuve.")
    reqs = hybrid.build_requests(kc.code_sentences(s, kw, "a_form"), s)
    assert len(reqs) == 1                                          # only sentences with a response
    sid, request, cand, env = reqs[0]
    assert sid == "s0" and [c["word"] for c in request["candidates"]] == ["célèbre"]
    assert [e["word"] for e in request["environment_words"]] == ["village", "vignes", "vergers"]
    assert request["previous_sentence"] == "" and request["section"] == "Histoire"
    json.dumps(request, ensure_ascii=False)                       # serialisable as sent to the API


def test_hybrid_drops_invalid_and_relinks(kw):
    s = sentences("Le village était célèbre pour ses vignes et ses vergers.",
                  "Le docteur, célèbre chirurgien, vit en ville.")
    spans = kc.code_sentences(s, kw, "a_form")
    kept, audit = hybrid.hybrid_spans(spans, s, FakeJudge(), workers=1)
    resp = kept[kept["code"] == "R"]
    assert len(resp) == 1 and resp.iloc[0]["sentence_id"] == "s0"
    assert resp.iloc[0]["pid"] == "B"                              # only 'village', chosen by the judge
    assert set(kept[kept["code"].isin(kc.ENV_CODES)].index) == set(spans[spans["code"].isin(kc.ENV_CODES)].index)
    assert audit["valid"].tolist() == [True, False]
    assert pm.cell_set(kept) == {("s0", "B", "R")}


def test_cache_answers_once(tmp_path, kw):
    s = sentences("Le village était célèbre pour ses vignes.")
    spans = kc.code_sentences(s, kw, "a_form")
    fake = FakeJudge()
    judge = hybrid.CachedJudge(tmp_path / "cache.jsonl", "test-model", fake)
    hybrid.hybrid_spans(spans, s, judge, workers=1)
    hybrid.hybrid_spans(spans, s, judge, workers=1)
    assert fake.calls == 1
    reloaded = hybrid.CachedJudge(tmp_path / "cache.jsonl", "test-model")       # offline
    kept, _ = hybrid.hybrid_spans(spans, s, reloaded, workers=1)
    assert (kept["code"] == "R").sum() == 1
    other = hybrid.CachedJudge(tmp_path / "cache.jsonl", "another-model")
    with pytest.raises(hybrid.MissingAnswers):
        hybrid.hybrid_spans(spans, s, other, workers=1)


def test_unjudged_candidates_keep_a_form_coding(kw):
    s = sentences("Le village était célèbre pour ses vignes.")
    spans = kc.code_sentences(s, kw, "a_form")
    kept, audit = hybrid.hybrid_spans(spans, s, lambda request: {"status": "refused", "responses": []}, workers=1)
    assert len(kept) == len(spans) and audit["status"].tolist() == ["refused"]
    assert kept[kept["code"] == "R"]["pid"].tolist() == spans[spans["code"] == "R"]["pid"].tolist()


def test_schema_is_strict():
    item = hybrid.SCHEMA["properties"]["responses"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == set(item["properties"])
