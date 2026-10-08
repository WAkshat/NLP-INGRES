# INGRES-Text2SQL

Multilingual (English / Hindi / Hinglish / a Dravidian language) Text-to-SQL research over
India's official groundwater assessment data (**INGRES**, CGWB + IIT Hyderabad).

> Status: **Phases 1-8 done**; Phase 9 pipeline and Phase 10 UI built, Phase 9 evaluation pending.
> **Start here: [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md)**, which explains the problem, tech stack, workflow, code,
> all results and the remaining work. Status table: [`PROJECT_STATUS.md`](PROJECT_STATUS.md).

## 1. Problem
INGRES publishes block/mandal/taluk-level groundwater assessments (recharge, extraction,
stage of extraction, Safe / Semi-Critical / Critical / Over-Exploited categories) through a
map-based portal. Answering questions such as *"Ludhiana ke kitne blocks over-exploited hain?"*
or *"Which Punjab blocks moved from Critical to Over-Exploited between 2022 and 2025?"*
requires navigating that portal by hand.

## 2. Research question
How well can a natural-language interface translate Indian multilingual and code-mixed questions
into correct, executable SQL over the INGRES schema, and which components (schema linking,
geographic entity resolution, tokenizer adaptation, numeric grounding, agentic decomposition)
measurably improve **execution accuracy**? Hypotheses (to be tested, not assumed) are listed
in `PROJECT_STATUS.md`.

## 3. Dataset
Official INGRES data, crawled from the portal's public JSON endpoint and reconciled against the
published national reports. Details, caveats and all numbers: [`docs/DATA_ACCESS_REPORT.md`](docs/DATA_ACCESS_REPORT.md).
Schema: [`docs/INGRES_SCHEMA.md`](docs/INGRES_SCHEMA.md) / `data/schema/schema.json`.

## 4. INGRES-Bench
371 items × 4 languages (English, Hindi, Hinglish, Tamil) = 1,484 NL→SQL instances with executed gold results,
4 difficulty levels, train/dev/test/hard-test splits. Construction protocol, QC and limitations:
[`docs/INGRES_BENCH.md`](docs/INGRES_BENCH.md).

## 5. Baselines, schema linking, entity resolution
- Baselines (keyword/template EX 38.8%, local qwen3:8b zero-shot EX 18.2%, BM25 / embedding schema retrieval):
  [`docs/BASELINES.md`](docs/BASELINES.md)
- Learned schema linker (column recall@3 0.409 -> 0.896; 0.851 on unseen question types): [`docs/SCHEMA_LINKING.md`](docs/SCHEMA_LINKING.md)
- Geographic entity resolver (top-1 0.84-0.89 on noisy names, 0.45 -> 0.97 on ambiguous names with context):
  [`docs/ENTITY_RESOLUTION.md`](docs/ENTITY_RESOLUTION.md)

## 6-11. Tokenization study, numeric grounding, pipeline, UI
- Tokenization / code-mixing (Qwen3 fertility: English 2.04, Tamil 8.96; fragmentation does not explain accuracy;
  linker hints +5.2 EX): [`docs/TOKENIZATION.md`](docs/TOKENIZATION.md)
- Numeric grounding (LLM answers with unsupported numbers 0.83% → 0%; 98.1% of planted errors caught):
  [`docs/GROUNDING.md`](docs/GROUNDING.md)
- Full pipeline: `src/pipeline/agent.py` (evaluation: TODO — requires experiment). UI: `streamlit run app/streamlit_app.py`

## 12. Evaluation methodology
Primary metric: execution accuracy (Spider/BIRD style result-set comparison). TODO.

## 13. Results
TODO — requires experiment.

## 14. Limitations
See `docs/DATA_ACCESS_REPORT.md` §Limitations for data-level limitations.

## 15. Reproduction
```bash
pip install -r requirements.txt
python scripts/crawl_ingres.py      # ~12 min per assessment year, resumable; raw JSON -> data/raw/ingres_api/
python scripts/audit_data.py        # interim parquet + reports/data_audit.json
python scripts/build_schema.py      # data/processed/ingres.db + data/schema/schema.json + docs/INGRES_SCHEMA.md
python scripts/build_benchmark.py   # data/benchmark/*.jsonl (INGRES-Bench v1)
python scripts/qc_benchmark.py      # benchmark quality control
python scripts/run_baselines.py --baseline A
python scripts/run_baselines.py --baseline D --backend ollama --model qwen3:8b   # needs Ollama running
python scripts/run_schema_linking_baselines.py
python scripts/train_schema_linker.py
python scripts/train_entity_resolver.py
python -m pytest
```

## Repository layout
```
configs/            data.yaml (years, paths, crawl politeness)
src/ingestion/      INGRES API client/crawler, raw->interim flattening, canonical DB builder
src/normalization/  cross-year location crosswalk
src/utils/          read-only SQL executor (authorizer-enforced)
src/benchmark/      INGRES-Bench entity pool, lexicon, intents, builder
scripts/            crawl / audit / build entry points
data/raw|interim|processed|schema   (raw + interim + db are regenerable and git-ignored)
docs/  reports/  tests/
```
