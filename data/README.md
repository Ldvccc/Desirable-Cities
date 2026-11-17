# Data contract

This file defines the corpus format shared by both students. Any change must be
discussed and approved by both, then reflected here.

## Scope
- Pilot corpus (milestone M1): 500 communes, languages **fr** and **en**.
- Full corpus (milestone M2): all 34,875 communes (reference: INSEE COG 2026),
  at least 4 languages.
- Other languages (de, es, it, zh) can be added later: a new value in `langue`,
  no change of format.

## Rules
- **One row per (`insee`, `langue`) pair.** A commune with articles in fr and en
  has two rows. The pair is unique (no duplicates).
- **`insee` is the common key** of every table in the project (corpus,
  annotations, map). Always stored as **text**, never as a number
  (`01049` must keep its leading zero; Corsica uses `2A` and `2B`).
- Format: **Parquet**. Encoding: **UTF-8**.
- A commune with no article in a language has **no row** for that language
  (the coverage statistics are computed from the missing pairs).
- Empty or very short articles are kept (with a small `longueur`), not deleted.
- Unknown values are left empty (null), never invented.

## Columns

| Column | Type | Description | Example |
|---|---|---|---|
| `insee` | string | INSEE code of the commune (COG 2026) | `77186` |
| `qid` | string | Wikidata item ID | `Q90` |
| `langue` | string | Wikipedia language edition code | `fr`, `en` |
| `titre` | string | Title of the article in that language | `Fontainebleau` |
| `url` | string | Full URL of the article | `https://fr.wikipedia.org/wiki/Fontainebleau` |
| `texte` | string | Article content, plain text (no wiki markup, no references); section titles are kept | |
| `sections` | list of structs | Structure of the article: list of `{titre, niveau, type}`. `niveau` is the heading level (2 = `== Title ==`; the introduction is level 1 with an empty title). `type` is a common section type shared across languages: intro, geography, history, heritage, culture, economy, politics, demography, transport, education, sport, personalities, other, or `skip` for sections that are not content (references, external links, see also) | `[{"titre": "Histoire", "niveau": 2, "type": "history"}]` |
| `longueur` | int | Length of `texte` in characters | `48210` |
| `population` | int | Latest population from Wikidata (2023) | `15000` |
| `lat` | float | Latitude, decimal degrees (WGS84) | `48.40` |
| `lon` | float | Longitude, decimal degrees (WGS84) | `2.70` |
| `revision_id` | int | Wikipedia revision of the article that was downloaded | `219876543` |
| `revision_date` | string | Date of that revision (ISO 8601, UTC) | `2026-10-30T10:00:00Z` |
| `date_extraction` | string | Day the article was downloaded | `2026-11-10` |

The values in the Example column are illustrative: check them against the real data.

## Open decisions (to settle together)
- Unit of `longueur` for languages without spaces (zh): characters.
- `date_extraction`, `revision_id` and `revision_date` were added on 2026-11-10
  (Ivann): `revision_id` is part of the sentence identifier of the annotation
  schema. To confirm together.
- Section types: "Urbanisme" and "Toponymie" (standard sections of French
  commune articles) have no type of their own and fall into `other`. Add
  `urbanism` / `toponymy` to the list (and to the annotation schema)?
- Whether commune metadata (`population`, `lat`, `lon`) stays in this table or
  moves to a separate `communes` table joined by `insee`.

## Text cleaning
- Source: MediaWiki API, TextExtracts (`prop=extracts`, `explaintext`): no wiki
  markup, references, tables or infobox.
- Typographic spaces (non-breaking, thin) become plain spaces, repeated spaces
  and blank lines are collapsed. Nothing else is changed.
- Section titles stay in `texte` as `== Title ==` lines.

## Sentences table
Built by `src/split_sentences.py` from the corpus; file
`data/processed/sentences_500.parquet`, one row per sentence.

| Column | Type | Description | Example |
|---|---|---|---|
| `sentence_id` | string | `<insee>-<langue>-<revision_id>-s<index>`, same format as in `schema/annotation_schema_v1.json` | `77186-fr-219876543-s12` |
| `insee`, `langue`, `revision_id` | | Same as in the corpus | |
| `index` | int | Position of the sentence in the article, 0-based | `12` |
| `section_titre` | string | Title of the section (empty for the introduction) | `Histoire` |
| `section_type` | string | Common section type (never `skip`: those sections are left out) | `history` |
| `text` | string | The sentence | |
| `n_mots` | int | Number of words | `18` |

Headings are not sentences. A list item without final full stop is one
sentence. The splitting rules are described at the top of
`src/split_sentences.py`.

## Sources and licences
- Commune list: Wikidata (CC0), checked against the INSEE COG 2026.
- Article text: Wikipedia (CC BY-SA). Keep `url` and `titre` to credit the source.
- Regenerate the commune list: `python src/wikidata_communes.py`.
- Rebuild the corpus and the sentences: `python src/wikipedia_text.py`, then
  `python src/split_sentences.py`.
- Reference file: download the INSEE COG communes file into `data/raw/`
  (not versioned).