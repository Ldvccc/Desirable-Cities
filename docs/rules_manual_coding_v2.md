# Rules for manual coding (v2)

Desirable Cities — Ivann Vasic, Ludovic Blondeau — 14 November 2026

Text version of [rules_manual_coding_v2.pdf](rules_manual_coding_v2.pdf). Goes with
[keyword_list_v3.pdf](keyword_list_v3.pdf) (machine-readable version:
[schema/keyword_list_v3.yaml](../schema/keyword_list_v3.yaml)). Supersedes
[coding_guide.md](coding_guide.md) (v0.1, sentence-level coding with lexicon v0).

The reference is the document **Desirable Cities: keyword list v3**. It gives one French word for each Koinos tag
of the thesis, extended with words for buildings, relief, history and heritage, negative emotions and reflections,
and the names of the categories and subcategories. **Only words from that list are coded.** Do not translate the
English Koinos tags yourself, and do not add words that are not in the list.

**Codes:** N natural, C cultural, B constructural (built), E emotions, A actions, R reflections.

## 0. Which part of the article to code

Only the running text of the article is coded, so that the human coding matches exactly the text the models will see.

**Start and end.**
- Start: the first line of the article text, just below the title.
- End: stop at the "Voir aussi" (See also) heading. Nothing from that heading onwards is coded.

**Code.**
- The running text of every section above "Voir aussi": the paragraphs.
- List items in the text.

**Never code.**
- The information box at the top right of the article (photo, map, "Administration", "Démographie", "Géographie",
  "Élections", "Localisation"). Skip the whole box, even when it continues on the next page.
- Images and everything attached to them: captions, gallery titles, text inside images, maps and charts.
- Tables and boxes: the "Communes limitrophes" compass box, the table of mayors, the population table and its notes,
  the histogram.
- Section and sub-section headings ("Géographie", "Climat", "Lieux et monuments").
- Reference marks: superscript numbers ("¹⁷"), "Note 1", "Carte 1", "[modifier]".

## 1. Identification rules

**I1. Form.** A word counts only if it is a form of a word in the list: plural, feminine, conjugated verb, or a word
built on the same French stem.
- Counts: *forêt → forêts, forestier*; *herbe → herbacée*; *urbain → urbaine, urbanisé*; *marcher → marchaient*;
  *église → églises*.
- Does not count:
  - synonyms: *bois* is not *forêt*, *fleuve* is not *rivière*;
  - more specific words: *concert* is not *musique*, *chêne* is not *arbres*, *basilique* is not *église*;
  - words that only share a Latin origin: *arbustive* is not *arbres*.

**I2. Category names.** The names of the categories and subcategories are keywords. They are in the list (source G)
and are coded in their own category: *naturel* N, *saison* N, *température* N, *culturel* C, *foule* C, *ambiance* C,
*transport* B, *infrastructure* B, *émotion* E, *action* A, *réflexion* R. "La région *culturelle*" → C;
"milieux semi-*naturels*" → N.

**I3. Span.** Highlight the shortest expression that matches a list word: "*forêt*", not "*la forêt de
Fontainebleau*". Keep the multi-word entries of the list whole: "*voie ferrée*", "*piste cyclable*", "*fête foraine*",
"*rue piétonne*", "*monument aux morts*", "*salle des fêtes*".

**I4. Homonyms.** Exclude a word only when it is a different word with the same spelling, or part of a fixed
expression: "il a *été* élu" (verb, not the season), "prendre *place*", "fiscalité *propre*", "à vol d'*oiseau*",
"*bassin* houiller", "*cultures* permanentes" (crops), "une *action* en justice". If it is the list word used in a
technical or descriptive sense, code it: "climat de *montagne*" → N; "unité *urbaine*", "zones *urbanisées*" → C.

**I5. Proper names.** Do not code a list word that is only part of the name of a commune, street, institution or
person: "Arbonne-la-Forêt", "lycée du Parc", "Belles-Fontaines". In "*rue* de la Forêt", only "rue" counts. Code it
when the common noun names the real thing: "la *forêt* de Fontainebleau" → forêt.

**I6. Temperatures.** Every value in degrees Celsius is coded N: "9,9 °C", "40,2 °C", "−17 °C". This includes values
outside −10 to 45 °C, negative values and thermal amplitudes. The word "*température*" is also coded N (I2).

**I7. Tense and negation.** Past, future and negation count: "les rois s'y *promenaient*", "il n'y a plus de
*tramway*", "hors unité *urbaine*".

**I8. Repetitions.** Code every occurrence, even several times in the same sentence.

**I9. When in doubt.** Apply only the form test: if the word is a form of a list word (I1) and is not a homonym (I4),
code it. Do not judge whether the meaning is close enough.

## 2. Rules for choosing the category

**D1. Word listed in two categories.** Some list words appear in two places. Choose from the context:
- *calme*: it describes a place or a noise → C (sounds); people feel it → E.
- *voitures, vélos, trains*: the noise they make → C (sounds); the means of transport → B.
- *restaurants, bars, marchés*: a smell → C (smells); the place itself → B.

**D2. Mountain and river.** *Montagne* and *rivière* are always N, even though Koinos also lists them in other
subcategories.

**D3. Buildings.** Buildings in the list are coded B: *église, mairie, école, château, fontaine, lavoir, usine,
maison*, etc. A building that is not in the list is not coded (*gendarmerie, caserne, pharmacie*).

**D4. Who feels or acts.** An emotion (E) or an action (A) is coded only when people experience it, whoever they are:
residents, visitors, kings. An adjective that the article uses about the place ("magnifique") is not an emotion.
A document is not an action: "photos aériennes" is not "photographier".

**D5. Population.** The number of inhabitants of the commune ("445 habitants") is never coded.

**D6. Reflections (R).** The words of the reflection part of the list are coded R (*penser, réputé, célèbre, surnom,
symbole, critique, débat, projet*…), in any form (I1), when the text reports what people think of the place. A fact
stated as a fact is not a reflection.

**D7. PID cells.** For each E, A or R, note which environments it relates to **in the same sentence**: the action
takes place in that element, the emotion is caused by it, or the reflection is about it. If the sentence has no
environment, note "0".

## 3. How to code and what to hand back

1. **Work alone.** Do not discuss the coding with the other coders before everyone has finished, and do not use any
   AI tool.
2. **Time yourself.** Write down the start and end time of each session, without breaks.
3. **Read in order**, sentence by sentence, from the start to the end defined in section 0.
4. **Highlight** each occurrence of a list word in the PDF, and write its code in the comment of the highlight:
   N, C, B, E, A or R.
5. **For E, A and R**, add the environments of the PID cell after ">": "A>N" (action linked to a natural element),
   "R>B,C", "E>0".
6. **When unsure**, highlight anyway and add "?" to the comment ("N?"). Do not leave a doubtful word out.
7. **Hand back** the annotated PDF and your session times. The totals per code are computed from your comments;
   you do not need to count.

## How the algorithm applies these rules

`src/keyword_coder.py`, method `a_form`, encodes the rules as follows (the encoding per word is in
`schema/keyword_list_v3.yaml`):

| Rule | Implementation | Limit |
|---|---|---|
| 0 Scope | Sentences from `split_sentences.py`: running text only, headings and "Voir aussi" and later sections dropped (TextExtracts has no infobox, tables or captions) | — |
| I1 Form | Plural, feminine and verb forms generated; words built on the same stem listed in `forms` | `forms` are proposals to check with the coders |
| I2 | Category names are entries of the list | — |
| I3 Span | Longest match wins, no overlap; multi-word entries matched whole | — |
| I4 Homonyms | `exclude` patterns per entry; "été" after *avoir*; possessive "son"; reflexive verbs need *se* | Only the listed expressions |
| I5 Names | Capitalised word inside a sentence, or word hyphenated to a capitalised one, is skipped | A lowercase word inside an institution name ("École des mines") is coded |
| I6 | Regular expression for values in °C | — |
| I7, I8 | All tenses, every occurrence | — |
| D1 | Sound, smell or feeling words in the sentence decide the code | Word lists, no syntax |
| D2 | `code: N` on *montagne* in the B list | — |
| D4, D6 | Not checked: E, A and R follow the form test | Main source of expected errors on long articles |
| D7 | PID = environments present in the sentence | No syntactic link |
