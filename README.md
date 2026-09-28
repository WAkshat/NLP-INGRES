# INGRES-Text2SQL

Multilingual (English / Hindi / Hinglish / a Dravidian language) Text-to-SQL research over
India's official groundwater assessment data (**INGRES**, CGWB + IIT Hyderabad).

> Status: **Phase 1-2 (data layer) done and validated**. See [`PROJECT_STATUS.md`](PROJECT_STATUS.md) for what is
> done, validated, and pending. No model results exist yet; every result slot below is
> `TODO — requires experiment` until the corresponding experiment has been run.

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

## 4-11. INGRES-Bench, architecture, components, baselines
TODO — later phases (benchmark, baselines, schema linking, entity resolution, tokenization study,
numeric grounding, agentic system).

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
python -m pytest
```

## Repository layout
```
configs/            data.yaml (years, paths, crawl politeness)
src/ingestion/      INGRES API client/crawler, raw->interim flattening, canonical DB builder
src/normalization/  cross-year location crosswalk
src/utils/          read-only SQL executor (authorizer-enforced)
scripts/            crawl / audit / build entry points
data/raw|interim|processed|schema   (raw + interim + db are regenerable and git-ignored)
docs/  reports/  tests/
```
