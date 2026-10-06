# Baselines (Phase 4)

All numbers are from `experiments/baselines/*/metrics.json` and `experiments/schema_linking/baselines.json`,
evaluated on INGRES-Bench v1 **dev + test + hard_test** (872 instances = 218 per language). The train split is only
used as retrieval memory / few-shot pool. 95% CIs are bootstrap intervals over instances; instances of the same item
in different languages are not independent, so the CIs are somewhat optimistic.

Commands:
```bash
python scripts/run_baselines.py --baseline A
python scripts/run_schema_linking_baselines.py            # B, C and the random reference
python scripts/run_baselines.py --baseline D --model gemini-3.6-flash --splits test hard_test dev --patient
```

## Baseline A: keyword / template retrieve-and-fill (`src/baselines/keyword.py`)
Retrieves the lexically closest **train** question (char 2-4-gram TF-IDF), reuses its SQL as a skeleton, and
re-fills years, categories, numbers, the metric column and place names extracted with rules. The gazetteer is built from
database names only; Hindi/Tamil text is romanised generically. **Caveat:** the metric/category keyword lexicon is the
benchmark's own (`src/benchmark/lexicon.py`), so A is an *optimistic* keyword system.

**Execution accuracy 38.8%** (872). SQL exact match 35.6%, execution errors 0%, mean latency 0.32 s (CPU).

| Split | EX | 95% CI |
|---|---:|---|
| dev | 58.3% | 51.8-64.5 |
| test | 32.6% | 27.9-37.5 |
| hard_test | 30.8% | 25.0-36.2 |

| | English | Hindi | Hinglish | Tamil |
|---|---:|---:|---:|---:|
| EX (all 3 splits) | 46.8% | 34.9% | 44.5% | 28.9% |

| Difficulty | EX | 95% CI |
|---|---:|---|
| simple_lookup | 24.2% | 19.2-29.6 |
| filtered_aggregate | 46.0% | 40.2-51.7 |
| cross_year | 28.3% | 22.3-34.8 |
| multi_hop | 60.5% | 52.6-68.4 |

Observations (descriptive, not causal):
- **Template artifact.** Multi-hop items are easiest for A because their SQL skeletons have few slots, so retrieving a
  similar train question almost solves them. Retrieval-heavy systems' multi-hop EX should be read with this in mind.
  Simple lookups are hardest for A because they depend on resolving a unit name.
- **Dev ≫ test** (58% vs 33%) is the effect of the entity partition and phrasing hold-out, as designed.
- **Ambiguous place names:** 9.4% EX (n=32, CI 0-19%) vs 39.9% (n=840) for the rest.
- Noisy (hard-test noise) 32.3% vs clean 40.7%.
- Code-mixing proxy and question length correlate *positively* with EX for A (high code-mix 46%, none 37%;
  >20 words 73%, ≤10 words 28%). Both are confounded: Hinglish keeps English technical terms that match the lexicon,
  and long questions are mostly multi-hop templates. The Phase 7 study will control for these.

## Baselines B and C: schema retrieval (`src/schema_linking/retrieval.py`)
Rank 106 columns and 9 tables of `schema.json` (English names + descriptions) for each question. Gold = columns used
by the gold SQL, excluding join keys and name columns (they carry no linking signal).

**Column Recall@3 by language**

| Method | English | Hindi | Hinglish | Tamil | Overall |
|---|---:|---:|---:|---:|---:|
| Random (no schema linking) | 0.025 | 0.033 | 0.041 | 0.012 | 0.028 |
| B: BM25 | 0.447 | 0.009 | 0.603 | 0.009 | 0.267 |
| C: multilingual-e5-small (off-the-shelf) | 0.600 | 0.339 | 0.421 | 0.276 | 0.409 |
| Fine-tuned (Phase 5) | TODO — requires experiment | | | | |

| Method | Col R@1 | Col R@3 | Col R@5 | Col MRR | Latency / query |
|---|---:|---:|---:|---:|---:|
| Random | 0.007 | 0.028 | 0.055 | 0.049 | — |
| B: BM25 | 0.161 | 0.267 | 0.307 | 0.230 | 0.14 ms |
| C: multilingual-e5-small | 0.221 | 0.409 | 0.499 | 0.353 | 3.8 ms (+48 s one-off load/index) |

Observations:
- **BM25 collapses on native scripts** (Hindi 0.009, Tamil 0.009): no token overlap with the English schema text.
- **Off-the-shelf multilingual embeddings partly bridge scripts,** but Hindi and Tamil remain 26-32 points below English.
  This gap is the motivation for the learned schema linker (Phase 5).
- BM25 does best on **Hinglish** (0.603), whose questions keep English technical terms.
- Table-level recall is not informative (most queries use 3-5 of 9 tables, so random R@3 = 0.33); it is reported in the JSON only.

## Baseline D: frontier LLM (Gemini, free tier) (`src/baselines/llm.py`)
Zero-shot: system instruction + documented conventions (year naming, category labels, INGRES spellings, units) +
the full schema with descriptions and example values; temperature 0; model `gemini-3.6-flash`.
Responses are cached (`cache/llm/`, git-ignored), so reruns cost no quota.

Free-tier facts established while setting this up (2026-09-28):
- Limits are per Google Cloud project, visible only in AI Studio; RPD resets at midnight Pacific. Google does not publish
  per-model numbers. Any 429 quota details returned by the API are logged to `experiments/baselines/gemini_quota_log.jsonl`.
- `gemini-2.5-flash` / `-flash-lite` return 404 ("no longer available to new users"); `gemini-2.5-pro` has no free tier.
- Most 3.x models answered **503 "high demand"** repeatedly; `gemini-3.6-flash` and `gemini-3-flash-preview` answered
  some probes. The run therefore uses long backoff and is resumable.
- Free-tier prompts and responses may be used by Google to improve its products (pricing page). Only public
  INGRES data is sent.

**Gemini result: not obtainable on the free tier.** The API reported the actual quota on 2026-09-28:
`GenerateRequestsPerDayPerProjectPerModel-FreeTier` = **20 requests/day** for `gemini-3.6-flash`
(`experiments/baselines/gemini_quota_log.jsonl`). 872 evaluation questions would take ~44 days, so the frontier baseline
is replaced by a local open model (below). Gemini remains available in the code (`--backend gemini`).

### Baseline D (local): `qwen3:8b` via Ollama, zero-shot
Served locally by Ollama (Q4 quantisation, RTX 5060 8 GB, thinking disabled, temperature 0, seed 0). The full schema dump
(~9k tokens) overflowed the 8k context, so local runs use a compact schema rendering (`compact_schema_prompt`: one line
per table, shared metric columns described once, exact INGRES state spellings) with the conventions and explicit rules
(full year labels, column locations, standard join path) placed next to the question. On a 24-question dev pilot,
`qwen2.5-coder:7b` scored 3/24 and `qwen3:8b` 8/24, so `qwen3:8b` was selected (pilot questions are dev, not test).

**Execution accuracy 18.2%** (872; CI by split below), execution errors 6.3%, mean latency 2.5 s, 1.50 M prompt tokens,
0 truncated prompts.

| Split | EX | 95% CI | | Language | EX | 95% CI |
|---|---:|---|---|---|---:|---|
| dev | 24.6% | 19.3-29.8 | | English | 22.5% | 17.0-28.0 |
| test | 18.0% | 14.3-21.9 | | Hindi | 16.5% | 11.9-21.6 |
| hard_test | 13.1% | 8.9-16.9 | | Hinglish | 19.7% | 14.7-25.2 |
| | | | | Tamil | 14.2% | 10.1-18.8 |

By difficulty: simple lookup 10.0%, filtered aggregate 38.9%, cross-year 7.6%, multi-hop 4.0%.
Ambiguous place names 3.1% (n=32) vs 18.8%; noisy hard-test questions 12.4% vs 20.0% clean.

Observations: the 8B model **scores below the keyword/template baseline A (38.8%)**. Its typical errors (inspected on the
pilot) are exactly the targets of the later components: misapplied year convention ("the 2023 assessment" -> 2023-2024),
wrong metric column (schema linking), unresolved or mis-cased place names (entity resolution), unit-level rows where a
state aggregate is asked (level confusion), and failing multi-step joins. A few-shot variant (4 fixed English train
examples) is run with `--few-shot 4`.
