# INGRES — Features and Implementation

Every feature implemented in the repository, with where it lives, how it works and how it was verified. "Tests" refers to
`python -m pytest` (69 tests). Numbers are from files under `experiments/` unless stated.

## A. User-facing features (Streamlit app, `app/streamlit_app.py`)

| Feature | What the user sees | Implementation | Verified by |
|---|---|---|---|
| **Multilingual Q&A chat** | Ask in English, Hindi (Devanagari), Hinglish or Tamil; conversation history kept in the session | `st.chat_input` → `Pipeline.answer` (`src/pipeline/agent.py:187`), cached pipeline (`st.cache_resource`) | AppTest render test; live Hindi question → correct SQL and Hindi answer (240,136.75 ham, Ludhiana 2024-25) |
| **Verified answer badge** | "✓ N number(s) verified against the data", or "⚠ model wording had unverified numbers — showing raw result" | `grounded_answer` (`src/grounding/verifier.py:98`) | 98.1% detection, 0% false alarms (`experiments/grounding/results.json`) |
| **Result table + CSV download** | Sortable table; "Download CSV" | `st.dataframe`, `st.download_button` | AppTest |
| **Automatic chart** | Bar chart when the result has 2–60 rows with a label and a number | `auto_chart` (Altair) | AppTest |
| **SQL view + value corrections** | The executed SQL; any place spelling corrected by value snapping ("'E Lungdah' → 'E LUNGDAR'") | `ValueSnapper.snap` output | 6 tests in `tests/test_modernization.py` |
| **Pipeline trace** | Schema hints, resolved places with scores, year labels, every attempt with its error, time per stage | `timings_ms`, `attempts`, `places` returned by `Pipeline.sql` | — |
| **Live ablation switches** | Turn off schema hints, place resolution, retrieved examples, year rule, metric definitions or value snapping for the next question | `components()` context manager swaps the pipeline attributes and restores them | Manual |
| **Example questions** | 4 per language, all answered correctly by v3 on DEV | `app/examples.json` (generated from `experiments/pipeline_v2/v3.jsonl`, dev only) | Correct on dev |
| **LLM status** | "LLM ready" / "LLM offline"; chat disabled when offline | `GET /api/tags`, 1.5 s timeout, cached 15 s | Manual |
| **Explore page (no LLM)** | Stage of extraction, extraction, recharge, over-exploited units for any year and region; category donut; state/district bar chart with 70% / 100% guides; 25 most stressed units; category shares across cycles | Direct SQL through the read-only executor | All-India 2024-25 values equal the published figures: 60.6% stage (PIB 60.63), 247.22 BCM extraction (247.22), 448.51 BCM recharge (448.52) |
| **Results page** | EX of every system, component metrics, speed table — read from result files | JSON readers | AppTest |

## B. NLP pipeline features (`src/pipeline/`)

| Feature | Purpose | Algorithm | Config / default | Edge cases & limitations |
|---|---|---|---|---|
| Schema linking | Tell the LLM which of 106 columns matter | Fine-tuned e5 bi-encoder, cosine, top-k | `k_cols = 5` | Gives columns, not tables/joins |
| Place linking | Map place names in any script to exact DB names | 1–3-word spans → resolver (TF-IDF candidates → 12-feature LR) → score ≥ τ → greedy non-overlap → re-resolve with detected state | τ = 0.9 (tuned on DEV) | Tamil recall 0.725 at τ = 0.9 on DEV; spans made only of frequent non-place words are skipped |
| Retrieved examples | Show 3 similar solved questions | Cosine over 612 TRAIN question embeddings | `k_shots = 3` | Benefits from template overlap; `exclude_intent` hides same-type examples for evaluation |
| Year rule | Convert "2024-25", "2025 ke assessment", "2025 के आकलन", "2025 மதிப்பீட்டில்" to `'2024-2025'` | Regex over normalised digits (Devanagari, Tamil digits) | on | Only the 5 cycles in the DB; a year outside them yields no hint |
| Metric definitions | Prevent stage-of-extraction / share-of-extraction confusion | Fixed 2-sentence prompt note | on | Covers irrigation/domestic/industrial shares only |
| Value snapping | Make place literals exact DB values | Regex over `=`, `IN`, `UPPER()=UPPER()` on name columns; exact → case → folded spelling (≥ 0.80, margin 0.05) | on | Leaves `LIKE '%…%'` alone; an unknown name with no close match stays unchanged |
| Execution-guided repair | Fix SQL errors and empty results | Error text appended as a user turn | `max_repairs = 2` | A wrong non-empty result (e.g. COUNT = 0) is not detected |
| Answer + numeric verification | One-sentence answer in the question's language with only grounded numbers | LLM writes; verifier checks numbers with tolerance and unit conversions; template fallback | on | Does not check which entity a number belongs to; years exempt |

## C. Data features (`src/ingestion/`, `src/normalization/`)

| Feature | Detail | Evidence |
|---|---|---|
| Crawler | Sequential, 0.5 s delay, gzip cache per response, resumable | 5,299 requests, 0 failures, ≈80 min |
| Flattening | Every scalar leaf → long table | 6,217,844 rows, 235 field paths |
| Fresh-water accounting | Missing saline key stored as 0 (NULL produced a wrong 128 BCM total) | `docs/DATA_ACCESS_REPORT.md` §9 |
| Cross-year crosswalk | UUID → name in district → name in state → guarded fuzzy (mutual best ≥ 0.75, no split/ordinal changes) | 37/40 fuzzy links correct on hand review |
| Granularity table | Unit type and count per state and year, to block incomparable cross-year questions | `state_unit_granularity`, 187 rows |
| Reconciliation test | National totals vs PIB releases | ≤ 0.07% difference, `tests/test_db_against_published.py` |

## D. Evaluation and research features

| Feature | Where | Notes |
|---|---|---|
| INGRES-Bench v1 | `data/benchmark/`, `src/benchmark/` | 371 items × 4 languages; QC 0 failures; slot checker catches 97.1% of corruptions |
| Execution accuracy | `src/evaluation/execution.py:67` | Multiset, order-aware, tolerance 1e-6 |
| Bootstrap CIs, McNemar tests | `src/evaluation/report.py:34`, `scripts/run_pipeline.py: mcnemar` | 2,000 resamples, seed 0 |
| Error taxonomy | `scripts/run_pipeline.py: error_category` | Now based on the predicted SQL (fixes the baseline over-count) |
| Leave-own-intent-out evaluation | `--config v3_loio` | Hides TRAIN examples of the question's own type |
| Tokenizer study | `src/tokenization/`, `scripts/run_tokenization_study.py` | 5 tokenizers, CMI, placebo control |
| Model forensics | `scripts/model_forensics.py` | Exact parameter counts from tensors / GGUF |
| Performance benchmark | `scripts/benchmark_perf.py` | Components, LLM serving (TTFT, tokens/s, VRAM), end-to-end |

## E. Engineering features

| Feature | Detail |
|---|---|
| LLM response cache | SHA-256 of model + messages + options; location overridable with `INGRES_LLM_CACHE` (Nov 2026) |
| Alias-embedding cache | `cache/alias_emb/<hash>.npy`; hash of the alias list, so a changed gazetteer invalidates it |
| Explicit Ollama HTTP errors | HTTP 4xx/5xx raised immediately with the server message (was: retried 5× then "not reachable") |
| Reproducibility | Seeds everywhere, fixed model ID, frozen baseline tag `baseline-v1`, environment recorded in every perf result |
| Security | Read-only executor; secrets only in git-ignored `.env`; nothing sent off the machine with the Ollama backend |

## F. Implemented but not used / not evaluated

| Item | Status |
|---|---|
| Gemini client (`GeminiClient`) | Works; 1 successful evaluation call (free-tier quota 20/day) |
| Vocabulary-adapted encoder | Evaluated, rejected (no gain) |
| Translate-first | Evaluated, rejected (−1.8 points) |
| `add_history_aliases` | Defined, not wired into the live gazetteer |
| Level hints ("block", "ज़िला") for place resolution | Not implemented |
