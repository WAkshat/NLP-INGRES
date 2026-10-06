# Geographic Entity Resolution (Phase 6)

Code: `src/entity_resolution/{gazetteer,resolver}.py`. Run: `python scripts/train_entity_resolver.py`.
Results: `experiments/entity_resolution/{results.json, per_mention.csv, errors_sample.csv}`.

## Method
- **Gazetteer** (9,558 entities: 37 states, 770 districts, 8,751 assessment units) built from `ingres.db`. Each entry
  has a canonical id, level, INGRES name, display name (`TAMILNADU` -> "Tamil Nadu", Himachal codes `KNG` -> "Kangra"),
  parent state and district, and aliases. Optional aliases: a curated table of 18 official renames / colloquial names
  (`COLLOQUIAL`, e.g. Gurgaon -> GURUGRAM) and historical INGRES spellings from the crosswalk (`add_history_aliases`).
- **Normalisation:** Devanagari and Tamil mentions are romanised (ISO 15919 -> ASCII), then phonetically folded
  (aa/a, sh/s, v/w, aspirates, doubled letters, Devanagari inherent final 'a'); a consonant skeleton is also kept.
- **Candidate generation:** char 2-4-gram TF-IDF over folded aliases (top 30) + exact folded matches.
- **Ranking:** logistic regression over 12 features: TF-IDF cosine, edit ratio and skeleton ratio on folded forms, exact
  match, **multilingual-e5-small embedding similarity** (mention vs alias), **hierarchy context** (candidate's state /
  district mentioned elsewhere in the question; conflict with a mentioned state), level indicators, length difference.
- **Training:** entities split 70/30 (seed 0). The ranker sees only synthetic noisy mentions of the 70% part
  (18,283 mentions: exact, lowercase, typo, transliteration variant, punctuation/space, automatic Devanagari / Tamil).
  Learned weights: edit ratio (+21.5) and embedding similarity (+10.6) dominate; state conflict is strongly
  penalised (-8.8); district context helps (+2.1).

## Results (top-1 / top-3 accuracy)

| Evaluation set | n (per condition) | No context top-1 | top-3 | With context top-1 | top-3 |
|---|---:|---:|---:|---:|---:|
| Synthetic noise, held-out entities | 5,985 | 0.841 | 0.951 | 0.885 | 0.964 |
| Hand-written Devanagari + Tamil names | 546 | 0.674 | 0.780 | 0.740 | 0.797 |
| Real INGRES historical respellings | 260 | 0.623 | 0.812 | 0.754 | 0.896 |
| Ambiguous names (shared across states) | 150 | 0.447 | 0.947 | **0.973** | 1.000 |
| Colloquial / renamed (no alias table vs alias table) | 16 | 0.188 | — | 0.813 (alias table) | — |

By noise type (top-1, no context -> with context): exact 0.896 -> 0.922, lowercase 0.888 -> 0.917, punctuation/space
0.863 -> 0.910, transliteration variant 0.881 -> 0.918, typo 0.798 -> 0.855, automatic Devanagari 0.871 -> 0.903,
automatic Tamil 0.688 -> 0.768, hand-written Hindi 0.780 -> 0.835, hand-written **Tamil 0.568 -> 0.645**,
historical fuzzy respellings 0.619 -> 0.746.

## Error analysis
Top-1 failures by category (`results.json` -> `error_categories`):
- **Right name, wrong place (homonym)** dominates (1,057 of 1,644 synthetic errors; 80 of 87 ambiguous-set errors).
  Even exact names fail without context because the name is genuinely ambiguous: Puducherry and Chandigarh are both
  a state and a district; the CHURU unit lies in CHURU district; INGRES holds Himachal districts under both codes and
  full names in different cycles (SRM / SIRMAUR, SHM / SHIMLA); some J&K units are literally named "Not Accessed".
  Context resolves almost all of these (ambiguous set 0.45 -> 0.97).
- **Wrong administrative level** (200 synthetic, 127 hand-script): district vs unit of the same name. A level hint from
  the question ("block", "ज़िला", "மாவட்டம்") would fix many; not yet used.
- **Tamil script is the weakest input** (hand-written 0.57 top-1). Tamil script does not mark voicing or aspiration, so
  romanised Tamil ("பாக்மாரா" -> "pakmara") diverges further from INGRES spellings than romanised Devanagari.
- **Colloquial names** are not recoverable by string similarity (0.19); they need an alias table (0.81 with 18 curated
  aliases; the remaining misses are renames whose new name is not in the INGRES district list).

## Limitations
- A bug in the typo generator (it could return the name unchanged) was caught by a unit test and fixed before
  the numbers above were produced.
- The synthetic evaluation noise comes from the same generators as the training noise (different entities). The
  hand-script, historical and colloquial sets are the realistic ones.
- Mention detection (finding the place-name span in a full question) is not part of this evaluation; mentions are given.
- Integration into Text-to-SQL (resolved names as prompt hints / agent tool) is future work (Phase 9).
