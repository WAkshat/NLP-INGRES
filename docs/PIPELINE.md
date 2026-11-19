# Full pipeline, ablations and error analysis

Code: `src/pipeline/agent.py`. Run: `scripts/run_pipeline.py` (stages `places`, `run`, `summary`).
Model: qwen3:8b (4-bit) via Ollama on an RTX 5060, temperature 0. Significance: paired McNemar exact tests.

- **§0 (November 2026): improved pipeline v3.** Results in `experiments/pipeline_v2/`.
- **§1–5 (October 2026): original pipeline (git tag `baseline-v1`).** Results in `experiments/pipeline/`; kept unchanged.

## 0. Improved pipeline v3 (November 2026)

### 0.1 What changed and why
All changes were designed on the DEV split. TEST and HARD_TEST were run once, after v3 was frozen.

| Step | Change | Motivating evidence |
|---|---|---|
| Resolver fix | Custom Tamil romaniser + voicing-neutral matching; ranker retrained | Audit B1: கர்நாடகா romanised as "gharnadhagha"; hand-written Tamil top-1 0.568 → 0.806 |
| Year rule | "2024-25" / "the 2025 assessment" → `'2024-2025'`, passed as a hint | 55 of 644 baseline SQLs had a wrong year set |
| Value snapping | Place literals in the SQL replaced by exact stored values (case, close spelling) | Model rewrote given spellings; a 0-row COUNT returns 0, so repair never fired. Offline replay on DEV: 12 fixed / 0 broken |
| Metric definitions | "share of extraction for irrigation" vs stage of extraction; list questions return names only | 9 of 38 v2 DEV errors in one question type |

### 0.2 DEV results (228 instances; used for design decisions)

| Configuration | EX | First attempt | English | Hindi | Hinglish | Tamil |
|---|---|---|---|---|---|---|
| `full`: baseline configuration + resolver fix | 77.2% | 75.4% | 84.2 | 64.9 | 87.7 | 71.9 |
| `v2`: + year rule | 83.3% | 82.0% | 91.2 | 77.2 | 86.0 | 78.9 |
| **`v3`: + value snapping + metric definitions** | **92.1%** | 92.1% | 100.0 | 89.5 | 91.2 | 87.7 |

Paired: v2 vs full 18 wins / 4 losses (p = 0.004); v3 vs v2 23 / 3 (p = 9e-5).

### 0.3 TEST and HARD_TEST results (run once)
Same environment for every row (Ollama 0.35.1, driver 621.24, empty response caches). The original code was re-run from
the `baseline-v1` worktree.

| System | test EX (n=384) | hard_test EX (n=260) |
|---|---|---|
| Keyword/template baseline (A) | 32.6% | 30.8% |
| qwen3:8b zero-shot (D) | 18.0% | 13.1% |
| Original pipeline, October run | 71.9% | 57.7% |
| **Original pipeline, re-run Nov 2026** | 72.1% | 58.8% |
| `full` (resolver fix only) | 74.7% | 59.6% |
| `v2` (+ year rule) | 78.4% | 61.5% |
| **`v3` (improved pipeline)** | **81.3%** [77.3, 85.2] | **70.4%** [65.0, 75.8] |
| `v3_loio` (examples of the question's own type hidden) | 51.0% | — |

- v3 vs original re-run: test 51 wins / 16 losses, McNemar p = 2e-05; hard_test 42 wins / 12 losses, McNemar p = 5e-05.
- Step by step (paired, test / hard_test): resolver fix vs original 12 wins / 2 losses, McNemar p = 0.013 / 4 wins / 2 losses, McNemar p = 0.688; + year rule (v2 vs full) 21 wins / 7 losses, McNemar p = 0.013 / 10 wins / 5 losses, McNemar p = 0.302; + snapping and definitions (v3 vs v2) 24 wins / 13 losses, McNemar p = 0.099 / 34 wins / 11 losses, McNemar p = 8e-04.
  The steps are complementary: on clean TEST the resolver fix and year rule carry the gain; on noisy HARD_TEST (misspelled names) value snapping does (v3 vs v2: 34/11, p = 0.0008).
- v3 by language (test): English 90.6, Hindi 75.0, Hinglish 84.4, Tamil 75.0.
- v3 by difficulty (test): simple lookup 73.3, filtered aggregate 90.4, cross-year 78.3, multi-hop 75.0.
- **Generalisation (`v3_loio`)**: with every TRAIN example of the question's own type hidden from retrieval, test EX
  falls from 81.3% to 51.0% (123 lost / 7 gained, p = 2e-28). That is below the original pipeline *with*
  same-type examples (39 / 120 vs the original, p = 9e-11).
  - By difficulty: simple lookup 55.0, filtered aggregate 66.0, cross-year 38.3, **multi-hop 8.3**.
  - By language: English 59.4, Hindi 50.0, Hinglish 46.9, Tamil 47.9.
  - Losses are spread across question types. Instances lost: district with the lowest stage of extraction in a state (14),
    unit metric lookup (11), units above their district's stage of extraction (8), districts with over-exploited units
    ranked by irrigation (8), state volume in BCM (8).
  - **Conclusion:** most of the headline accuracy comes from seeing a solved question of the same type. Accuracy on new
    question types is closer to 51% than to 81%.
- October vs November run of the same original code: 71.9 → 72.1% (test, 5 / 4, p = 1.0), 57.7 → 58.8% (hard, 6 / 3, p = 0.51); 84.8% of the 644 SQL strings were identical.

**Post-evaluation bug fix (v3.1, the shipped code).** The UI trace exposed a place-linker bug inherited from baseline-v1: the second pass kept its re-resolution whatever its score ("शीर्ष" → SIRSA at 0.0). Fixed (C-18), with a regression test. Measured afterwards with cached replays, so only affected questions called the LLM: DEV 92.1 → 94.3% (5 fixed / 0 broken), TEST 81.3 → 81.5% (1 / 0), HARD 70.4 → 71.2% (2 / 0). v3 stays the headline because it was frozen before the single TEST evaluation.

### 0.4 Error analysis (rule-based, on the predicted SQL; test + hard_test)
- Original re-run: 214 errors: other (filters, joins, output shape) 76; gold place literal missing from SQL 72; wrong assessment year 35; wrong metric / column 20; wrong aggregation 7; no SQL / execution error 4.
- v3: 149 errors: other (filters, joins, output shape) 62; gold place literal missing from SQL 37; wrong metric / column 22; wrong assessment year 12; wrong aggregation 11; no SQL / execution error 5.

### 0.5 Known measurement artefact
EX can score a wrong query as correct when the results happen to coincide. Example (DEV, IB_0034_ta): the linker missed
மகபூபாபாத் (Mahabubabad). The model wrote `MAHBUBNAGAR`, value snapping corrected it to the existing district
`Mahabubnagar`, and both districts had exactly 1 Critical unit in 2019-20. One of the 210 correct v3 DEV answers lacks a
gold place literal in its SQL.

### 0.6 Exploratory: more examples for unseen question types (DEV only)
With same-type examples hidden on DEV, 6 retrieved examples score 59.2% against 55.7% for 3 (14 / 6, p = 0.12, not
significant). Prompts grow from 2,857 to 3,295 tokens (+15%) and LLM time from 3.32 to 3.43 s. By the rule used for every
change in this round (adopt only what DEV supports), it is not adopted and was not run on TEST. Generalisation needs a
different remedy: pattern-level examples or fine-tuning (`docs/08_FUTURE_RESEARCH_ROADMAP.md`, item 1).

## 1. Components
1. **Schema-linker hints**: top-5 columns from the fine-tuned multilingual-e5-small (Phase 5).
2. **Place hints**: 1–3-word spans are resolved with the Phase 6 resolver. Matches with score ≥ 0.9 that don't overlap are
   kept, then re-resolved with the detected state as context, and their exact DB spellings go into the prompt. Dev F1 is 0.852.
3. **Retrieved examples**: the 3 TRAIN questions most similar to the input (e5 cosine), with their SQL.
4. **Execution-guided repair**: an SQL error or an empty result is sent back to the model, at most 2 times. The loop stops
   if the model repeats itself.
5. **Answer + numeric verification** (Phase 8). Not part of the EX evaluation: the UI uses it, and it is evaluated separately.

## 2. End-to-end results

| System | test EX (n=384) [95% CI] | hard_test EX (n=260) |
|---|---|---|
| A keyword/template | 32.6% [27.9, 37.5] | 30.8% |
| D qwen3:8b zero-shot | 18.0% [14.3, 21.9] | 13.1% |
| D + schema hints | 23.2% [19.3, 27.4] | — |
| **Full pipeline** | **71.9% [67.4, 76.0]** | **57.7% [51.9, 63.8]** |

- Full vs A: 167 wins / 16 losses on test, 88 / 18 on hard_test (p < 1e-6 for both). Full vs D: 211 / 4 and 121 / 5.
- By language (test): English 78.1, Hindi 69.8, Hinglish 77.1, Tamil 62.5. In absolute points the
  English–Tamil gap grows (10.4 for D → 15.6). In relative terms Tamil rises from 55% to 80% of English accuracy. Tamil
  is still the weakest language.
- By difficulty (test): simple lookup 55.8, filtered aggregate 84.6, cross-year 76.7, multi-hop 64.6. Zero-shot D scored
  8.3 / 35.9 / 5.0 / 0.0.
- Cost: mean 2.4 s of LLM time per question on test (2.9 s on hard_test), 2,892 prompt tokens, 0.20 repair turns.

## 3. Ablations (test, n=384)

Cumulative ladder:

| Configuration | EX | Δ |
|---|---|---|
| D zero-shot | 18.0% | |
| + schema hints | 23.2% | +5.2 (p = 0.008) |
| + place hints + repair (= full without examples) | 35.4% | +12.2 (60 / 13, p = 2e-8) |
| + 3 retrieved examples (= full) | **71.9%** | +36.5 (155 / 15, p = 2e-30) |

Leave-one-out from the full pipeline:

| Removed | EX | Δ vs full | Paired test |
|---|---|---|---|
| retrieved examples | 35.4% | −36.5 | 155 / 15, p = 2e-30 |
| place hints | 67.4% | −4.4 | 32 / 15, p = 0.019 |
| repair loop (first attempt only) | 70.3% | −1.6 | 6 fixed, 0 broken |

**What helps.**
- Retrieved examples are by far the biggest lever. They show the model the exact SQL idioms of this database: year
  labels, join paths and the level of each table.
- Place hints help significantly even on top of examples.
- Repair is small but never hurts: 6 fixes, 0 breaks. It runs on about 20% of test questions.

**Important caveat.** INGRES-Bench is template-based, and 376 of the 384 test instances use question types (intents) that
also occur in TRAIN, with different places, years and phrasings. Retrieved examples therefore often show a structurally
similar query. Part of the +36.5 points reflects this, and the gain on question types never seen in training would be
smaller. The keyword baseline A has the same advantage (it copies the nearest train SQL) and the pipeline still beats it
by 39 points. Only 8 test instances use an unseen intent, which is too few to measure separately. A leave-intents-out
pipeline evaluation is future work.

## 4. Error analysis (full pipeline, 218 errors on test + hard_test)
These are rule-based categories (`scripts/run_pipeline.py: error_category`): the first rule that matches wins.

| Category | Share of errors |
|---|---|
| place not linked (a gold place missing from the resolved places) | 41.3% |
| other (filters, joins, output shape) | 33.0% |
| wrong assessment year | 13.3% |
| wrong metric / column | 8.3% |
| wrong aggregation | 2.3% |
| no SQL / execution error | 1.8% |

- **Place linking is the largest error source, and it is worst in Tamil** (35 of Tamil's errors vs 14–24 in the other
  languages). This matches Phase 6: hand-written Tamil names are the weakest input (top-1 0.65). All gold places were found in only
  68% of test instances, because test places are deliberately unseen and include ambiguous and respelled names.
- Year errors (13%) are the "the N assessment" convention. Column errors are rare (8%) thanks to the schema linker.
- Execution errors are almost gone (1.8%), down from 6.3% for zero-shot D, thanks to examples and the repair loop.

## 5. Next steps suggested by the errors
1. Improve Tamil place resolution: Tamil-specific romanisation rules, or adding Tamil-script aliases to the gazetteer.
2. A deterministic year normaliser ("2025 assessment" → '2024-2025') before the LLM.
3. A leave-intents-out evaluation of the pipeline, to measure the gain on unseen question types.
4. A frontier-model comparison, to show how much of the remaining error is due to the 8B model.
