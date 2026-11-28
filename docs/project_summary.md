# Project summary: from the list of communes to the PID matrices

Desirable Cities at scale — UTSEUS EG01, autumn 2026 — state of the repository on 25 November 2026

This page summarises what has been built so far, in the order of the pipeline: extraction of the corpus, coding
scheme, keyword lists, algorithms, results on the two pilot articles, and the PID matrices. Each section points to
the files that hold the details.

## 1. Goal

The Desirable Cities framework (J. Villar, doctoral thesis, 2025) reads urban experience through three
**environments** (N natural, C cultural, B constructural) and three **responses** (E emotions, A actions,
R reflections). Crossing them gives the 3 × 3 matrix of the Cities' PIDs; each crossing is a **PID cell** (e.g.
natural × action). The project applies the framework to the French Wikipedia article of every French commune,
in order to describe how each place is presented.

Questions of the paper (`Desirable_Cities_Utseus_Temporary_Paper`, draft of 17 November):

- **RQ1**: can the categories be turned into a coding scheme that independent human coders apply consistently?
- **RQ2**: how closely do automatic methods (a keyword baseline, LLMs) reproduce the human reference?
- **Working hypothesis**: encyclopedic text foregrounds the cultural and constructural environments and seldom
  reports responses.

## 2. Timeline

| Date | Step | Where |
|---|---|---|
| 24 Oct | Project structure; list of communes from Wikidata, checked against the INSEE register | `src/wikidata_communes.py`, `src/check_cog.py` |
| 26 Oct | Stratified sample of 500 communes; titles of their French and English articles | `src/make_sample.py`, `src/wikipedia_titles.py` |
| 1 Nov | Annotation schema v1 (sentence level), lexicon v0, validator | `schema/`, `src/schema_utils.py`, `docs/schema_v1_note.md` |
| 12 Nov | Article text and sentence splitter (tested on Fontainebleau); first algorithm A (sentence level, lexicon v0); coding guide v0.1 | `src/wikipedia_text.py`, `src/split_sentences.py`, `src/classify_keywords.py` |
| 14 Nov | Keyword list v3 and rules for manual coding v2: coding moves to the word level | `docs/keyword_list_v3.pdf`, `docs/rules_manual_coding_v2.pdf` |
| 17 Nov | Paper, working draft | — |
| 19 Nov | Courchaton coded by two humans and by an AI; list v3 and rules v2 encoded; methods A, A+, A-form; comparison | `src/keyword_coder.py`, `src/compare_coders.py`, `docs/courchaton_comparison.pdf` |
| 24 Nov | Lyon coded by the algorithms; list v4 (proposal); comparison of the list versions | `schema/keyword_list_v4.yaml`, `src/compare_list_versions.py`, `docs/list_versions_comparison.pdf` |
| 25 Nov | PID matrices of the pilot articles; this summary; differences between the lists | `src/pid_matrix.py`, `docs/pid_matrices.pdf`, `docs/keyword_lists.md` |
| 25 Nov | Methods Heritage (inherited links) and Hybrid (LLM check of the responses); comparison of the six methods; third article, Fontainebleau (no human coding) | `src/heritage.py`, `src/hybrid.py`, `src/compare_methods.py`, `docs/methods_comparison.pdf` |

## 3. Extraction: from the list of communes to sentences

Each step is a script in `src/` that writes a versioned table; the formats are fixed by the data contract in
`data/README.md`. Run them in this order from the project root:

| Step | Script | Output | Key facts |
|---|---|---|---|
| 1. Communes | `wikidata_communes.py` | `data/processed/communes.csv` | Wikidata items with an INSEE code (P374), queried department by department (101), with the latest population (P1082) and coordinates. **34,875 communes**, the exact count of the official register on 1 January 2026, after two corrections: Paris (Q90) added by hand, one obsolete item (Les Trois Lacs, 27058) excluded. 7 items have no name and 8 no coordinates. |
| — check | `check_cog.py` | `docs/cog_check_2026-10-24.txt` | Comparison with the INSEE *Code officiel géographique* 2026 (communes only). |
| 2. Sample | `make_sample.py` | `data/sample_500.csv`, `docs/sample_strata.csv` | **500 communes**: 100 per population class (< 500, 500–1,999, 2,000–9,999, 10,000–49,999, ≥ 50,000), fixed seed; Paris, Fontainebleau and Bois-le-Roi are always included. Not representative of France on purpose (97 % of communes are small); built to compare sizes. |
| 3. Titles | `wikipedia_titles.py` | `data/titles_500.csv`, `docs/titles_coverage.csv` | Wikidata sitelinks: all 500 communes have a French and an English article (1,000 articles). |
| 4. Text | `wikipedia_text.py` | `data/processed/corpus_500.parquet` | MediaWiki API, TextExtracts: running text and section titles, without infobox, tables, captions or references. The **revision id and date** of every article are stored. Section titles are mapped to 13 shared types (intro, geography, history, heritage, culture, economy, politics, demography, transport, education, sport, personalities, other); non-content sections (references, see also…) are typed `skip`. |
| 5. Sentences | `split_sentences.py` | `data/processed/sentences_500.parquet` | Rule-based splitter written for French and English (abbreviations such as *av. J.-C.*, initials, quotations). Each sentence gets a stable id `<insee>-<langue>-<revision_id>-s<index>`, the unit of annotation. |

**Status.** The pipeline is tested end to end (unit tests, Fontainebleau, Courchaton, Lyon). The full sample has not
been downloaded into this working copy yet (`data/processed/` has no `corpus_500.parquet`). Steps 4–5 for the 500
communes, then for all communes, come next.

**Revisions.** TextExtracts returns only the current revision of an article. The pilot articles are therefore kept as
raw API answers in `data/reference/` (Courchaton rev. 234797520, Lyon rev. 241583218). Human coders work on a PDF of
the article, which must be printed from the same revision as the text the algorithms read. For Lyon this is not the
case yet: the coders' PDF is rev. 241194072 (9 November), and there were three small edits before rev. 241583218.

## 4. Coding scheme

**Unit.** A **span**: a word or a fixed expression of the running text, from the first line to the "Voir aussi"
heading (no infobox, table, caption or heading). Each span gets one code, N, C, B, E, A or R. Every response span
is **linked** to the environments of its sentence that it relates to (rule D7); a link defines a PID cell.

**Rules for manual coding v2** (`docs/rules_manual_coding_v2.md`). They are deliberately form-based: coders
recognise words rather than interpret meaning.

| Rule | In one line |
|---|---|
| I1 Form | A word counts if it is a form of a list word: plural, feminine, conjugated verb, same-stem word (*forêt* → *forestier*). Synonyms and more specific words do not count. |
| I2 Category names | The names of categories and subcategories are keywords. |
| I3 Span | The shortest expression matching a list word; multi-word entries kept whole. |
| I4 Homonyms | Exclude a different word with the same spelling or a fixed expression (*il a été élu*, *prendre place*). |
| I5 Proper names | A list word that is only part of a name is not coded (*Arbonne-la-Forêt*). |
| I6 Temperatures | Every value in °C is N. |
| I7, I8 | Every tense, negation, every occurrence. |
| I9 Doubt | Apply the form test only. |
| D1 | Words listed twice (*calme*, *voitures*, *restaurants*): the context decides. |
| D2 | *Montagne* and *rivière* are always N. |
| D3 | Listed buildings are B; unlisted buildings are not coded. |
| D4 | E and A only when people really feel or act. |
| D5 | The number of inhabitants is never coded. |
| D6 | R only when the text reports what people think of the place. |
| D7 | Link each response to the environments of its sentence (or "0"). |

The first scheme (schema v1, 1 November) coded whole **sentences**, with public-space types and register
(`schema/annotation_schema_v1.json`, `docs/coding_guide.md`). It is kept for its history; the sentence record format
remains the target output format for all annotators (paper §4.1).

## 5. Keyword lists

The details are in **`docs/keyword_lists.md`**. In short:

- **Lexicon v0** (1 Nov): 204 concepts, 631 French terms, sentence-level prototype. Superseded.
- **Koinos tags**: the 158 tags of the thesis, one French term each. They are the list of method A.
- **List v3** (14 Nov, **reference**): 341 entries = 158 Koinos tags + 6 Card elements + 21 category names + 136
  extensions + 20 reflection markers. The YAML file adds the encoding of the rules for each word.
- **List v4** (24 Nov, **proposal**): 383 entries = v3 − 3 entries that were never right (*action*, *projet*,
  *proposition*) + 45 generic words seen in Courchaton and Lyon + 21 re-encoded entries. To be validated, and tested
  on an article that was not used to build it.

The lists are never edited after their release: a change is a new version.

## 6. Algorithms

All methods produce the same output: one row per span (`sentence_id, start, end, text, code, pid, entry, tag, src,
kind`). They are in `src/keyword_coder.py`:

    python src/keyword_coder.py --sentences <sentences.parquet> --method a|a_plus|a_form [--list <list.yaml>]

| Method | List | Matching | Rules applied | PID links |
|---|---|---|---|---|
| **A** | Koinos tags only (158) | the list term as written, whole word, case-insensitive, optional plural *s*/*x* | none | every environment of the sentence |
| **A+** | full list v3 (341) | same as A | none | same |
| **A-form** | full list v3 + its encoding | all forms of each entry (see below) | I1–I9, D1, D2 | D7: environments of the sentence |

**How A-form works.**

1. **Forms (I1).** For each entry, generate its forms: noun plurals, adjective feminine and plural (*forestier* →
   *forestière, forestiers, forestières*), conjugated forms of *-er* verbs, the same-stem words listed in `forms`.
   Multi-word entries accept plural and feminine endings on their content words (*voies ferrées*).
2. **Candidates.** Search every form in the sentence as a whole word.
3. **Filters.** A capitalised word inside a sentence, or a word hyphenated to one, is part of a proper name (I5).
   The `exclude` patterns of the entry remove fixed expressions and homonyms (I4). Some entries need a determiner
   (*le son*, not the possessive *son*), a reflexive pronoun (*se reposer*), or a check that *été* is not the
   participle of *être*. Sound, smell and feeling words in the sentence decide the code of the D1 words.
4. **Overlaps (I3).** The longest span wins. On a tie, the reading given by the context wins, then the lemma over a
   conjugated form over a derived form, then the order of the list.
5. **Links (D7).** Each E, A or R span is linked to every environment present in its sentence, or "0".

**What the keyword methods do not do.** Rules D4 and D6 (people really feel, act or think) need the meaning of the
sentence. A, A+ and A-form code responses on their form only, so they over-count E, A and R and the PID cells built
on them. Two methods built on A-form address the limits of the matrix:

| Method | What it changes | File |
|---|---|---|
| **Heritage** | A response with no environment in its sentence inherits the environments of the previous sentence (same section) when its sentence refers back to a place: *y* (not *il y a*), *là*, *celui-ci*, *ce lieu*…, or a sentence-initial *Il/Elle/Ils/Elles* that is not impersonal. Inherited links are flagged. | `src/heritage.py` |
| **Hybrid** | Environments kept as A-form codes them. Every sentence with a response candidate is sent to an LLM (Claude Opus 5.5, structured JSON output) with the candidates, the environment words of the sentence, the previous sentence and rules D4, D6, D7. The LLM says whether each candidate is a real response and which environment words it relates to; invalid ones are dropped. It never adds a word, so the list stays closed. Answers are cached with the exact request (`data/llm/hybrid_answers.jsonl`). | `src/hybrid.py` |

`Hybrid + Heritage` applies both. `python src/compare_methods.py` compares the six methods.

**First algorithm A** (`src/classify_keywords.py`, 12 Nov): the same naive idea at the sentence level with lexicon
v0. Kept for reference.

**AI coding.** On Courchaton, the AI (Claude, through the API) received the article, the list and the rules as PDFs,
with the coding decisions in the prompt, and coded the article like a human. The LLM annotators of the paper (three models, fixed versions and
prompts, repeated runs) are still to be done.

## 7. Results on the pilot articles

### Courchaton (38 sentences, human reference)

Two human coders (A: 47 words, about 20 min; B: 48 words, about 25 min); 50 words in their union, 45 in their
consensus. Comparison word by word: a method finds a reference word when one of its spans overlaps it with the same
code (`docs/courchaton_comparison.pdf`).

| Coder | Found (union of 50) | Extra words | F1 vs union | F1 vs consensus |
|---|---|---|---|---|
| AI (Claude) | 50 | 0 | 1.00 | 0.95 |
| A (Koinos tags) | 4 | 6 | 0.13 | 0.15 |
| A+ (full list, naive) | 30 | 9 | 0.67 | 0.69 |
| **A-form** (list v3 + rules) | **50** | **0** | **1.00** | **0.95** |

Courchaton is **development data**: the manual was refined on it and A-form was tuned on it, so its perfect score is
not a test. The naive methods miss feminine and derived forms (*culturelle*, *climatiques*) and code homonyms
(*a été*, *propre*, *bassin*).

### Lyon (1,494 sentences, about 33,000 words, no human reference yet)

| Method | List | Spans | Estimated precision (95 % CI) |
|---|---|---|---|
| A | v3 = v4 | 572 | 60 % (46–74) |
| A+ | v3 | 1,868 | 69 % (61–76) |
| A-form | v3 | 2,009 | 83 % (76–88) |
| A+ | v4 | 2,214 | 72 % (65–79) |
| A-form | v4 | 2,265 | 92 % (87–95) |

Precision was estimated on a random sample of 200 spans reviewed by Claude against the rules
(`data/reference/lyon_fr_241583218_review_sample.csv`). This is **not** a human reference, and recall cannot be
measured without a full coding. Lyon was also used to build list v4, so the v4 figures are optimistic
(`docs/list_versions_comparison.pdf`).

### Heritage and Hybrid (list v3)

`docs/methods_comparison.pdf`. Courchaton: every method built on A-form finds the 50 reference words and the single
reference PID cell (*célèbre* R × N). Lyon and Fontainebleau (rev. 240633341, 391 sentences, 8,300 words, no human
coding; it served earlier as a smoke test of A-form, so it is not entirely unseen):

| Article | Method | Response spans | Sentences with a PID cell | PID cells (9 cells, in sentences) |
|---|---|---|---|---|
| Lyon | A-form | 184 | 125 | 176 |
| Lyon | Heritage | 184 | 127 | 179 |
| Lyon | Hybrid | 61 | 38 | 42 |
| Lyon | Hybrid + Heritage | 61 | 40 | 45 |
| Fontainebleau | A-form | 55 | 41 | 67 |
| Fontainebleau | Heritage | 55 | 41 | 67 |
| Fontainebleau | Hybrid | 38 | 23 | 28 |
| Fontainebleau | Hybrid + Heritage | 38 | 23 | 28 |

On Fontainebleau the Hybrid keeps a much larger share of the candidates (38 of 55, against 61 of 184 in Lyon): the
article reports more real responses (royal hunts and climbing in the forest, visitors to the castle, the
reputation of the forest), and its N × A and N × R cells stay filled (6 sentences each). Heritage adds nothing there:
the only sentence that refers back (*Le comte d'Artois y fit courir…*) follows a sentence without environment word,
and *Cette pratique, devenue emblématique* refers back with a word that is not a marker.

- **Hybrid** keeps 61 of the 184 response candidates (E 4 of 9, A 32 of 82, R 25 of 93). It drops *projet* (32),
  *proposer* (13), *danse* as an art form or a name (13), *action* (10)… and keeps nicknames (*surnommé*: the
  Crayon, the ficelle, the petit Louvre), reputations (*réputé*, *célèbre* about the place) and real visitors and
  dancers. It also narrows the links of 14 kept responses to the environment words they are about. Every
  decision and its reason is in `docs/hybrid_audit_lyon.csv`.
- **Heritage** changes little: 2 sentences of Lyon (the nicknames of the Part-Dieu towers, the visitors of the
  basilica). Most unlinked responses are false ones whose sentence does not refer back to a place.
- **These Hybrid figures are a preview.** No API key was available, so the LLM answers were written by Claude
  (the same model) inside the Claude Code session, following the prompt of `hybrid.py`, and cached under the
  model id `session:claude-opus-5-5`. They must be rerun through the API before being quoted. No human judgment
  of the responses exists yet, so the precision of Hybrid on responses is not measured.

### PID matrices

`python src/compare_methods.py` (or `python src/pid_matrix.py`) → **`docs/pid_matrices.pdf`**: one 3 × 3 matrix per
article and per method (Courchaton: human reference, A, A+, A-form, Heritage, Hybrid, Hybrid + Heritage; Lyon: the
same six methods; list v3), with the keywords found in each cell. The last page compares them all; the CSV also has
list v4. As in the paper (§5.2 c, Figure 2), a cell is counted in **sentences**: a
sentence contains N × A when one of its action spans is linked to a natural span. Two margins complete the matrix:
"no response" (environment only) and "no environment" (response not linked). `docs/pid_matrices.csv` has every cell
with its keywords.

What the matrices show so far:

- **Courchaton, human reference**: 20 of the 38 sentences mention an environment, mostly natural (29 % of the
  sentences; the standard climate paragraph); a single response, *célèbre* (R) linked to *vergers* and *vignes* (N × R).
- **Lyon, A-form v3**: B 43 %, C 20 %, N 10 % of the sentences, which fits the working hypothesis (built and
  cultural first). Responses appear in 11 % of the sentences (6 % with list v4), but in the review sample only 5 of
  21 response spans were valid. With list v4, the sentences with a PID cell drop from 125 to 74; with Hybrid,
  to 38. The PID cells of A, A+ and A-form are an upper bound; those of Hybrid are the closest to the rules, but
  remain unmeasured until the human coding of Lyon is available.

The same script computes one matrix per article for a whole coded corpus:

    python src/pid_matrix.py --spans data/processed/spans_a_form.csv --sentences data/processed/sentences_500.parquet

## 8. Where things are

| Path | Content |
|---|---|
| `src/` | pipeline (steps 1–5), `keyword_coder.py` (A, A+, A-form), `heritage.py`, `hybrid.py`, `pid_matrix.py`, comparison reports |
| `schema/` | `keyword_list_v3.yaml` (reference), `keyword_list_v4.yaml` (proposal), `lexicon_v0.yaml` and `annotation_schema_v1.json` (prototype) |
| `data/README.md` | data contract (formats of the corpus and sentence tables) |
| `data/reference/` | pilot articles (raw API answers: Courchaton, Lyon, Fontainebleau), Courchaton human reference, Lyon review sample |
| `data/llm/` | cached LLM answers of the Hybrid method (request, model, prompt version, answer) |
| `docs/` | lists and rules (PDF and text), reports (`courchaton_comparison`, `list_versions_comparison`, `methods_comparison`, `pid_matrices`, `algorithms`: each algorithm and its limits), `hybrid_audit_lyon.csv`, this summary, `keyword_lists.md` |
| `tests/` | 149 unit tests (no network: the LLM is replaced by a fake judge): `python -m pytest -q tests` |

Reports are regenerated with:

    python src/compare_coders.py          # Courchaton: humans, AI and algorithms
    python src/compare_list_versions.py   # lists v3 and v4 on Courchaton and Lyon
    python src/compare_methods.py         # the six methods + PID matrices (Hybrid needs an API key, or --offline)

## 9. Next steps and open questions

1. **Human coding of Lyon**, the real test of the scheme and of A-form. Align the text first: either the
   algorithms read rev. 241194072 (the coders' PDF), or the coders' spans are mapped onto rev. 241583218.
2. **Agreement between coders** (Krippendorff's α at token, span and PID-cell level, paper §5.2) once the three
   codings exist.
3. **Responses (D4/D6).** The biggest source of error in the algorithms' PID cells. Hybrid addresses it: rerun it
   through the API, then measure it on a human judgment of the 184 response candidates of Lyon (valid or not,
   linked to which environment).
4. **LLM annotators**: models, versions, prompt (the manual and the list, as given to the coders), repeated runs,
   costs.
5. **List v4**: validation by the coders and J. Villar (see `docs/keyword_lists.md`), then a test on a third article
   coded by the humans and never seen while building the list.
6. **Scale**: run steps 4–5 and the retained method on the 500 communes, then on all communes; other language
   editions need their own lists.
