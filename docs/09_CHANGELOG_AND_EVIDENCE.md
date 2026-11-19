# INGRES — Changelog and Evidence Ledger

## 1. Changelog (modernization, November 2026)

Baseline: git tag `baseline-v1` (commit `79ec245`). Every change below has a test or a measurement.

| ID | Date | Change | Files | Why (audit finding) | Evidence |
|---|---|---|---|---|---|
| C-01 | 11-17 | Tamil romaniser replaces the library's TAMIL→ISO scheme; Devanagari anusvara made homorganic | `src/entity_resolution/gazetteer.py` | B1, B4 | E-01, E-05; tests `test_tamil_romanisation_*`, `test_anusvara_*` |
| C-02 | 11-17 | Voicing-neutral second TF-IDF space for Tamil-script mentions | `src/entity_resolution/resolver.py` | B1 | E-05; `test_resolver_ranks_tamil_script_state_first` |
| C-03 | 11-17 | Resolver: batched mention embeddings (`embed`), optional precomputed embedding in `resolve`, on-disk alias-embedding cache | `resolver.py`, `src/pipeline/agent.py` | D1, D2 | E-10 |
| C-04 | 11-17 | Entity ranker retrained (same seed and data); `--embedder` / `--out` options | `scripts/train_entity_resolver.py`, `experiments/entity_resolution/` | B1 | E-05 |
| C-05 | 11-17 | Year rule (`year_labels`) passed as a prompt hint | `src/pipeline/years.py`, `agent.py` | B2, D7 | E-02, E-06; `test_year_labels` |
| C-06 | 11-17 | Error taxonomy based on the predicted SQL | `scripts/run_pipeline.py` | B3 | E-03; `test_error_category_*` |
| C-07 | 11-17 | Ollama HTTP errors raised immediately with the server message | `src/baselines/llm.py` | B5 | code review |
| C-08 | 11-17 | `exclude_intent` (leave-own-intent-out) evaluation mode | `agent.py`, `run_pipeline.py` | D6 | E-12 |
| C-09 | 11-19 | Value snapping of place literals before execution | `src/pipeline/values.py`, `agent.py` | new (dev error analysis) | E-07; 2 tests |
| C-10 | 11-19 | Metric definitions note (pipeline only) | `agent.py: DOMAIN_NOTES` | new (dev error analysis) | E-07 |
| C-11 | 11-19 | Per-stage timings returned by `Pipeline.sql` / `answer` | `agent.py` | observability | UI trace |
| C-12 | 11-19 | `INGRES_LLM_CACHE` overrides the response-cache directory | `llm.py` | B6 (cross-environment replay) | E-04 |
| C-13 | 11-19 | New Streamlit app: chat, verification badges, charts, trace, live ablations, Explore and Results pages | `app/streamlit_app.py`, `app/examples.json`, `.streamlit/config.toml` | UI | AppTest; E-11 |
| C-14 | 11-17 | Tooling: `scripts/model_forensics.py`, `scripts/benchmark_perf.py` | `scripts/` | Phase 1 / 4 | `experiments/forensics/`, `experiments/perf/` |
| C-15 | 11-17 | Tests: `tests/test_modernization.py` (8 tests); repair-loop test helper updated | `tests/` | regression safety | 69 tests pass |
| C-16 | 11-19 | `v3k6_loio` config (6 retrieved examples with same-type examples hidden) | `scripts/run_pipeline.py` | generalisation experiment | see `docs/PIPELINE.md` §0.6 |
| C-17 | 11-19 | App: removed misleading metric arrows; examples restricted to DEV questions whose SQL contains the gold places | `app/` | UI correctness | screenshots |
| C-18 | 11-19 | Place linker second pass: keep a re-resolution only if it clears τ; drop out-of-state places with no confident in-state match | `src/pipeline/agent.py: PlaceLinker.link` | bug found in the UI trace ("शीर्ष" → SIRSA, score 0.0); inherited from baseline-v1 | E-21; `test_second_pass_needs_a_confident_match` |

Unchanged on purpose: the benchmark, the EX metric, the shared prompt `CONVENTIONS`, the schema linker checkpoint, the
LLM and its options. The baseline-v1 result files in `experiments/pipeline/` and `experiments/entity_resolution/baseline_v1/`
are kept as they were.

## 2. Evidence ledger

Label key: CODE (source), CONFIG, RUNTIME (observed by running), BENCH (benchmark script with stored output),
EXT (external source), INF (inferred).

| ID | Claim | Value | Label | Command | Stored at |
|---|---|---|---|---|---|
| E-01 | Old romaniser output for கர்நாடகா | `gharnadhagha` | RUNTIME | `romanise()` at `baseline-v1` | audit §7.1 |
| E-02 | Year-rule accuracy on TRAIN / DEV (current rule) | 612/612, 228/228 | RUNTIME | inline check, `src/pipeline/years.py` | this ledger |
| E-02b | Old keyword-baseline year rule on test+hard, Tamil | 77.6% | RUNTIME | audit script | audit §7.1 |
| E-03 | Baseline "place not linked" errors whose SQL still had every gold place | 31 of 90 | RUNTIME | audit script over `experiments/pipeline/errors_full.csv` | audit §7.1 |
| E-04 | Same model ID, Oct vs Nov environment: identical SQL | 24 / 39 | RUNTIME | `experiments/forensics/determinism_replay.json` | idem |
| E-04b | Two live runs, same Nov environment | 39 / 39 identical | RUNTIME | idem | idem |
| E-05 | Resolver hand-written Tamil top-1 (no ctx / ctx) | 0.568 → 0.806 / 0.645 → 0.857 | BENCH | `python scripts/train_entity_resolver.py` | `experiments/entity_resolution/{baseline_v1/,}results.json` |
| E-05b | Paired change, hand Tamil | 128 fixed, 5 broken, p = 6e-32 | BENCH | per-mention CSVs | `per_mention.csv` (both) |
| E-06 | Place linker DEV F1 at τ = 0.9 | 0.852 → 0.905 | BENCH | `run_pipeline.py --stage places` | `experiments/{pipeline,pipeline_v2}/places_dev.json` |
| E-07 | DEV EX: full (resolver fix) / v2 (+year) / v3 (+snap, +definitions) | 0.772 / 0.833 / 0.921 | BENCH | `run_pipeline.py --stage run --splits dev` | `experiments/pipeline_v2/{full,v2,v3}.jsonl` |
| E-07b | DEV paired: v2 vs full; v3 vs v2 | 18/4 p = 0.004; 23/3 p = 9e-5 | BENCH | `mcnemar` | idem |
| E-08 | qwen3:8b exact parameters | 8,190,735,360 | RUNTIME | `python scripts/model_forensics.py` | `experiments/forensics/models.json` |
| E-09 | e5-small exact parameters | 117,653,760 | RUNTIME | idem | idem |
| E-10 | Performance before/after | see `docs/04_BENCHMARKS_AND_PERFORMANCE.md` | BENCH | `python scripts/benchmark_perf.py` | `experiments/perf/*.json` |
| E-11 | All-India 2024-25 from the DB vs PIB | 60.6% / 247.22 BCM / 448.51 BCM vs 60.63 / 247.22 / 448.52 | RUNTIME | Explore page SQL | app |
| E-12 | TEST EX: original re-run / full / v2 / **v3** / v3_loio | 72.1% (277/384) / 74.7% (287) / 78.4% (301) / **81.3% (312)** / 51.0% (196) | BENCH | `run_pipeline.py --stage run` + `--stage summary` | `experiments/pipeline_v2/{baseline_v1_rerun,full,v2,v3,v3_loio}.jsonl`, `results.json` |
| E-12b | HARD_TEST EX: original re-run / **v3** | 58.8% (153/260) / **70.4% (183/260)** | BENCH | idem | idem |
| E-12c | Paired TEST: v3 vs original; full vs original; v2 vs full; v3 vs v2 | 51/16 p = 2e-5; 12/2 p = 0.013; 21/7 p = 0.013; 24/13 p = 0.099 | BENCH | `mcnemar` in `run_pipeline.py` | `results.json` → `paired_tests` |
| E-12d | Paired HARD: v3 vs original | 42/12 p = 5e-5 | BENCH | idem | idem |
| E-12f | HARD ladder: original / full / v2 / v3 (paired steps) | 58.8 / 59.6 (4/2, p = 0.69) / 61.5 (10/5, p = 0.30) / 70.4 (34/11, p = 0.0008) | BENCH | idem | idem |
| E-12g | DEV, same-type examples hidden: 3 vs 6 examples | 55.7% vs 59.2% (14/6, p = 0.12) | BENCH | `--config v3_loio / v3k6_loio --splits dev` | `v3_loio.jsonl`, `v3k6_loio.jsonl` |
| E-20 | November LLM calls | 4,595 (cached), 3.28 GPU-hours | RUNTIME | cache file count | `cache/llm_2026-11/`, worktree cache, `cache/llm/` |
| E-21 | v3 → v3.1 (fix C-18), cached replays | DEV 92.1 → 94.3 (5/0), TEST 81.3 → 81.5 (1/0), HARD 70.4 → 71.2 (2/0) | BENCH | `--config v31` | `experiments/pipeline_v2/v31.jsonl` |
| E-12e | v3 vs v3_loio (TEST) | 123/7 p = 2e-28 | BENCH | idem | idem |
| E-13 | Original code, October vs November environment | TEST 71.9 → 72.1 (5/4, p = 1.0); HARD 57.7 → 58.8 (6/3, p = 0.51); 84.8% identical SQL | BENCH | baseline-v1 worktree re-run | `experiments/pipeline/full.jsonl` vs `experiments/pipeline_v2/baseline_v1_rerun.jsonl` |
| E-14 | Errors TEST+HARD, original → v3 | 214 → 149 (place missing 72 → 37, wrong year 35 → 12) | BENCH | `error_analysis` | `results.json` → `error_analysis`, `errors_*.csv` |
| E-15 | Lucky-correct v3 answers (SQL without gold place literal) | 4 / 495 | RUNTIME | ad-hoc check with `sql_has_places` | `experiments/pipeline_v2/v3.jsonl` |
| E-16 | Pre-LLM latency mean, baseline → v3 | 115.78 → 47.87 ms (−58.7%); place linking 107.16 → 39.18 ms | BENCH | `benchmark_perf.py --stage components` | `experiments/perf/{baseline,optimized}_components.json` |
| E-17 | Cold start, baseline → v3 (cache / no cache) | 22.13 → 8.25 s / 22.28 s | BENCH | idem (+ `optimized_nocache`) | idem |
| E-18 | End-to-end `Pipeline.sql` median, baseline → v3 | 2,085 → 2,095 ms (≈0%); LLM share 94.7% → 97.6% | BENCH | `--stage e2e` | `experiments/perf/{baseline,optimized}_e2e.json` |
| E-19 | LLM serving (v3 prompt) | median 2,010 ms, TTFT 285 ms, 51.8 tok/s, 8,697 prompt tok/s, VRAM 7,459 MiB in use | BENCH | `--stage llm` | `experiments/perf/optimized_llm.json` |
