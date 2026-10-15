# Full pipeline, ablations and error analysis (Phases 9 and 11)

Code: `src/pipeline/agent.py`. Run: `scripts/run_pipeline.py` (stages `places`, `run`, `summary`). Results:
`experiments/pipeline/{results.json, full.jsonl, no_fewshot.jsonl, no_places.jsonl, places_dev.json, errors_full.csv}`.
Model: qwen3:8b (4-bit) via Ollama on an RTX 5060, temperature 0. Significance: paired McNemar exact tests.

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
