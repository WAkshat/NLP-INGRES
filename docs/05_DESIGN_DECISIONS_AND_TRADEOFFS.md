# INGRES — Architecture Decision Records

Each record states what was chosen, the alternatives, why it was chosen, and the evidence. "Original rationale" is what the
project docs recorded at the time. "Verified" means a measurement in this repository supports the decision. Numbers are
EX on INGRES-Bench unless stated.

| # | Decision | Status |
|---|---|---|
| ADR-01 | Text-to-SQL over a local SQLite copy, not a chatbot over documents | Accepted (original) |
| ADR-02 | Crawl the portal's public JSON endpoint | Accepted (original) |
| ADR-03 | Read-only executor enforced by the SQLite authorizer | Accepted (original), tested |
| ADR-04 | Execution accuracy as the primary metric | Accepted (original) |
| ADR-05 | Local qwen3:8b instead of a frontier API | Accepted (constraint), trade-off acknowledged |
| ADR-06 | Small fine-tuned bi-encoder for schema linking | Accepted, verified |
| ADR-07 | Feature-based LR ranker for place names, not a neural model | Accepted, verified |
| ADR-08 | Retrieved examples in the prompt | Accepted, verified (largest single gain) |
| ADR-09 | Execution-guided repair, max 2 turns | Accepted, small gain |
| ADR-10 | Deterministic numeric verifier with template fallback | Accepted, verified |
| ADR-11 | Translate-first rejected | Rejected, verified |
| ADR-12 | Vocabulary adaptation rejected | Rejected, verified |
| ADR-13 | Custom Tamil romaniser + voicing-neutral matching | Accepted (Nov 2026), verified |
| ADR-14 | Deterministic year rule as a prompt hint | Accepted (Nov 2026), verified on dev |
| ADR-15 | Value snapping of place literals after generation | Accepted (Nov 2026), verified on dev |
| ADR-16 | Metric definitions in a pipeline-only prompt note | Accepted (Nov 2026), verified on dev |
| ADR-17 | Batched span embeddings + on-disk alias cache | Accepted (Nov 2026), measured |
| ADR-18 | Streamlit for the UI | Accepted |
| ADR-19 | Not adopted: ONNX/quantised encoders, GPU encoders, cross-encoder reranking, LoRA on the LLM | Deferred |

---

### ADR-01 Text-to-SQL over SQLite
- **Context.** Questions are about specific numbers in a structured, official table (recharge, extraction, categories by unit and year).
- **Decision.** Translate each question into one SQL query over a canonical SQLite database. Answers are computed by the database, not generated.
- **Alternatives.** RAG over PDF reports (numbers would be paraphrased and unverifiable); a chatbot fine-tuned on the data (cannot aggregate reliably); hand-written intent templates (cannot cover compositional questions).
- **Why.** Aggregations, comparisons and cross-year joins are exact in SQL, and every answer can be shown with its query.
- **Trade-off.** The LLM must learn the schema and conventions. That is the source of most errors (wrong year, wrong column, wrong place spelling).

### ADR-02 Crawl the public JSON endpoint
- **Original rationale.** No public API or bulk download exists (Excel export is admin-only); PDFs would need table extraction. The portal's own unauthenticated endpoint returns structured JSON.
- **Verified.** National totals match published PIB figures within 0.07% for 4 cycles (`tests/test_db_against_published.py`).
- **Trade-off.** The endpoint is undocumented and may change. Mitigated by a raw snapshot with a SHA-256 manifest (local only).

### ADR-03 Read-only executor
- **Decision.** `mode=ro` URI + `set_authorizer` allow-list (SELECT, READ, FUNCTION, RECURSIVE) + denied functions + 10 s progress-handler timeout + 10,000-row cap (`src/utils/safe_sql.py`).
- **Why not string filtering?** Keyword blocklists miss `ATTACH`, `PRAGMA`, `load_extension`, comments and encoded variants. The authorizer is enforced inside SQLite at statement-compile time.
- **Evidence.** 13 tests in `tests/test_safe_sql.py` (writes, ATTACH, PRAGMA, multiple statements, extension loading).

### ADR-04 Execution accuracy (EX)
- **Why.** Many SQL strings are correct for one question; comparing results is the Spider/BIRD standard. Exact-match SQL would undercount (the keyword baseline: 35.6% exact match vs 38.8% EX).
- **Settings.** Multiset comparison, order-sensitive only with ORDER BY, numeric tolerance 1e-6 relative, column count must match.
- **Trade-off.** Strict on output shape: a correct answer with one extra column counts as wrong (5 of 38 dev errors for v2).

### ADR-05 Local qwen3:8b
- **Original rationale.** The Gemini free tier allowed 20 requests per day (logged); one evaluation pass is 872 requests. A local model is free, private and reproducible.
- **Model choice.** Dev pilot of 24 questions: qwen3:8b 8/24, qwen2.5-coder:7b 3/24.
- **Measured cost.** 8,190,735,360 parameters, Q4_K_M, 6.2 GB VRAM with an 8,192-token context; 51.7 generated tokens/s, median request 2.01 s, time to first token 281 ms (`experiments/perf/baseline_llm.json`, 2026-11-19; 66.7 tokens/s in an earlier session on 2026-11-17).
- **Trade-off.** 8 GB of VRAM caps the model size. The frontier-model upper bound is NOT MEASURED.
- **Finding (Nov 2026).** Re-installing the same model ID with a newer GPU driver reproduced 24 of 39 cached answers exactly; two runs in one environment matched 39/39. Temperature-0 GPU generation is deterministic within an environment, not across driver versions. All before/after comparisons are therefore made within one environment.

### ADR-06 Fine-tuned multilingual-e5-small for schema linking
- **Alternatives measured.** BM25 R@3 0.267 (0.009 on Hindi and Tamil script); off-the-shelf e5-small 0.409.
- **Decision.** Contrastive fine-tuning with hard negatives (similar columns; the same column at another administrative level).
- **Verified.** R@3 0.896 overall; 0.851 on question types removed from training (3 seeds); +5.2 EX when its top-5 columns are added to the zero-shot prompt (McNemar p = 0.008).
- **Why small?** 117.65 M parameters, 8.8 ms per question on CPU, trains in 386 s on CPU. A larger encoder is not justified while linking is not the bottleneck: after v3, wrong-column errors are 3 of 18 dev errors.

### ADR-07 LR ranker for place names
- **Why not end-to-end neural?** No labelled data of misspelled Indian place names exists. 12 interpretable features train in minutes on synthetic noise, and the weights can be read (edit ratio +18.9, embedding +13.8, state conflict −14.9).
- **Verified.** Ambiguous names 0.447 → 0.973 top-1 with hierarchy context.

### ADR-08 Retrieved examples
- **Verified.** Removing them costs 36.5 points on test (baseline-v1: 71.9 → 35.4, p = 2e-30).
- **Trade-off / caveat.** Test question types also occur in training. The leave-own-intent-out run (`v3_loio`) measures how much survives on unseen types; see `docs/PIPELINE.md`.

### ADR-09 Execution-guided repair
- **Verified.** +1.6 points on test in baseline-v1 (6 fixed, 0 broken). On dev v3, first-attempt EX equals final EX (0.921): value snapping now prevents most failures the repair loop used to see.
- **Cost.** Mean 0.05–0.2 extra LLM calls per question.

### ADR-10 Numeric verifier
- **Verified.** 98.1% of 215 planted numeric errors caught, 0% false alarms on 384 template answers and unit conversions; the 2 real hallucinations in 242 LLM answers were both caught (`experiments/grounding/results.json`).
- **Trade-off.** Checks that a number exists in the result, not that it is attached to the right entity.

### ADR-11 Translate-first (rejected)
- **Measured.** 16.4% vs 18.2% direct (n = 872; 30 wins / 46 losses, p = 0.08). The 8B model mistranslated domain terms (अति-दोहित "over-exploited" → "extremely undernourished").

### ADR-12 Vocabulary adaptation (rejected)
- **Measured.** Tamil fragmentation 0.63 → 0.43, but R@3 0.896 → 0.897 and EX with hints unchanged (0.232 → 0.232).

### ADR-13 Tamil romaniser + voicing-neutral matching (Nov 2026)
- **Problem.** The library's TAMIL→ISO scheme mapped க to "gha": கர்நாடகா → "gharnadhagha".
- **Alternatives.** A different transliteration library (none installed; would add a dependency); learning a character model (no labelled data); adding Tamil-script aliases to the gazetteer (needs 9,558 hand renderings).
- **Decision.** A 30-line deterministic romaniser + a second "devoiced" TF-IDF space chosen per mention.
- **Verified.** Hand-written Tamil top-1 0.568 → 0.806 (128 fixed / 5 broken); place-linker dev F1 0.852 → 0.905; dev EX of the otherwise unchanged pipeline (config `full`, no other change) 0.772.
- **Trade-off.** Devoicing merges some distinct names (k/g pairs); the LR ranker and context features handle the resulting ties.

### ADR-14 Year rule (Nov 2026)
- **Problem.** "The 2025 assessment" means the cycle `2024-2025`; the LLM applied this wrongly in 55 of 644 baseline test/hard queries.
- **Decision.** Regex rule over 4 languages and 2 digit scripts (`src/pipeline/years.py`), written against TRAIN + DEV only (accuracy 100% on both), passed as a hint.
- **Why a hint, not a rewrite?** The LLM still writes the query; rewriting years in the SQL would break questions comparing two years.
- **Verified on dev.** full 0.772 → v2 0.833 (18 wins / 4 losses, p = 0.004).

### ADR-15 Value snapping (Nov 2026)
- **Problem.** The model rewrites exact spellings it was given ('Mahabubabad' → 'MAHABUBABAD'). SQLite `=` is case-sensitive, and a COUNT over zero rows returns 0, so the repair loop never fires. 196 unit names exist in two casings.
- **Alternatives.** Always compare case-insensitively (changes semantics for the 196 case-variant pairs); ask the LLM again (costs a call, same failure mode).
- **Decision.** Deterministic post-processing of `=`, `IN (...)` and `UPPER(col) = UPPER('...')` comparisons on the three name columns; unknown names are replaced only when folded similarity ≥ 0.80 and clearly better than the runner-up.
- **Verified.** Offline replay on v2 dev outputs: 14 queries changed, 12 errors fixed, 0 correct answers broken. Live (v3 with definitions): see ADR-16.

### ADR-16 Metric definitions (Nov 2026)
- **Problem.** 9 of 38 v2 dev errors answered "what share of extraction was for irrigation" with `stage_of_extraction_pct`.
- **Decision.** A two-sentence definition note added by the pipeline only. Kept out of the shared `CONVENTIONS` string so earlier experiments keep byte-identical prompts.
- **Verified on dev (together with ADR-15).** v2 0.833 → v3 0.921 (23 wins / 3 losses, p = 9e-5). Test: `docs/PIPELINE.md`.

### ADR-17 Batched span embeddings + alias cache (Nov 2026)
- **Problem.** Place linking embedded each span separately (one transformer call per span) and re-embedded 16,681 aliases at every start-up.
- **Decision.** One batched `encode` per question; alias matrix cached on disk under a hash of the alias list.
- **Measured.** `docs/04_BENCHMARKS_AND_PERFORMANCE.md`.

### ADR-18 Streamlit UI
- **Alternatives.** FastAPI + React (more work, no benefit for a single-user demo); Gradio (comparable).
- **Why.** Already a dependency; chat components, Altair charts and data tables are built in; one Python file (`app/streamlit_app.py`).

### ADR-19 Deferred optimizations
| Candidate | Why deferred |
|---|---|
| ONNX Runtime / int8 for the encoders | Encoders take ≈9 ms of a ≈2 s request; at most 0.5% end-to-end gain |
| GPU for the encoders | The 8 GB GPU is fully used by the LLM (≈7.3 GB in use during runs) |
| Cross-encoder reranking for schema linking | Wrong-column errors are 3 of 18 v3 dev errors |
| LoRA fine-tuning of qwen3:8b on TRAIN SQL | Would need a CUDA PyTorch build and ≥ 8 GB of free VRAM for 4-bit QLoRA; only 612 training questions. Highest-potential next step for unseen question types |
| Larger LLM (14B+) | Does not fit in 8 GB VRAM at usable speed |
| Self-consistency (several samples + vote) | Multiplies the dominant cost (LLM time) by the number of samples |
