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
| `sections` | list of structs | Structure of the article: list of `{titre, type}`, where `type` is a common section type (history, geography, heritage, ...) shared across languages | `[{"titre": "Histoire", "type": "history"}]` |
| `longueur` | int | Length of `texte` in characters | `48210` |
| `population` | int | Latest population from Wikidata (2023) | `15000` |
| `lat` | float | Latitude, decimal degrees (WGS84) | `48.40` |
| `lon` | float | Longitude, decimal degrees (WGS84) | `2.70` |

The values in the Example column are illustrative: check them against the real data.

## Open decisions (to settle together)
- Unit of `longueur` for languages without spaces (zh): characters.
- Whether to keep `date_extraction` and `revision_id` (reproducibility: which
  version of the article was annotated).
- Whether commune metadata (`population`, `lat`, `lon`) stays in this table or
  moves to a separate `communes` table joined by `insee`.

## Sources and licences
- Commune list: Wikidata (CC0), checked against the INSEE COG 2026.
- Article text: Wikipedia (CC BY-SA). Keep `url` and `titre` to credit the source.
- Regenerate the commune list: `python src/wikidata_communes.py`.
- Reference file: download the INSEE COG communes file into `data/raw/`
  (not versioned).