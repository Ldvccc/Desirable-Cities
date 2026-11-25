# Keyword lists: what differs between them

Desirable Cities — 25 November 2026

The repository holds three lists, plus the Koinos tags that method A uses as its own list. **None of the lists is
edited after its release:** each new idea becomes a new version, so that every result can be traced back to the
list that produced it. This page explains how they differ and which one to use.

## At a glance

| | Lexicon v0 | Koinos tags | List v3 | List v4 |
|---|---|---|---|---|
| File | `schema/lexicon_v0.yaml` | entries `src: K` of list v3 | `schema/keyword_list_v3.yaml`, `docs/keyword_list_v3.pdf` | `schema/keyword_list_v4.yaml` |
| Date | 1 November 2026 | thesis (Villar 2025, §31.2.3.7) | 14 November 2026 | 24 November 2026 |
| Status | superseded prototype | part of v3 and v4, unchanged | **reference**: the list the human coders use | **proposal**, not validated |
| What is coded | a sentence (categories ticked) | a word (span) | a word (span) | a word (span) |
| Size | 204 concepts, 631 French terms | 158 entries | 341 entries (334 distinct French terms) | 383 entries (376 distinct) |
| French terms per tag | several (synonyms, derived words) | one | one | one |
| Coding rules | coding guide v0.1 (`docs/coding_guide.md`) | none (naive match) | rules for manual coding v2 | rules v2, plus third-person verb forms |
| Used by | `src/classify_keywords.py` (first algorithm A) | method A | human coders, methods A+ and A-form | methods A+ and A-form with `--list` |

Two lists with the same number of entries per section can still give different results: what matters is also how
each entry is **matched** (exact term, plural, forms, exclusions). That second layer is described for each list below.

## Lexicon v0 (prototype, 1 November)

The first attempt, written for **sentence-level** coding with the annotation schema v1
(`schema/annotation_schema_v1.json`, `docs/schema_v1_note.md`). For each sentence, a coder ticked the environments
and responses it mentions, with the words as evidence, plus the public-space types and the register.

- **Structure.** Category → subcategory → concept, each concept with its English thesis term and **several French
  terms**: `{en: windy, fr: [venteux, vent, mistral, tramontane]}`. Each subcategory has a status: `thesis` (list
  from the thesis, French translation ours), `extension` (added by us) or `proposal` (reflections, for which the
  thesis has no list). It also has two facets that later lists dropped: the nine public-space types and the
  register (descriptive, imaginary, spectacle).
- **Size** (counted in the `environments` and `responses` sections):

  | Category | Subcategories | Concepts | French terms | Status |
  |---|---|---|---|---|
  | Natural | 8 | 56 | 156 | 50 thesis, 6 extension |
  | Cultural | 8 | 38 | 128 | 27 thesis, 11 extension |
  | Constructural | 6 | 63 | 186 | 63 thesis |
  | Emotion | 2 | 12 | 45 | 7 thesis, 5 extension |
  | Action | 2 | 26 | 76 | 20 thesis, 6 extension |
  | Reflection | 3 | 9 | 40 | 9 proposal |
  | **Total** | 29 | **204** | **631** | |

- **Matching** (`src/classify_keywords.py`): exact term, case-insensitive, whole word, optional plural; a category is
  ticked when one of its terms appears; PID cells = every environment × every response of the sentence.
- **What replaced it.** On 14 November the team moved to **word-level** coding with a **closed** list (one French
  term per tag) and form-based rules, the scheme described in the paper (§4); `docs/coding_guide.md` is marked
  superseded. 227 of the 334 distinct French terms of list v3 were already in lexicon v0.

## The Koinos tags (method A)

The 158 predefined tags of the Koinos tagging system of the thesis (§31.2.3.7, pp. 534–537), each rendered by
**exactly one French term** (the temperature scale counts as one tag: every value in °C). They are not a separate
file: they are the entries of list v3 with `src: K`, identical in list v4.

| N | C | B | E | A | R | Total |
|---|---|---|---|---|---|---|
| 50 | 29 | 52 | 7 | 20 | 0 | 158 |

Reflections have no tags: Koinos records them as free text. Method A (Koinos tags only) therefore never finds a
reflection. The paper reports results on the Koinos tags apart from the additions, so that the extensions can be
judged on their own.

## List v3 (reference, 14 November)

The list in `docs/keyword_list_v3.pdf`, written by the two coders and supervised by F. Pfaender and J. Villar.
`schema/keyword_list_v3.yaml` is its machine-readable copy. Both coders and both algorithms A+ and A-form use it.

**Composition** (section × source):

| | G names | K Koinos | T Cards | E extensions | P reflection markers | Total |
|---|---|---|---|---|---|---|
| N Natural | 7 | 50 | | 26 | | 83 |
| C Cultural | 5 | 29 | | 27 | | 61 |
| B Constructural | 5 | 52 | 6 | 47 | | 110 |
| E Emotions | 1 | 7 | | 16 | | 24 |
| A Actions | 1 | 20 | | 20 | | 41 |
| R Reflections | 2 | | | | 20 | 22 |
| **Total** | **21** | **158** | **6** | **136** | **20** | **341** |

G = names of the categories and subcategories (rule I2), T = elements of the Emotion-naire Cards (orientation
elements after Lynch, hotel, restaurants, shops). Seven French terms appear twice, because two tags received the
same French word (*rivière*, *cascade*, *passerelle*, *montagne*, *culturel*, *foule*, *calme*): hence 334 distinct
terms. *montagne* is listed in N and in B and is always coded N (rule D2). *calme* is listed in C and in E; rule D1
decides between them from the context.

**Two layers in the YAML file**, kept apart on purpose:

1. **The list**: `tag`, `fr`, `src` and the section. It is exactly the PDF and is never edited.
2. **The encoding of the rules** for method A-form. It does not change the list; it writes down what the rules
   mean for each entry, so that the algorithm applies them the way the coders do:

   | Field | Meaning | Entries |
   |---|---|---|
   | `pos` | noun, adjective, verb, multi-word expression, invariable, °C value | all |
   | `forms` | words built on the same stem (rule I1: *forêt* → *forestier*); proposed by us, to be checked by the coders | 164 |
   | `exclude` | fixed expressions and homonyms (rule I4: *ouvrage d'art*, *bassin houiller*) | 30 |
   | `lemma`, `plural` | singular of a plural entry (*vagues*), irregular plural (*hôpitaux*) | 17, 2 |
   | `conj`, `verb` | irregular conjugated forms; a verb whose forms count (*critiqué*) | 10, 8 |
   | `require` | a determiner before *son* (sound, not the possessive), a reflexive pronoun (*se reposer*), *été* as the season | 10 |
   | `when` | rule D1: the code depends on the context (*calme*, *voitures*, *restaurants*…) | 7 |
   | `drop` | a generated form that is another word (*marché* is not *marcher*) | 5 |
   | `case` | exact case (acronym *VTC*) | 1 |

## List v4 (proposal, 24 November)

Built at the authors' request from what the two pilot articles showed: Courchaton (rev. 234797520) and Lyon
(rev. 241583218). The criteria are written at the top of the YAML file, and every change is logged, with its evidence,
in its `changes` field.

- **Kept:** all Koinos tags, Card elements and category names, except one name (*action*).
- **Removed:** an extension or reflection marker whose matches in the pilot articles are almost never the intended
  sense.
- **Added** (source `L`): a generic word that names an element of the framework, occurs in the pilot articles, is not
  covered by v3 (synonym or more specific word, rule I1) and should be common in commune articles. Nothing specific
  to Lyon (*soie*, *canut*, *traboule*).
- **Re-encoded:** new exclusions and corrected forms for the homonyms seen in the pilot articles.

**Composition:** 383 entries = 341 − 3 removed + 45 added.

| | N | C | B | E | A | R | Total |
|---|---|---|---|---|---|---|---|
| v3 | 83 | 61 | 110 | 24 | 41 | 22 | 341 |
| v4 | 93 | 71 | 133 | 24 | 41 | 21 | 383 |
| difference | +10 | +10 | +23 | 0 | 0 | −1 | +42 |

(A: −1 *action*, +1 *flâner*. R: −2 *projet*, *proposition*, +1 *renommée*.)

**Matching change for every verb.** v4 sets `encoding: {third_person_only: true}`. For regular *-er* verbs, only the
infinitive, the third-person forms and the participles are generated. Encyclopedic text is written in the third person,
and the other persons are often other words: *joues* (cheeks) is not *jouer*, *pensions* is not *penser*.

### Removed (3)

| Word | Code | Source | A-form matches with v3 | Reason |
|---|---|---|---|---|
| action | A | G | Lyon 11 / Courchaton 0 | Financial shares, *action municipale*, *action sociale*: never people acting in a place (rule D4). Rule I2 would need an exception. |
| projet | R | P | Lyon 32 / Courchaton 0 | Urban or institutional projects; never reports what people think of the place (rule D6). |
| proposition | R | P | Lyon 13 / Courchaton 0 | *proposer* means "to offer" (*radios proposant du jazz*, *visites proposées*); never a reflection. |

### Added (45)

| Word | Code | A-form matches with v4 | Reason |
|---|---|---|---|
| fleuve | N | Lyon 10 | Synonym of *rivière* (not coded under rule I1); the main water feature of river towns. |
| rive | N | Lyon 18 | River banks (*rive gauche*, *rive droite*). |
| berge | N | Lyon 10 | River banks, often described as leisure places. |
| confluent | N | Lyon 8 | Meeting of rivers; generic in geography sections. |
| pente | N | Lyon 9 | Relief (slopes of a hill). |
| sommet | N | Lyon 7 | Relief (top of a hill or mountain); *sommet du G7* excluded. |
| précipitations | N | Lyon 2 / Courchaton 3 | Weather; part of the standard climate paragraph of thousands of commune articles, next to *température*. |
| étang | N | Lyon 2 | Water feature, synonym of *lac*. |
| espace vert | N | Lyon 4 | Vegetated open space; Koinos green features. |
| terre arable | N | Courchaton 1 | Farmland; standard land-cover paragraph (Corine Land Cover), next to *prairies* and *forêts*. |
| fête | C | Lyon 17 | Festivity (*fête des Lumières*, *fête patronale*); only *fête foraine* and *salle des fêtes* were in v3. |
| spectacle | C | Lyon 7 | Cultural events. |
| concert | C | Lyon 4 / Courchaton 1 | Cultural events; more specific than *musique*, so not coded in v3 (rule I1). |
| cuisine | C | Lyon 6 | Gastronomy (*cuisine lyonnaise*); forms: *culinaire*. |
| danse | C | Lyon 13 | Dance as an art form (*Maison de la danse*), like *musique*; v3 coded it A as a form of *danser*, against rule D4. |
| héritage | C | Lyon 4 | Synonym of *patrimoine*. |
| médiéval | C | Lyon 5 | History (period). |
| antique | C | Lyon 5 | History (period); forms: *Antiquité*. |
| romain | C | Lyon 22 | History (Roman period); also matches *gallo-romain*. |
| fréquentation | C | Lyon 3 | Crowd density (Koinos *many people*); forms: *fréquenté*. |
| quai | B | Lyon 13 | Open-air public space along rivers (Koinos *promenade*). |
| boulevard | B | Lyon 6 | Major street (Koinos *avenue*, ch. 15 major boulevards). |
| palais | B | Lyon 15 | Building (*palais de justice*, *palais des sports*). |
| opéra | B | Lyon 3 | Cultural building, next to *théâtre*. |
| basilique | B | Lyon 7 | Religious building; more specific than *église*, so not coded in v3. |
| synagogue | B | Lyon 4 | Religious building. |
| mosquée | B | Lyon 5 | Religious building. |
| temple | B | Lyon 4 | Religious building. |
| couvent | B | Lyon 4 | Religious building. |
| monastère | B | Lyon 1 | Religious building. |
| statue | B | Lyon 8 | Visual reference (Koinos *landmark*). |
| façade | B | Lyon 10 | Architecture. |
| édifice | B | Lyon 4 | Synonym of *bâtiment*. |
| tour | B | Lyon 30 (about half are election rounds, excluded) | Landmark (*tour Part-Dieu*, *tour médiévale*). |
| halle | B | Lyon 5 | Market hall (Koinos *food markets*, building). |
| faubourg | B | Lyon 6 | Settlement, next to *quartier* and *bourg*. |
| banlieue | B | Lyon 11 | Settlement. |
| agglomération | B | Lyon 23 | Settlement (urban area), next to *ville*. |
| salle | B | Lyon 14 / Courchaton 1 | Building for events (*salle de concert*, *salle de spectacle*). |
| cité | B | Lyon 23 | The city as a settlement (*la cité*, *cité ouvrière*). |
| aqueduc | B | Lyon 3 | Infrastructure (Roman aqueducts). |
| amphithéâtre | B | Lyon 2 | Building (Roman amphitheatre). |
| parvis | B | Lyon 1 | Open-air public space (ch. 15 public squares). |
| flâner | A | Lyon 1 | Strolling, more specific than *se promener*; forms: *flânerie*. |
| renommée | R | Lyon 4 | Reputation, next to *réputé*. |

### Re-encoded (21)

The list entry stays; only what the algorithm counts as a form of it changes.

| Entry | Seen in the pilot articles | Change |
|---|---|---|
| -er verbs | *joues de porc*, *pensions* | Only third-person forms, infinitive and participles are generated. |
| étoilé | Lyon 4, all Michelin or heraldic stars | Excludes restaurant stars and heraldic stars. |
| fleurs | Lyon 4, *fleurs de lys* | Excludes the heraldic fleur de lys (coat-of-arms sections of most articles). |
| place | Lyon 5 of 62 | Excludes the verb *placer*, seats (*5 438 places assises*) and *place de choix*. |
| naturel | Lyon 1 | Drops *naturellement* ("of course"). |
| source | Lyon 2 | Excludes data sources (*(source infoclimat.fr)*, *les sources et les études*). |
| propre | Lyon 2, Courchaton 2: never "clean" | Excludes "own" after nouns (*industries propres*, *compétences propres*). |
| artistique | Lyon 1 | Excludes *gymnastique* and *patinage artistique*. |
| constructurel | Lyon 1 | Excludes *permis de construire*. |
| bassin | Lyon 1 | Excludes *bassin méditerranéen*. |
| ferme | Lyon 1 | Excludes the verb *fermer* (*la ville ferme ses temples*). |
| aube | Lyon 1 | Excludes *l'aube du XXIe siècle*. |
| inspiration | Lyon 3, Fontainebleau 1 | Drops the verb *inspirer* (*inspiré de*): an influence of style, not an emotion (rule D4). |
| danser | Lyon 13 | Drops the noun *danse* (now a C entry); *danseurs* stays A. |
| travailler | Lyon 2 | Drops *travaux* (building works, not people working). |
| patiner | Lyon 3 | Drops *patinoire* (a building). |
| assister | Lyon 1 | Only *assister à* (to attend); *le maire est assisté* is excluded. |
| conduire | Lyon 1 | Excludes *conduire à* (to lead to). |
| réfléchir | Lyon 1 | Excludes light being reflected. |
| considérer | Lyon 1 | Excludes *si l'on considère*. |
| célèbre | Lyon 2 | Drops *célébrité* (famous people, not the place); *qui célèbre* is the verb *célébrer* (A). |

## What the differences change in the results

Method A-form, rules v2. Courchaton is compared with the human reference (union of coders A and B, coded with list
v3). Lyon has no human coding yet: its precision was estimated on 200 random spans reviewed by Claude, so it is an
order of magnitude, not a reference (`docs/list_versions_comparison.pdf`).

| | List v3 | List v4 |
|---|---|---|
| Courchaton: reference words found | 50 / 50 | 50 / 50 |
| Courchaton: words coded beyond the reference | 0 | 6 (*précipitations* ×3, *terres arables*, *salle*, *concert*: v4 additions, errors by construction) |
| Courchaton: F1 against the union | 1.00 | 0.94 |
| Lyon: spans coded | 2,009 | 2,265 |
| Lyon: estimated precision (95 % CI) | 83 % (76–88) | 92 % (87–95) |
| Lyon: sentences with a PID cell (`docs/pid_matrices.pdf`) | 125 | 74 |

The last line is the clearest effect of v4. The removed entries and the new exclusions were mostly false
**responses** (*projet*, *proposition*, *action*, *danse*), and these false responses created false PID cells.

Method A gives the same result with both lists, since the Koinos tags did not change. A+ goes from 1,868 to 2,214
spans on Lyon, with precision 69 % → 72 %.

## Which list to use

- **List v3** for everything compared with the human coding and reported in the paper. It is the list the coders
  apply.
- **Koinos tags alone** (method A) as the baseline closest to the framework, reported apart from the additions.
- **List v4** only after (1) the coders and J. Villar validate the changes above, and (2) a test on an article that
  was **not** used to build it. Lyon helped to build v4, so its Lyon figures are optimistic. If v4 is adopted, the
  coders' manual must say so, since the human reference would then follow a different list.
- **Lexicon v0**: history only.

## Points to validate (v4)

1. Removing a category name (*action*) contradicts rule I2 (category names are always coded). Should I2 have an
   exception, or should *action* stay and be handled by rule D4?
2. Are the 45 additions acceptable as extensions of the framework? Watch in particular the religious buildings,
   *cité* and *agglomération* (settlement), and *romain* / *médiéval* / *antique* (history as cultural).
3. Is *danse* cultural (an art form like *musique*) rather than an action?
4. Should the human coders also code verbs in the third person only? This rule exists only in the algorithm for now.
