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

Tests: `python -m pytest -q tests`
