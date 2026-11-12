# Coding guide v0.1

Ivann Vasic, Ludovic Blondeau · 12 November 2026 · goes with `schema/annotation_schema_v1.json` and `schema/lexicon_v0.yaml`

This guide tells a human coder (and later the LLM prompt) how to annotate one sentence. Two coders who follow it should give the same answer. When they do not, the rule that was missing is added at the end (section 7) and the version number goes up.

## 1. The unit

- Code **one sentence at a time**, from `data/processed/sentences_*.parquet`.
- Read the section title and the previous sentence only to resolve "it", "elle", "cette forêt". Never code what the context says and the sentence does not.
- Code what the sentence **says**, not what you know about the place.
- Tense does not matter: a past action ("les rois y chassaient") is coded like a present one.

## 2. The procedure, in this order

1. **Environments.** Which parts of the place does the sentence mention? Tick natural, cultural, constructural (zero, one or several). Copy the words that justify each one as `evidence`.
2. **Responses.** Does the sentence report what people **feel, do or think** about the place? Tick emotion, action, reflection (zero, one or several), with evidence. Most sentences have none: that is expected (it is the hypothesis we test).
3. **PID cells.** For each response, which environment is it about? One cell per pair that the sentence links. A response with no environment gives no cell.
4. **Public-space types.** Tick the nine types of ch. 15 only when the sentence names one (§4 below).
5. **Register.** Descriptive by default; imaginary or spectacle only when §5 applies.
6. **Uncertain.** Tick it and write a `comment` when you hesitate between two codes. Do not guess silently.

## 3. Categories

| Category | Code it when the sentence mentions… | Do not code it for… |
|---|---|---|
| **Natural** | relief, rocks, water, climate, weather, vegetation, forest, fauna, ecosystems | a park or garden as a designed space (→ constructural); a place name that only contains a natural word ("Arbonne-la-Forêt") |
| **Cultural** | history, heritage status, events, festivals, traditions, legends, gastronomy, identity, inhabitants and their life, crowds and atmosphere | a person's biography with no link to the place (personalities lists); election results and statistics |
| **Constructural** | buildings, streets, squares, parks, gardens, transport, infrastructure, the built-up area, its form and functions | a building only cited as a date or an owner, with nothing about it as a built object |
| **Emotion** | a feeling attached to the place: calm, pleasure, nostalgia, emotion, boredom, fear | an adjective of the article itself ("magnifique", "pittoresque"): see rule R4 |
| **Action** | something people do or did there: walk, climb, visit, hunt, gather, swim, work | the action of the authorities that built or managed the place ("la ville a construit…") |
| **Reflection** | a meaning, judgement, reputation, nickname or debate attributed to people: réputé, célèbre, renommé, reconnu, surnommé, considéré comme, critiqué, symbole de | a fact presented as a fact ("le second plus grand château de France") |

The lexicon gives keywords for each category. It helps; it does not decide. A keyword in the sentence is neither necessary nor sufficient.

## 4. Rules for the hard cases

- **R1 Building vs heritage.** The building itself is constructural. Its history, its listing (monument historique, UNESCO) or the events that took place in it are cultural. A sentence often has both.
- **R2 Forest vs park.** A forest, a wood or a natural area is natural. A park or garden is constructural (public-space type), and also natural only if the sentence describes its vegetation or water.
- **R3 Who responds.** Any people count: residents, visitors, "les Parisiens", climbers, kings, "the public". Visitor numbers count as an action ("13 millions de visiteurs" → action).
- **R4 Evaluative words.** Code a reflection only when a judgement is **attributed to people** (réputé, célèbre, reconnu, surnommé, critiqué, considéré comme). A bare adjective written by the article (beau, remarquable, magnifique) gives no response; tick `uncertain` if it carries the whole sentence.
- **R5 Legends and etymologies.** A legend is cultural, register imaginary. It is a reflection only if the sentence reports that people interpret or believe it ("selon la tradition populaire…").
- **R6 Thinking.** Meditating or contemplating as an activity is an action. A meaning, an opinion or a debate is a reflection.
- **R7 Lists.** A list item ("la RD 409, en direction de…", "Université Paris-Cité ;") is coded like any sentence; usually one environment, no response.
- **R8 Out of scope.** Politics, elections, demography figures, school lists and personalities with no place element get empty arrays. Do not force a category.

## 5. Public-space types and register

**Public-space types** (ch. 15.4, p. 255): `sightseeing_site`, `public_square`, `major_boulevard`, `small_street`, `commercial_open_air`, `popup_street_market`, `metropolitan_park`, `small_garden`, `promenade`. Tick one only when the sentence names it ("la place d'Armes" → public_square). A forest is not a public-space type.

**Register:**
- `descriptive`: the default, a neutral statement.
- `imaginary` (Silva): legend, nickname, collective memory, popular tradition.
- `spectacle` (Debord): branding, labels, rankings, promotional figures, events staged to attract visitors.
- `uncertain`: both apply; explain in `comment`.

## 6. Worked examples (Fontainebleau)

| # | Sentence (shortened) | Environments | Responses | PID cells | Register |
|---|---|---|---|---|---|
| 1 | Cette forêt est pour les Parisiens un lieu de promenade mais son relief très accidenté et ses nombreux rochers […] en font aussi un lieu réputé pour la pratique sportive de l'escalade. | natural ("Cette forêt", "son relief très accidenté et ses nombreux rochers") | action ("lieu de promenade", "la pratique sportive de l'escalade"), reflection ("un lieu réputé") | natural × action, natural × reflection | descriptive |
| 2 | La ville stricto sensu […] s'étend sur 232 hectares. | constructural ("La ville stricto sensu") | none | none | descriptive |
| 3 | Le 20 avril 1814, Napoléon […] fait ses adieux à sa garde […] dans la cour du Cheval blanc […] : le moment fut, selon les témoins, très émouvant. | cultural ("fait ses adieux à sa garde"), constructural ("la cour du Cheval blanc") | emotion ("très émouvant") | cultural × emotion | descriptive |
| 4 | La multiplicité de ces installations et événements vaut par ailleurs à la ville le surnom de « capitale du cheval ». | cultural ("événements"), constructural ("installations") | reflection ("le surnom de « capitale du cheval »") | cultural × reflection, constructural × reflection | imaginary |
| 5 | Cette légende est une alternative à l'autre étymologie fantaisiste du nom qui viendrait de fontaine belle eau. | cultural ("Cette légende") | none (R5) | none | imaginary |
| 6 | Fontainebleau est une ville relativement touristique — en 2011, 450 000 personnes ont visité le château et environ 13 millions la forêt […] | constructural ("le château"), natural ("la forêt") | action ("ont visité") | constructural × action, natural × action | descriptive |
| 7 | Les nombreuses plantations de résineux […] sont critiquées par certains qui estiment que cela a mis à mal la cohérence de son écosystème […] | natural ("plantations de résineux", "son écosystème") | reflection ("sont critiquées par certains qui estiment") | natural × reflection | descriptive |
| 8 | The forest is also well regarded for bouldering and is particularly popular among climbers […] | natural ("The forest") | action ("bouldering"), reflection ("well regarded") | natural × action, natural × reflection | descriptive |
| 9 | Fontainebleau abrite un très célèbre château royal, le second plus grand château de France derrière celui de Versailles. | constructural ("château royal") | reflection ("très célèbre") | constructural × reflection | descriptive |
| 10 | Les scrutins européens voient également la droite arriver en tête à Fontainebleau. | none (R8) | none | none | descriptive |

Example 9: "le second plus grand" is a fact, so it gives no reflection; "très célèbre" is a reputation, so it gives one (R4).

## 7. Working method and decisions log

- **Double coding.** Both coders code the same sentences for Bois-le-Roi (whole article) and the first 50 sentences of each other pilot article. Agreement (Krippendorff's α) is computed on these sentences; the rest is split between the two coders.
- **Disagreements.** After each batch, compare, agree on the right code, and write the new rule below if the guide did not cover the case. Do not change the codes of the double-coded sentences used for α.
- **Questions for John Villar** go into `docs/schema_v1_note.md`.

| Version | Date | Decision |
|---|---|---|
| 0.1 | 2026-11-12 | First version: rules R1-R8, examples from Fontainebleau. |
