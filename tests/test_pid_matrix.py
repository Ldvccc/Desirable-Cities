"""Tests of the PID matrices (environments x responses, counted in sentences)."""
import pandas as pd
import pytest

import compare_coders as cc
import keyword_coder as kc
import pid_matrix as pm


def spans(*rows):
    """rows: (sentence_id, code, entry, pid)"""
    return pd.DataFrame(rows, columns=["sentence_id", "code", "entry", "pid"])


def test_cells_are_counted_in_sentences():
    s = spans(("s1", "B", "musée", ""), ("s1", "A", "visiter", "B"), ("s1", "A", "visiter", "B"),
              ("s2", "N", "forêt", ""), ("s2", "B", "rue", ""),
              ("s3", "R", "célèbre", "0"))
    m = pm.pid_matrix(s, n_sentences=5)
    cells = m["cells"]
    assert cells[("B", "A")]["sentences"] == 1                       # two A spans, one sentence
    assert cells[("B", "A")]["response"] == {"visiter": 2}
    assert cells[("B", "A")]["environment"] == {"musée": 1}
    assert cells[("N", "-")]["sentences"] == 1 and cells[("B", "-")]["sentences"] == 1   # s2: description only
    assert cells[("-", "R")]["sentences"] == 1                       # response with no environment
    assert cells[("-", "-")]["sentences"] == 2                       # s4, s5: no keyword
    assert m["env_only_sentences"] == 1 and m["linked_sentences"] == 1 and m["unlinked_sentences"] == 1
    assert sum(c["sentences"] for (e, r), c in cells.items() if e in pm.ENVS and r in pm.RESPONSES) == 1


def test_explicit_link_limits_the_cells():
    s = spans(("s1", "N", "vergers", ""), ("s1", "B", "village", ""), ("s1", "R", "célèbre", "N"))
    cells = pm.pid_matrix(s, 1)["cells"]
    assert cells[("N", "R")]["sentences"] == 1
    assert cells[("B", "R")]["sentences"] == 0
    assert cells[("B", "-")]["sentences"] == 0                       # the sentence has a response


def test_links_parsing():
    assert pm.links("N,B") == {"N", "B"}
    assert pm.links("0") == set() and pm.links("") == set() and pm.links(float("nan")) == set()


def test_algorithm_spans_give_the_expected_cell():
    kw = kc.load_list()
    text = "Courchaton était autrefois célèbre pour ses vignes et ses vergers de mirabelliers."
    s = kc.code_sentences(pd.DataFrame({"sentence_id": ["s1"], "text": [text]}), kw, "a_form")
    cells = pm.pid_matrix(s, 1)["cells"]
    assert cells[("N", "R")]["sentences"] == 1
    assert cells[("N", "R")]["response"] == {"célèbre": 1}


@pytest.fixture(scope="module")
def courchaton():
    sentences = cc.load_sentences(cc.ARTICLE, "70178")
    return sentences, pm.reference_spans(cc.load_reference(cc.REFERENCE, sentences))


def test_courchaton_reference_matrix(courchaton):
    sentences, ref = courchaton
    m = pm.pid_matrix(ref, len(sentences))
    core = {(e, r): m["cells"][(e, r)]["sentences"] for e in pm.ENVS for r in pm.RESPONSES}
    assert core.pop(("N", "R")) == 1 and set(core.values()) == {0}  # a single response: célèbre (R>N)
    assert m["cells"][("N", "R")]["environment"] == {"verger": 1, "vignoble": 1}
    assert m["n_sentences"] == 38 and m["spans"] == 50
    rows = pm.matrix_rows(m, article="Courchaton")
    assert len(rows) == 16 and sum(r["sentences"] for r in rows if r["environment"] == "-" == r["response"]) == 18


def test_koinos_share_of_the_reference(courchaton):
    _, ref = courchaton
    share = pm.koinos_share(ref, kc.load_list())
    assert 0 < share < 1


def test_corpus_mode_one_matrix_per_article():
    sentences = pd.DataFrame({"sentence_id": ["a-s0", "a-s1", "b-s0"], "insee": ["1", "1", "2"],
                              "langue": ["fr", "fr", "fr"], "text": ["", "", ""]})
    s = spans(("a-s0", "B", "rue", ""), ("a-s0", "A", "flâner", "B"))
    table = pm.corpus_matrices(s, sentences)
    assert len(table) == 32                                          # 16 cells x 2 articles
    a = table[table["insee"] == "1"].set_index(["environment", "response"])
    assert a.loc[("B", "A"), "sentences"] == 1 and a.loc[("-", "-"), "sentences"] == 1
    b = table[table["insee"] == "2"].set_index(["environment", "response"])
    assert b.loc[("-", "-"), "sentences"] == 1 and b["sentences"].sum() == 1
