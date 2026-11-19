# INGRES — Future Research Roadmap

Ordered by expected value per unit of effort. Each item has a measurable success criterion. Effort estimates are
estimates, not measurements.

| # | Direction | Why (evidence) | Approach | Effort / resources | Success criterion |
|---|---|---|---|---|---|
| 1 | **Generalisation to unseen question types** | v3 scores 81.3% on TEST but **51.0%** when TRAIN examples of the question's own type are hidden (`v3_loio`; 123 lost / 7 gained, p = 2e-28). Multi-hop drops to 8.3%, cross-year to 38.3%. Simply showing 6 examples instead of 3 did not help significantly (DEV 55.7 → 59.2%, p = 0.12) | (a) Add hand-written examples covering SQL *patterns* (self-join across years, CTE with aggregates, ratio of two columns) rather than question types; (b) a held-out-intent benchmark split | 1–2 days writing; GPU evaluation ≈ 20 min per run | `v3_loio` EX within 10 points of `v3` |
| 2 | **QLoRA fine-tuning of the LLM on TRAIN SQL** | The model makes systematic schema-convention errors that prompting fixes only partly | 4-bit QLoRA (rank 16) on 612 TRAIN pairs + augmented paraphrases; needs a CUDA build of PyTorch for the RTX 5060 and the LLM unloaded from Ollama while training | ≈ 1 day; 8 GB VRAM is tight for 8B (may need a 4B model) | +5 points on `v3_loio`, no loss on test |
| 3 | **Native-speaker validation** | Hindi/Hinglish/Tamil text was generated, not checked by native speakers | Review a stratified sample of 100 instances per language; report error rate with CI | Half a day per language | ≥ 95% of sampled questions judged natural and faithful |
| 4 | **Frontier-model upper bound** | Unknown how much remaining error is due to the 8B model | Run the v3 prompt with a paid API on TEST (384 calls) | A few US dollars; ≈ 30 min | Gap between 8B and frontier quantified with a paired test |
| 5 | **Level-aware unit-name resolution** | 37 of v3's 149 TEST+HARD errors lack a gold place in the SQL; 32 of them are unit (block/taluk) names, and the linker missed the place in 34 of 37. Linker found all gold places in 79.2% of TEST questions | Use level words in the question ("block", "ज़िला", "மாவட்டம்") as a resolver feature | ≈ 0.5 day; retrain the ranker | Place-linker DEV F1 ≥ 0.93; Tamil recall ≥ 0.80 |
| 6 | **Output-shape control** | 24 of v3's 149 errors return extra columns (the right rows with more columns than asked) | Post-check: if the question is a "which/list" question and the result has more columns than names, re-ask once | ≈ 0.5 day | Fewer "other" errors on DEV without new breaks |
| 7 | **Streaming answers in the UI** | Median 2.0 s per LLM request; time to first token ≈ 0.28 s | Stream the answer sentence; show the SQL as soon as it exists | ≈ 0.5 day | Perceived latency below 0.5 s |
| 8 | **Multi-user serving** | The app is single-user; Ollama serves one request at a time by default | FastAPI wrapper + Ollama `OLLAMA_NUM_PARALLEL`; measure throughput vs VRAM | ≈ 1 day | Throughput and p95 latency measured at concurrency 1, 2, 4 |
| 9 | **More seeds** | Schema linker and ranker trained with one seed | Retrain with 3–5 seeds | ≈ 1 h CPU | Report mean ± sd for R@3 and resolver top-1 |
| 10 | **Year rule as SQL validation** | The year rule is only a hint; 15 of 644 v3 TEST+HARD queries still have a wrong year set (12 counted as year errors) | Validate that the SQL year set equals the rule's set when the rule fires; repair otherwise | ≈ 0.5 day | Wrong-year errors on DEV → 0 |

## Deferred, with reasons

| Idea | Reason it is not prioritised |
|---|---|
| ONNX / int8 encoders | Encoders are ≈ 9 ms of a ≈ 2 s request |
| Cross-encoder reranker for schema linking | Wrong-column errors are a minority after v3 |
| Self-consistency voting | Multiplies the dominant LLM cost |
| A bigger LLM | Does not fit in 8 GB VRAM at usable speed |
