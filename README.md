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
    python src/hybrid.py                          # A-form + LLM check of the responses -> data/processed/spans_hybrid.csv
    python src/heritage.py --spans data/processed/spans_hybrid.csv --sentences data/processed/sentences_500.parquet
                                                  # + links inherited from the previous sentence
    python src/pid_matrix.py --spans data/processed/spans_a_form.csv --sentences data/processed/sentences_500.parquet
                                                  # one PID matrix per article -> data/processed/pid_matrices_a_form.csv

`hybrid.py` calls the Claude API (`claude-opus-5-5`): set `ANTHROPIC_API_KEY` in `.env` / the environment, or log
in with `ant auth login`. Its answers are cached in `data/llm/hybrid_answers.jsonl` (versioned, so that a run can be
audited and repeated); `--offline` uses the cache only.

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
- `src/heritage.py` (method **Heritage**): A-form, plus links inherited from the previous sentence when a
  response has no environment in its sentence and the sentence refers back to a place (*y*, *là*, *celui-ci*,
  sentence-initial *Il/Elle*…). Inherited links are flagged.
- `src/hybrid.py` (method **Hybrid**): A-form environments kept; every response candidate (E, A, R) checked by an
  LLM against rules D4 and D6, and linked by it to the environment words of its sentence (D7). The list stays
  closed: the LLM never adds a word.
- `src/compare_methods.py`: A, A+, A-form, Heritage, Hybrid and Hybrid + Heritage on Courchaton, Lyon and
  Fontainebleau (`ARTICLES`) -> `docs/methods_comparison.pdf` / `.csv`, `docs/hybrid_audit_<article>.csv` (every
  LLM decision with its reason), and
  regenerates `docs/pid_matrices`. The current Hybrid figures are a **preview**: no API key was available, so the
  answers in the cache were written by Claude inside a Claude Code session (model id
  `session:claude-opus-5-5`); rerun `python src/compare_methods.py` with a key for the real run.
- `src/algorithms_report.py` -> `docs/algorithms.pdf`: how each algorithm works and where it fails (figures read
  from the comparison reports, so rerun it after `compare_methods.py`).
- Earlier prototype, kept for reference: `schema/lexicon_v0.yaml`, `docs/coding_guide.md` and
  `src/classify_keywords.py` (sentence-level labels, schema v1).

Tests: `python -m pytest -q tests`
