# INGRES-Bench v1

A multilingual Text-to-SQL benchmark over the canonical INGRES database (`data/processed/ingres.db`,
see `docs/DATA_ACCESS_REPORT.md`). **371 items × 4 languages = 1,484 question instances**, each with gold SQL
and a gold result obtained by executing that SQL.

| File | Content |
|---|---|
| `data/benchmark/ingres_bench_v1.jsonl` | all instances |
| `data/benchmark/{train,dev,test,hard_test}.jsonl` | the same instances, one file per split |
| `data/benchmark/entity_pool.csv` | the fixed entity pool questions are drawn from |
| `data/benchmark/transliterations.json` | Devanagari / Tamil renderings of every pool name |
| `reports/benchmark_qc.json`, `reports/benchmark_manual_review.csv` | QC output and manual review |

Rebuild: `python scripts/build_benchmark.py`, then `python scripts/qc_benchmark.py` (deterministic, seed 7).

## 1. Construction protocol

**This is an LLM-authored, template-grounded benchmark.** Question wording was written by Claude (the assistant
building this repository) as phrasings with slots. SQL, entities and answers come from the real database.
It is not a corpus of organic user queries; see §6.

1. **Entity pool** (`src/benchmark/pool.py`, seeded). 173 real assessment units from 37 states/UTs and 94 districts:
   up to 2 districts × 2 units per state, 8 deliberately **ambiguous unit names** (e.g. *Rampur*, *Rajgarh*,
   *Mohanpur*, shared by units in ≥3 states; up to 5 occurrences each), and 12 units with a **real historical
   respelling** in INGRES (from the cross-year crosswalk, e.g. SONKUTCH → SONKATCH). A unit is only eligible if
   (unit name, district, state) is unique, so gold SQL can address it by name.
2. **Intents** (`src/benchmark/intents.py`). 38 SQL patterns over 4 difficulty levels. Each has a sampler
   that draws real entities, years, categories and thresholds, an answer shape, and ≥3 phrasings per language.
3. **Gold SQL and result.** Every sampled SQL is executed through the read-only executor. An item is kept only if the
   result is non-empty and well-formed: scalars not NULL, lists of at most 20 rows, most zero counts resampled, and the unit
   filter matching **exactly** the intended unit. Duplicate (intent, SQL) pairs are rejected.
4. **Entity mention level.** A unit is mentioned with just enough context to be unambiguous: name only if the
   name is unique nationwide (sometimes still with its state), name + state if unique within the state, otherwise
   name + district + state. The gold SQL filters on exactly the mentioned context.
5. **Rendering in 4 languages.** All four versions of an item are generated from the **same slots**
   (place, year, metric, category, number), so they have identical SQL by construction.
   Hindi/Hinglish metric nouns carry grammatical gender for agreement (का/की, था/थी). Tamil phrasings use
   postpositional frames (…பகுதியில், …மாநிலத்தில்) to avoid gluing case suffixes onto transliterated names.
   Place names are Devanagari/Tamil script in 85% of Hindi/Tamil instances and Latin script in 15%, reflecting
   common mixed-script usage. Hinglish lower-cases names 30% of the time.
6. **Year convention.** `2024-25` / `2024-2025` mean `assessment_year = '2024-2025'`. "the *N* assessment"
   (e.g. "2025 के आकलन में", "2025 மதிப்பீட்டில்") means the **published GWRA N report**, i.e.
   `'(N-1)-N'`. So "the 2024 assessment" is `'2023-2024'`, following the official naming verified in the data report.
   Bare single years are never used as slots.
7. **Cross-year questions** are only generated for (state, year A, year B) where the state's assessment-unit
   type is unchanged (MANDAL ≡ BLOCK) and the unit count differs by ≤10% (`state_unit_granularity`).
   Every cross-year item carries the methodology caveat text in `methodology_caveat` (106 items).

### Language choice and translation validation
- Dravidian language: **Tamil**. Tamil Nadu is data-rich in INGRES, the script is distinct from Devanagari
  and Latin (useful for the tokenizer study), and open Indic model support is good.
- **No native-speaker validation was available.** Protocol used instead:
  (a) slot-aligned generation (translations cannot change the SQL semantics);
  (b) automatic back-transliteration check of all 546 name renderings (`scripts/check_transliterations.py`):
      543 pass, 3 flagged and hand-reviewed as correct (standard exonyms or English words), 0 failing;
  (c) automatic slot-presence QC on every instance (§4);
  (d) author review of a stratified random sample (§5).
  A back-translation check with an independent MT model (e.g. IndicTrans2) is **not yet done**. It needs a model
  download.

## 2. Difficulty levels and intents

| Level | Intents | Items | Examples of what is required |
|---|---:|---:|---|
| simple_lookup | 7 | 107 | one table plus joins for names; one year (unit / district / state metric, category, unit→district, unit type, BCM conversion) |
| filtered_aggregate | 13 | 120 | COUNT / AVG / percentage / top-k / BETWEEN / arg-min/max over units, districts or states |
| cross_year | 9 | 80 | self-joins across `assessment_year`, change detection, category transitions, first year in a category |
| multi_hop | 9 | 64 | nested aggregates and CTEs, comparison with state/district aggregates, granularity-aware filtering |

Answer shapes: scalar 259, list 44, ordered table 40, table 28 (items).

## 3. Splits and leakage control

| Split | simple | aggregate | cross-year | multi-hop | Items | Instances |
|---|---:|---:|---:|---:|---:|---:|
| train | 47 | 46 | 34 | 26 | 153 | 612 |
| dev | 11 | 25 | 6 | 15 | 57 | 228 |
| test | 30 | 39 | 15 | 12 | 96 | 384 |
| hard_test | 19 | 10 | 25 | 11 | 65 | 260 |

- **Item-level splitting:** all four language versions of an item are in the same split. No paraphrase of an item
  appears in two splits (QC: 0 SQL strings and 0 question strings shared across splits).
- **Entity partition:** pool units are split into a train/dev side (≈60%) and a test side (≈40%). Ambiguous and
  respelled units lean to the test side (75%).
- **Phrasing hold-out:** the last phrasing of every (intent, language) is never used in train/dev (QC: 0 violations).
- **hard_test** over-represents cross-year and multi-hop items (55% of its items vs 28% in test), ambiguous and respelled
  entities (7 of 13 ambiguous-name items), and gets **noise** on 201 of 260 instances:

| Noise (hard_test instances) | English | Hindi | Hinglish | Tamil |
|---|---:|---:|---:|---:|
| typo in an entity name (vowel drop, swap, doubling, phonetic respelling) | 28 | 30 | 30 | 37 |
| real historical INGRES respelling of the unit | 1 | 2 | 2 | 3 |
| entity names left in Latin script inside Hindi/Tamil | — | 49 | — | 51 |
| lowercase, no punctuation | 35 | — | 39 | — |
| numbers written as words (e.g. "sattar percent", "எழுபது சதவீதம்") | 1 | 1 | 2 | 0 |

## 4. Quality control (`scripts/qc_benchmark.py`, result in `reports/benchmark_qc.json`)

| Check | Failures / 1,484 |
|---|---:|
| SQL parses and executes (read-only executor) | 0 |
| Gold result reproduces on re-execution | 0 |
| Referenced tables/columns exist in `schema.json` | 0 |
| Every SQL literal (year, category, number, entity, metric) is expressed in the question | 0 |
| All 4 language versions share SQL and split, and all pass the slot check | 0 |
| SQL or question text leaked across splits | 0 |
| Held-out phrasing used in train/dev | 0 |

Sensitivity of the slot check: on 2,011 deliberately corrupted clean questions (year, entity or category replaced),
it flagged 1,952 (97.1%). The remaining 59 mutations changed words that are not SQL literals (e.g. "safe or
over-exploited?" in a question whose SQL just selects the category). Those are correct passes, except for the category-literal gap that was
found this way and fixed (category literals inside `IN (...)` and in multi-hop CTEs are now checked).

## 5. Manual review
A stratified random sample of 24 instances (6 per language, every difficulty; `reports/benchmark_manual_review.csv`)
was reviewed by the author (an LLM, **not** a native speaker). **24/24 ask what the gold SQL computes.** 2/6 Tamil
instances have minor grammatical awkwardness (adjective + "ஆக"; a state name not in adjectival form); both
remain understandable.

## 6. Limitations
- **Template-grounded, LLM-authored text.** 439 distinct phrasings; linguistic variety is lower than organic user
  queries, and the phrasings may be closer to how an LLM writes than how farmers or officials ask. Results on
  INGRES-Bench should not be read as performance on real traffic.
- **Same-family bias.** If the frontier-LLM baseline (Phase 4) is a Claude model, it shares authorship style with the
  questions and may be advantaged. A baseline from another model family should be reported alongside.
- **No native-speaker verification** of the Hindi, Hinglish or Tamil text (see §1).
- **Unit coverage:** 51 distinct units appear in the 93 unit-level items; only 13 items test ambiguous unit names.
- **Zero-valued answers:** 26 items have gold 0 (zero counts, or a genuinely zero future availability).
  Degenerate systems that always answer 0 will score on these.
- Noise in hard_test is mostly synthetic. Only 8 instances use real historical respellings.
- Gold SQL addresses entities by their exact INGRES spelling (e.g. `'TAMILNADU'`, `'KNG'`-style HP district codes are not
  in the pool). A system must map user spellings to these, which is intended.

## 7. Evaluation protocol (implemented in Phase 4)
Primary metric: **execution accuracy (EX)**, Spider/BIRD-style. The predicted SQL is executed on `ingres.db` with the
read-only executor, and the result is compared with `gold_result`:
- a multiset comparison of rows, order-insensitive, except when the gold SQL has `ORDER BY` (shapes `table_ordered`, top-k),
  where order matters;
- numeric cells equal within relative tolerance 1e-6 (absolute 1e-9 near zero); strings compared exactly;
- column order must match; extra or missing columns count as wrong;
- errors, timeouts or refused SQL count as wrong.
Scores are broken down by language, difficulty, split, intent, noise type and entity-ambiguity flag.
