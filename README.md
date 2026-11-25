# Desirable Cities at scale

How French communes present themselves on Wikipedia.

UTSEUS (Shanghai University) EG01 Engineering Project, Autumn 2026.
Supervisor: Fabien Pfaender (UTSEUS / UTC–COSTECH). Industry partner: John Villar (HWCD, R&D).

**Start here:** [docs/project_summary.md](docs/project_summary.md) summarises the whole project (extraction,
coding scheme, lists, algorithms, results, PID matrices); [docs/keyword_lists.md](docs/keyword_lists.md) explains
how the keyword lists differ.

## Repository structure

- `src/`: Python code
- `data/`: corpus (not versioned), sample, pilot articles and references (`data/reference/`)
- `schema/`: keyword lists (v3 reference, v4 proposal), annotation schema and lexicon v0 (prototype)
- `docs/`: summary, lists and coding rules, comparison reports, PID matrices
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
    python src/pid_matrix.py --spans data/processed/spans_a_form.csv --sentences data/processed/sentences_500.parquet
                                                  # one PID matrix per article -> data/processed/pid_matrices_a_form.csv

## Keyword coding

- `docs/keyword_list_v3.pdf` and `schema/keyword_list_v3.yaml`: the 341 keywords (list v3); the YAML also
  encodes, per word, how the rules apply (forms, homonyms, context).
- `docs/rules_manual_coding_v2.pdf` and `docs/rules_manual_coding_v2.md`: the rules for manual coding v2.
- `src/keyword_coder.py`: algorithm A (Koinos tags, naive), A+ (full list, naive) and A-form (list + rules),
  one row per coded word.
- `src/compare_coders.py`: humans vs AI vs algorithms on a pilot article
  (`data/reference/`) -> `docs/courchaton_comparison.pdf` and `.csv`.
- `schema/keyword_list_v4.yaml`: **proposal** of list v4 (383 entries), built from Courchaton and Lyon;
  every change, with its reason and evidence, is in its `changes` field. Not validated yet; list v3 stays
  the reference of the human coding. Lists are never edited after their release: `docs/keyword_lists.md`
  compares lexicon v0, the Koinos tags, v3 and v4.
- `src/compare_list_versions.py`: lists v3 and v4 with the three methods on Courchaton (against the human
  reference) and Lyon -> `docs/list_versions_comparison.pdf` / `.csv`, `docs/lyon_spans.csv`.
- `data/reference/lyon_fr_241583218_review_sample.csv`: 200 Lyon spans reviewed by Claude against the rules
  v2, used only to estimate precision while the human coding of Lyon is not available. Not a human reference.
- `src/pid_matrix.py`: the 3 × 3 PID matrix (environments × responses, counted in sentences, with the keywords
  of each cell). Without arguments it writes `docs/pid_matrices.pdf` / `.csv`: one matrix per method and per
  pilot article (and the Courchaton human reference); with `--spans` and `--sentences`, one matrix per article
  of a coded corpus.
- Earlier prototype, kept for reference: `schema/lexicon_v0.yaml`, `docs/coding_guide.md` and
  `src/classify_keywords.py` (sentence-level labels, schema v1).

Tests: `python -m pytest -q tests`
