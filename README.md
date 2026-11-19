# Desirable Cities at scale

How French communes present themselves on Wikipedia.

UTSEUS (Shanghai University) EG01 Engineering Project, Autumn 2026.
Supervisor: Fabien Pfaender (UTSEUS / UTC–COSTECH). Industry partner: John Villar (HWCD, R&D).

## Repository structure

- `src/`: Python code
- `data/`: corpus (not versioned)
- `schema/`: annotation schema (JSON Schema), lexicon of keywords per category, annotated examples
- `docs/`: project charter, reading notes, draft vocabulary
- `tests/`: unit tests

## Installation

    pip install -r requirements.txt
    cp .env.example .env   # then fill in your API keys

## Pipeline

Run from the project root, in this order:

    python src/wikidata_communes.py   # list of communes from Wikidata
    python src/make_sample.py         # stratified sample of 500 communes
    python src/wikipedia_titles.py    # article titles (fr, en)
    python src/wikipedia_text.py      # article text -> data/processed/corpus_500.parquet
    python src/split_sentences.py     # sentences    -> data/processed/sentences_500.parquet
    python src/keyword_coder.py --method a_form   # keyword spans -> data/processed/spans_a_form.csv

## Keyword coding

- `docs/keyword_list_v3.pdf` and `schema/keyword_list_v3.yaml`: the 341 keywords (list v3); the YAML also
  encodes, per word, how the rules apply (forms, homonyms, context).
- `docs/rules_manual_coding_v2.pdf` and `docs/rules_manual_coding_v2.md`: the rules for manual coding v2.
- `src/keyword_coder.py`: algorithm A (Koinos tags, naive), A+ (full list, naive) and A-form (list + rules),
  one row per coded word.
- `src/compare_coders.py`: humans vs AI vs algorithms on a pilot article
  (`data/reference/`) -> `docs/courchaton_comparison.pdf` and `.csv`.
- Earlier prototype, kept for reference: `schema/lexicon_v0.yaml`, `docs/coding_guide.md` and
  `src/classify_keywords.py` (sentence-level labels, schema v1).

Tests: `python -m pytest -q tests`
