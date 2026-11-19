# INGRES — Benchmarks and Performance

Before = git tag `baseline-v1` (frozen original system, run from a separate worktree). After = `main` (pipeline v3).
Both were measured on the same machine, in the same session, one after the other, with no other GPU workload.

## 1. Test environment

| Item | Value |
|---|---|
| CPU | AMD Ryzen 7 9700X, 8 cores / 16 threads |
| RAM | 32 GB |
| GPU | NVIDIA GeForce RTX 5060, 8,151 MiB VRAM, driver 621.24 |
| OS | Windows 11 Pro 10.0.26200 |
| Python / PyTorch | 3.12.10 / 2.14.0+cpu (encoders run on CPU, 16 threads) |
| transformers / sentence-transformers | 4.57.6 / 3.1.0 |
| LLM runtime | Ollama 0.35.1, `qwen3:8b` (ID `500a1f067a9f`, Q4_K_M), `num_ctx` 8192, temperature 0, seed 0, thinking off |
| Encoders | `multilingual-e5-small` float32 (fine-tuned + base) |

## 2. Method (`scripts/benchmark_perf.py`)

| Stage | What is timed | Questions | Warm-up | Notes |
|---|---|---|---|---|
| `components` | query encoding, schema ranking, place linking, example retrieval (CPU); model loading; RSS | 200 TEST (50 per language) | 5 DEV questions | batch size 1, one request at a time |
| `llm` | one LLM request with the exact pipeline prompt, streamed (TTFT), plus Ollama's token counters | 100 TEST (25 per language) | 5 DEV prompts | response cache bypassed; cold start measured after unloading the model |
| `e2e` | `Pipeline.sql` wall clock (encode → link → prompt → LLM → snap → execute → repair) | 100 TEST | 5 DEV | response cache bypassed (empty temporary directory) |

Statistics: mean, median, p90, p95, p99 and standard deviation over the measured requests; throughput = requests ÷
summed wall time (serial, concurrency 1). Memory: Windows working set (current and peak) of the Python process.
VRAM: `nvidia-smi` before and after. Formulas used below: latency reduction = (old − new) / old × 100.

## 3. Results

### Components (CPU, 200 TEST questions, 5 warm-up, batch 1)

| Measure | baseline-v1 | optimized | change |
|---|---|---|---|
| Query encoding — mean | 8.50 ms | 8.58 ms | +0.9% (slower) |
| Query encoding — median | 8.48 ms | 8.48 ms | ≈0% |
| Query encoding — p95 | 9.79 ms | 10.15 ms | +3.7% (slower) |
| Query encoding — p99 | 11.10 ms | 10.99 ms | −1.0% |
| Place linking — mean | 107.16 ms | 39.18 ms | −63.4% |
| Place linking — median | 104.81 ms | 37.46 ms | −64.3% |
| Place linking — p95 | 192.41 ms | 70.59 ms | −63.3% |
| Place linking — p99 | 219.26 ms | 81.41 ms | −62.9% |
| Schema ranking — mean | 0.06 ms | 0.06 ms | ≈0% |
| Schema ranking — median | 0.06 ms | 0.05 ms | −16.7% |
| Schema ranking — p95 | 0.07 ms | 0.07 ms | ≈0% |
| Schema ranking — p99 | 0.08 ms | 0.08 ms | ≈0% |
| Example retrieval — mean | 0.06 ms | 0.05 ms | −16.7% |
| Example retrieval — median | 0.06 ms | 0.05 ms | −16.7% |
| Example retrieval — p95 | 0.07 ms | 0.06 ms | −14.3% |
| Example retrieval — p99 | 0.09 ms | 0.08 ms | −11.1% |
| **Total before the LLM** — mean | 115.78 ms | 47.87 ms | −58.7% |
| **Total before the LLM** — median | 113.22 ms | 45.88 ms | −59.5% |
| **Total before the LLM** — p95 | 202.77 ms | 80.41 ms | −60.3% |
| **Total before the LLM** — p99 | 229.06 ms | 91.37 ms | −60.1% |
| Throughput before the LLM (questions/s, 1 thread of requests) | 8.64 | 20.89 | +142% |

### Cold start (seconds)

| Stage | baseline-v1 | optimized, first start (no alias cache) | optimized (alias cache present) |
|---|---|---|---|
| load_finetuned_encoder_s | 0.48 | 0.41 | 0.41 |
| load_base_encoder_s | 4.5 | 4.65 | 4.62 |
| build_place_linker_s | 14.27 | 14.35 | 0.34 |
| build_pipeline_index_s | 2.88 | 2.87 | 2.88 |
| cold_start_total_s | 22.13 | 22.28 | 8.25 |
| RSS after load (MB) | 1295.1 | 1305.9 | 1182.2 |
| Peak RSS (MB) | 1377.6 | 1388.3 | 1322.2 |

### By language — place linking mean (ms)

| Language | baseline-v1 | optimized |
|---|---|---|
| english | 119.1 | 42.12 |
| hindi | 110.94 | 39.27 |
| hinglish | 83.41 | 30.38 |
| tamil | 115.2 | 44.95 |

### Encoder batch scaling (queries/s)

| Batch | baseline-v1 | optimized |
|---|---|---|
| 1 | 140.8 | 143.6 |
| 8 | 287.8 | 288.7 |
| 32 | 297.5 | 299.4 |
| 64 | 274.3 | 288.3 |

### LLM serving (qwen3:8b, RTX 5060, 100 TEST prompts, cache bypassed, streaming)

| Measure | baseline-v1 prompt | v3 prompt |
|---|---|---|
| request wall — mean | 2,198 ms | 2,182 ms |
| request wall — median | 2,009 ms | 2,010 ms |
| request wall — p90 | 2,783 ms | 2,739 ms |
| request wall — p95 | 3,314 ms | 3,279 ms |
| request wall — p99 | 3,781 ms | 3,847 ms |
| time to first token — mean | 289 ms | 293 ms |
| time to first token — median | 281 ms | 285 ms |
| time to first token — p90 | 395 ms | 402 ms |
| time to first token — p95 | 411 ms | 438 ms |
| time to first token — p99 | 444 ms | 452 ms |
| prompt_tokens_mean | 2,343.7 | 2,348.6 |
| output_tokens_mean | 98.7 | 97.8 |
| generation_tokens_per_s | 51.7 | 51.8 |
| prompt_eval_tokens_per_s | 8,762.3 | 8,697.1 |
| requests/s (serial) | 0.45 | 0.46 |
| cold start: model load / first request wall | 3.04 s / 5.77 s | 1.79 s / 4.54 s |
| VRAM in use after run (MiB of 8151) | 7459 | 7459 |

### End to end (`Pipeline.sql`, 100 TEST questions, LLM cache bypassed)

| Measure | baseline-v1 | v3 | change |
|---|---|---|---|
| wall — mean | 2,289.94 ms | 2,303.47 ms | +0.6% (slower) |
| wall — median | 2,084.73 ms | 2,094.78 ms | ≈0% |
| wall — p90 | 2,974.53 ms | 2,890.90 ms | −2.8% |
| wall — p95 | 3,467.73 ms | 3,432.75 ms | −1.0% |
| wall — p99 | 3,840.43 ms | 3,906.11 ms | +1.7% (slower) |
| non-LLM overhead — mean | 120.91 ms | 54.38 ms | −55.0% |
| non-LLM overhead — median | 119.80 ms | 52.05 ms | −56.6% |
| non-LLM overhead — p95 | 198.32 ms | 79.27 ms | −60.0% |
| LLM share of wall time | 94.7% | 97.6% | |
| mean LLM calls per question | 1.0 | 1.0 | |
| questions/s (serial) | 0.44 | 0.43 | |

| Language | baseline-v1 median | v3 median |
|---|---|---|
| english | 2,071 ms | 2,050 ms |
| hindi | 2,097 ms | 2,129 ms |
| hinglish | 2,017 ms | 2,038 ms |
| tamil | 2,200 ms | 2,259 ms |

<!-- baseline_components: commit 79ec245 dirty=False 2026-11-19T13:23:37Z gpu=7490 MiB 7% -->

<!-- optimized_components: commit 6c37a9f dirty=True 2026-11-19T13:34:07Z gpu=7460 MiB 7% -->

<!-- baseline_llm: commit 79ec245 dirty=False 2026-11-19T13:28:22Z gpu=7459 MiB 51% -->

<!-- optimized_llm: commit 6c37a9f dirty=True 2026-11-19T13:38:27Z gpu=7459 MiB 97% -->

<!-- baseline_e2e: commit 79ec245 dirty=False 2026-11-19T13:32:55Z gpu=7459 MiB 98% -->

<!-- optimized_e2e: commit 6c37a9f dirty=True 2026-11-19T13:42:48Z gpu=7458 MiB 97% -->

## 4. Interpretation

- **End-to-end latency did not improve.** `Pipeline.sql` median 2,085 → 2,095 ms (≈0%), mean +0.6%, p90 −2.8%, p99 +1.7%:
  all within run-to-run noise. The LLM is 97.6% of end-to-end time in v3, so CPU-side savings of ≈66 ms per question
  hardly show.
- **The LLM dominates.** Generation runs at ≈51.8 tokens/s with ≈98 output tokens per SQL, so ≈1.9 s of generation per
  request. Prompt processing is ≈8,697 tokens/s for ≈2.35k prompt tokens, about 0.27 s. Shorter outputs, not shorter
  prompts, are the lever for latency.
- **Pre-LLM work** fell from 116 ms to 48 ms per question (−58.7%; place linking −63.4%), because place linking now embeds
  all spans of a question in one batch. Pre-LLM throughput rose from 8.6 to 20.9 questions/s (+142%). This matters for
  the CPU load of a multi-user deployment, not for single-user latency.
- **Cold start** fell from 22.1 s to 8.3 s (−62.7%) when the alias cache exists. The first start without the cache is
  unchanged (22.3 s), because it computes and stores the 16,681 alias embeddings.
- **Memory**: RSS after loading fell from 1,295 MB to 1,182 MB (−8.7%), and peak from 1,378 to 1,322 MB, because the alias
  matrix is read from disk instead of computed with a batch encode. The two float32 encoders (≈941 MB) remain the bulk.
- **The v3 prompt** is 2,349 tokens on average vs 2,344 for the original prompt (+0.2%). The year hint and definitions
  are a few dozen tokens, offset by fewer place-hint lines. The LLM request time is unchanged (median 2,010 vs 2,009 ms).
- **GPU speed varies between sessions.** On 2026-11-17 the same model generated 66.7 tokens/s; on 2026-11-19 it
  generated 51.7–51.8 tokens/s, on the same GPU and driver; other processes (desktop compositor, wallpaper engine) held ≈1.4 GB of the 7.46 GB in use. Before and
  after were therefore measured back to back in one session; absolute LLM latencies should be read with this ±25% caveat.

## 5. Accuracy benchmarks
Execution accuracy and ablations: `docs/PIPELINE.md` §0 and `INGRES_COMPLETE_TECHNICAL_DEEP_DIVE.md` §12.

| System | TEST (384) | HARD_TEST (260) |
|---|---|---|
| Original pipeline (re-run, same environment) | 72.1% | 58.8% |
| Improved pipeline v3 | **81.3%** [77.3, 85.2] | **70.4%** [65.0, 75.8] |

Paired (test): 51 wins / 16 losses, McNemar p = 2e-05.

## 6. Not measured

| Item | What would be needed |
|---|---|
| Throughput at concurrency > 1 | `OLLAMA_NUM_PARALLEL` > 1 and a load generator; VRAM for extra KV caches |
| Accuracy cost of 4-bit quantisation | The F16 model (≈16 GB) does not fit in 8 GB VRAM |
| GPU encoders / ONNX / int8 encoders | Encoders take ≈1% of request time; not worth the GPU memory the LLM needs |
| API cost per request | No paid API used (local inference: electricity only) |
