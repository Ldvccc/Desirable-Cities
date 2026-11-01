# Annotation schema v1 and lexicon v0: note for review

Ivann Vasic, Ludovic Blondeau · supervised by Fabien Pfaender and John Villar · 1 November 2026

We classify each **sentence** of a commune's Wikipedia article against the Desirable Cities framework. This note explains the choices behind the schema and lists the points we would like John Villar to validate before milestone M1 (6 November).

## What a sentence receives

| Field | Values | Source in the thesis |
|---|---|---|
| `environments` | natural, cultural, constructural (several allowed), each with the exact words that justify it | Magnaghi triad, Table 01 p. 14 |
| `responses` | emotion, action, reflection (several allowed, or none) | Peirce triad, Table 01 p. 14 |
| `pid_cells` | environment × response pairs that the sentence links together | Cities' PIDs, §16.4 p. 270 |
| `tags` | Koinos-style tags, e.g. `natural.water_features.river` | Koinos tagging system, §31.2.3.7 pp. 533-537 |
| `public_space_types` | the nine open-air types | §15.4 p. 255 |
| `register` | descriptive, imaginary, spectacle | Debord and Silva, §16.2-16.3 pp. 267-270 |
| `uncertain` | true / false | best practice for LLM annotation (Törnberg 2024) |

Files: `schema/annotation_schema_v1.json` (format), `schema/lexicon_v0.yaml` (keywords), `schema/examples/examples_fr.json` (five annotated sentences), `src/schema_utils.py` (validator).

## Where the keywords come from

- **Thesis lists** (English terms kept verbatim, French translations ours): the Terms-naire Tray and Koinos tags for natural, cultural, constructural, emotions and actions; the nine public-space types, transport modes and activities of ch. 15; the orientation elements and building functions of the Emotion-naire Cards. 162 terms.
- **Extensions** (to validate): Wikipedia articles are dominated by geography, history and heritage, which the Koinos tags do not cover. We added relief and climate, heritage and history, festivals, gastronomy, identity, negative emotions and a few leisure actions. 33 terms.
- **Proposal for reflections**: 9 groups of markers, since the thesis has no list (see question 1).

## Coding rules we propose

1. A building or a street is **constructural**; its history, heritage status or meaning is **cultural**.
2. A response is coded only when the sentence reports what people feel, do or think about the place (e.g. "a popular walking spot"); a sentence that only describes what is there gets no response.
3. A PID cell is coded only when the sentence links the response to that environment.

## Questions for John Villar

1. **Reflections.** The Terms-naire Tray omits ideas (p. 380) and Koinos uses free text (p. 537). We propose markers of meaning (symbol of, evokes, nickname, reputed for) derived from how P91 expressed reflections (pp. 457-460). Is a nickname or a reputation a valid reflection?
2. **Public spaces.** Chapter 15 gives 9 types, Koinos gives 18. We use the 9 as the main field and map the 18 Koinos types onto them. Do you agree with this mapping?
3. **Emotions.** The 7 Koinos emotions are all positive, and the thesis notes an over-positivity bias of the cards. May we add negative emotions (boredom, stress, fear)?
4. **Cultural extensions.** May we count heritage, history, festivals, gastronomy and identity as cultural, as the subject suggests?
5. **"Thinking"** appears as an action in Koinos. Should it stay an action or move to reflections?
6. **Register.** Is a large branded festival "spectacle" or "imaginary"? Our fifth example is marked uncertain for this reason.
