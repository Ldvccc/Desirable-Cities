"""Tests of keyword list v3 and of the span coder (algorithms A, A+, A-form).

Most examples are the examples of docs/rules_manual_coding_v2.md."""
from collections import Counter

import pytest

import compare_coders as cc
import keyword_coder as kc


@pytest.fixture(scope="module")
def kw():
    return kc.load_list()


@pytest.fixture(scope="module")
def form(kw):
    return kc.build_matchers(kw, "a_form")


def spans(text, matchers, method="a_form"):
    return [(s["text"], s["code"]) for s in kc.code_sentence(text, matchers, method)]


def codes(text, matchers):
    return [c for _, c in spans(text, matchers)]


# --- the list --------------------------------------------------------------------

def test_list_counts_match_the_paper(kw):
    entries = list(kc.iter_entries(kw))
    assert len(entries) == 341
    by_section = Counter(e["section"] for e in entries)
    assert by_section == {"N": 83, "C": 61, "B": 110, "E": 24, "A": 41, "R": 22}
    by_src = Counter(e["src"] for e in entries)
    assert by_src == {"G": 21, "K": 158, "T": 6, "E": 136, "P": 20}


def test_every_entry_compiles(kw):
    for method in kc.METHODS:
        assert kc.build_matchers(kw, method)


def test_montagne_is_always_natural(kw):
    assert {e["code"] for e in kc.iter_entries(kw) if e["fr"] == "montagne"} == {"N"}


def test_inflections():
    assert kc.inflect_adj("forestier") >= {"forestière", "forestiers", "forestières"}
    assert kc.inflect_adj("végétal") >= {"végétale", "végétaux"}
    assert kc.inflect_adj("religieux") >= {"religieuse", "religieuses"}
    assert kc.inflect_adj("repos") == {"repos"}                  # not "repose"
    assert kc.inflect_noun("château") == {"château", "châteaux"}
    assert {"marchaient", "marché", "mangeait"} <= kc.conjugate_er("marcher") | kc.conjugate_er("manger")


# --- identification rules -------------------------------------------------------------

def test_i1_forms_count(form):
    for text, code in [("Les forêts domaniales", "N"), ("un chemin forestier", "N"), ("une végétation herbacée", "N"),
                       ("hors unité urbaine", "C"), ("des zones urbanisées", "C"), ("les églises romanes", "B")]:
        assert code in codes(text, form), text
    assert ("marchaient", "A") in spans("Les habitants marchaient le long du canal.", form)


def test_i1_synonyms_and_specific_words_do_not_count(form):
    assert spans("un petit bois", form) == []
    assert spans("le fleuve", form) == []
    assert spans("un vieux chêne", form) == []
    assert spans("la basilique", form) == []
    assert ("arbustive", "N") not in spans("une végétation arbustive", form)


def test_i2_category_names(form):
    assert spans("la région culturelle", form) == [("culturelle", "C")]
    assert ("naturels", "N") in spans("milieux semi-naturels", form)


def test_i3_longest_expression(form):
    assert spans("une voie ferrée", form) == [("voie ferrée", "B")]
    assert spans("le monument aux morts", form) == [("monument aux morts", "B")]
    assert spans("la forêt de Fontainebleau", form) == [("forêt", "N")]


def test_i4_homonyms_and_fixed_expressions(form):
    assert spans("Il a été élu maire.", form) == []
    assert ("été", "N") not in spans("Le bâtiment a quant à lui d'abord été une ferme.", form)
    assert ("été", "N") in spans("un climat tempéré à été frais", form)
    assert ("été", "N") in spans("Il y passait l'été.", form)
    for text in ["prendre place", "la liste se place en tête", "une fiscalité propre", "à 8 km à vol d'oiseau",
                 "le bassin houiller", "cultures permanentes (4,8 %)", "une action en justice", "un ouvrage d'art"]:
        assert spans(text, form) == [], text
    assert spans("le climat de montagne", form) == [("climat", "N"), ("montagne", "N")]


def test_i4_possessive_son_is_not_a_sound(form):
    assert spans("son maire", form) == []
    assert ("son", "C") in spans("le son des cloches", form)


def test_i4_reflexive_verbs(form):
    assert spans("Le territoire repose sur le bassin houiller.", form) == []
    assert ("reposer", "A") in spans("On vient s'y reposer.", form)


def test_i5_proper_names(form):
    assert spans("Arbonne-la-Forêt", form) == []
    assert spans("le lycée du Parc", form) == [("lycée", "B")]
    assert spans("Elle devient Belles-Fontaines.", form) == []
    assert spans("rue de la Forêt", form) == [("rue", "B")]
    assert spans("selon Météo-France", form) == []
    assert spans("Forêts et prairies couvrent la commune.", form)[0] == ("Forêts", "N")   # sentence start


def test_i6_temperatures(form):
    text = "La température moyenne est de 9,9 °C ; maximale 40,2 °C, minimale −17 °C."
    assert spans(text, form) == [("température", "N"), ("9,9 °C", "N"), ("40,2 °C", "N"), ("−17 °C", "N")]


def test_i8_every_occurrence(form):
    assert codes("le climat, un climat de type climat de montagne", form) == ["N", "N", "N", "N"]


# --- category rules ---------------------------------------------------------------------

def test_d1_context(form):
    assert spans("le bruit des voitures", form)[-1] == ("voitures", "C")
    assert spans("les voitures stationnent", form) == [("voitures", "B")]
    assert spans("un village calme", form) == [("village", "B"), ("calme", "C")]


def test_d4_documents_are_not_actions(form):
    assert spans("les photos aériennes de l'IGN", form) == []


def test_d7_pid_link(kw, form):
    out = kc.code_sentence("Courchaton était autrefois célèbre pour ses vignes et ses vergers de mirabelliers.",
                           form, "a_form")
    assert [(s["text"], s["code"], s["pid"]) for s in out] == [
        ("célèbre", "R", "N"), ("vignes", "N", ""), ("vergers", "N", "")]
    assert kc.code_sentence("Il est célèbre.", form, "a_form")[0]["pid"] == "0"


# --- naive baselines ---------------------------------------------------------------------

def test_naive_methods_keep_their_known_errors(kw):
    plus = kc.build_matchers(kw, "a_plus")
    assert ("été", "N") in spans("Il a été élu.", plus, "a_plus")             # homonym coded
    assert spans("la région culturelle", plus, "a_plus") == []                 # feminine missed
    koinos = kc.build_matchers(kw, "a")
    assert spans("une église", koinos, "a") == []                              # extension, not a Koinos tag


# --- Courchaton comparison -------------------------------------------------------------

def test_courchaton_reference_is_located_and_counted():
    cmp = cc.compare(cc.ARTICLE, cc.REFERENCE)
    ref = cmp["ref"]
    assert len(ref) == 50
    assert (ref["human_a"].sum(), ref["human_b"].sum(), ref["ai"].sum()) == (47, 48, 50)
    union = next(a for a in cmp["agreement"] if a["reference"] == "Union (A or B)" and a["coder"] == "A-form")
    assert union["R"] >= 0.9                                                   # regression guard (dev article)
