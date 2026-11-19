# INGRES — Reproducibility Guide

Everything below was run on the machine described in §1. Commands are run from the repository root.

## 1. Reference environment

| Item | Value |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| CPU / RAM | AMD Ryzen 7 9700X (8 cores / 16 threads) / 32 GB |
| GPU | NVIDIA GeForce RTX 5060, 8 GB VRAM, driver 621.24 (617.14 for the October runs) |
| Python | 3.12.10 |
| LLM runtime | Ollama **0.35.1**, model `qwen3:8b`, ID `500a1f067a9f` |
| Key packages | torch 2.14.0+cpu, transformers 4.57.6, sentence-transformers 3.1.0, tokenizers 0.22.2, scikit-learn 1.9.1, scipy 1.17.1, pandas 2.3.3, numpy 2.5.3, indic_transliteration 2.3.69, streamlit 1.38.0, pytest 9.1.1 |

`requirements.txt` lists the pins. Note: it pins `numpy==1.26.4`, which was the October environment; the November runs
used numpy 2.5.3 and all tests pass under both.

## 2. Setup

```bash
pip install -r requirements.txt
winget install --id Ollama.Ollama --version 0.35.1      # or the installer from ollama.com
ollama pull qwen3:8b
ollama list                                             # the ID must be 500a1f067a9f to reuse cached answers safely
```

## 3. Assets that are not in git

| Asset | Size | How to get it |
|---|---|---|
| `data/processed/ingres.db` | 21.8 MB | Rebuild (step 4) or copy from a teammate |
| `experiments/schema_linking/checkpoints/finetuned_e5/` | 466 MB | `python scripts/train_schema_linker.py` (≈6.5 min CPU) or copy |
| `experiments/tokenization/checkpoints/vocab_adapted_e5/` | 466 MB | `python scripts/run_tokenization_mitigation.py --stage vocab` (only for that experiment) |
| `cache/llm/` | 5,360+ JSON files | Optional. Without it every LLM call is recomputed (same answers at temperature 0 with the same model ID) |
| `cache/alias_emb/` | ≈30 MB | Created automatically on first start |
| `multilingual-e5-small` | 470 MB | Downloaded from Hugging Face on first use (revision `614241f6…`) |

`experiments/entity_resolution/ranker.pkl` **is** in git.

## 4. Data and benchmark

```bash
python scripts/crawl_ingres.py                      # ~80 min, resumable, polite (0.5 s between requests)
python scripts/audit_data.py                        # reports/data_audit.json
python scripts/build_schema.py                      # data/processed/ingres.db, data/schema/schema.json
python scripts/build_benchmark.py                   # data/benchmark/*.jsonl (seed 7, deterministic)
python scripts/qc_benchmark.py                      # reports/benchmark_qc.json
```
The benchmark files are in git, so steps 4–5 of this block are only needed to regenerate them.

## 5. Models

```bash
python scripts/train_schema_linker.py                           # fine-tune + evaluate the schema linker (seed 0)
python scripts/train_schema_linker.py --intent-holdout 0.25 --seed 1   # generalisation check
python scripts/train_entity_resolver.py                         # train + evaluate the entity ranker (seed 0, ~4 min)
python scripts/model_forensics.py                               # exact parameter counts -> experiments/forensics/models.json
```

## 6. Experiments

```bash
# baselines
python scripts/run_baselines.py --baseline A
python scripts/run_baselines.py --baseline D --backend ollama --model qwen3:8b
python scripts/run_schema_linking_baselines.py
# tokenization study and numeric grounding
python scripts/run_tokenization_study.py
python scripts/run_tokenization_mitigation.py --stage translate   # then: vocab, hints, summary
python scripts/run_grounding.py
# full pipeline (current code) -> experiments/pipeline_v2/
python scripts/run_pipeline.py --stage places
python scripts/run_pipeline.py --stage run --config v2 --splits dev
python scripts/run_pipeline.py --stage run --config v2 --splits test hard_test
python scripts/run_pipeline.py --stage run --config full --splits test hard_test     # current code, no year hints
python scripts/run_pipeline.py --stage run --config v2_loio --splits test            # own question type hidden
python scripts/run_pipeline.py --stage summary
```

## 7. Performance benchmarks

```bash
python scripts/benchmark_perf.py --label optimized --stage components        # CPU only
python scripts/benchmark_perf.py --label optimized --stage llm --n 100       # needs `ollama serve`
python scripts/benchmark_perf.py --label optimized --stage e2e --n 100
```
To reproduce the **baseline** numbers, check out the frozen original system and run the same script there:

```bash
git worktree add ../ingres_baseline baseline-v1
# copy data/processed/ingres.db and the finetuned_e5 checkpoint into the worktree, copy scripts/benchmark_perf.py, then:
cd ../ingres_baseline && python scripts/benchmark_perf.py --label baseline --stage components
```
Method: 5 warm-up requests on DEV questions, then the first 25 or 50 TEST questions per language; batch size 1; one
request at a time; wall-clock `time.perf_counter`; the LLM response cache is bypassed in the `llm` and `e2e` stages.
Run with no other heavy process on the machine: CPU contention changes the non-LLM timings.

## 8. Determinism

| Component | Source of randomness | Control |
|---|---|---|
| Benchmark build | sampling | seed 7 |
| Schema-linker training | shuffling, dropout, negatives | seed 0 (`torch.manual_seed`, `random.Random`) |
| Entity ranker | entity split, noise generation, LR solver | seed 0 |
| LLM | sampling | temperature 0, seed 0, fixed model ID, thinking off; responses cached by request hash |
| Bootstrap CIs | resampling | seed 0, 2,000 resamples |

Known limits: CPU floating-point results can differ in the last digits across BLAS builds; batched and single encodes
of the same text differ at ≈1e-7, which can flip a score sitting exactly on a threshold. GPU generation at temperature 0
was identical across the October and November installs for the requests that were replayed (same model ID).

## 9. Tests

```bash
python -m pytest            # 69 tests
```
`tests/test_db_against_published.py` needs `data/processed/ingres.db`.

## 10. UI

```bash
ollama serve
streamlit run app/streamlit_app.py        # http://localhost:8501
```
