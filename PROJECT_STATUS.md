# Project status

_Last updated: 2026-09-28_

| Phase | State | Evidence |
|---|---|---|
| 1. Data-access audit + ingestion | **Done, validated** | `docs/DATA_ACCESS_REPORT.md`, `reports/data_audit.json` |
| 2. Schema extraction + canonical DB | **Done, validated** | `data/processed/ingres.db`, `docs/INGRES_SCHEMA.md`, `tests/test_db_against_published.py` |
| 3. INGRES-Bench | Next | — |
| 4. Baselines (keyword, BM25, embeddings, frontier LLM) | Not started | — |
| 5. Learned schema linking | Not started | — |
| 6. Geographic entity resolution | Not started (raw material collected: 445 real respellings, 169 names shared across states, HP district codes) | `reports/crosswalk_renames.csv` |
| 7. Tokenizer / code-mixing study | Not started | — |
| 8. Numeric grounding verifier | Not started | — |
| 9. Agentic decomposition | Not started | — |
| 10. Minimal UI | Not started | — |
| 11. Ablations, error analysis, final docs | Not started | — |

## Environment (inspected 2026-09-28)
- Windows 11, Python 3.12.10, git 2.52, GitHub CLI 2.101 (not authenticated; releases skipped at user's request)
- GPU: NVIDIA GeForce RTX 5060, 8 GB. **The installed torch 2.14.0 is a CPU build.** Training phases (5, 6, 7) need a
  CUDA build of torch that supports this GPU (Blackwell). Install before Phase 5.
- Installed: pandas 2.3.3, numpy 1.26.4, pyarrow 25.0.1, scikit-learn 1.9.1, transformers 4.57.6,
  sentence-transformers 3.1.0, pydantic 2.13, pytest 9.1.1.

## Phase 1-2 summary (what was actually done)
- Found the INGRES public JSON endpoint by reading the portal's JS bundle (the endpoint is undocumented).
- Crawled 7 cycle labels: 5,299 responses, 0 failures. Included 5 complete cycles (GWRA 2020, 2022-2025);
  excluded 2016-17 (incomplete, totals inconsistent) and 2025-26 (in progress).
- National totals from the DB match the PIB-published figures within 0.1% for GWRA 2022, 2023, 2024 and 2025 (tested).
- Built the cross-year crosswalk, because INGRES re-issues unit UUIDs for some states; hand-reviewed fuzzy-link precision
  is 37/40.
- Recorded that assessment-unit granularity changed in 10+ states (the `state_unit_granularity` table).
- Read-only SQL executor (SQLite authorizer + `mode=ro`) with 13 injection/write-attempt tests.
- Tests: 37 passing (`python -m pytest`).

## Commands executed
```bash
python scripts/crawl_ingres.py --years 2024-2025 2023-2024 2022-2023 2021-2022 2019-2020 2016-2017 2025-2026
python scripts/audit_data.py
python scripts/build_schema.py
python scripts/snapshot_raw.py pack && python scripts/snapshot_raw.py restore dist/ingres_raw_2026-09-28.tar
python -m pytest
```

## Unresolved issues
1. GWRA 2020 national figures: only extraction (≈245 BCM) was verified against a primary source.
2. ~1.5% of districts per year: units do not sum to the reported district value (max rel. diff 0.85); cause unknown.
3. Semantics of `pipeline` / `sewage` recharge, domestic allocation and rainfall averaging are inferred from names (marked UNCERTAIN).
4. Two doubtful fuzzy crosswalk links remain (see report §8); others in `reports/crosswalk_renames.csv` have not all been reviewed.
5. The raw snapshot (139 MB) exists locally in `dist/` only; it is not in git or a release.
6. Sub-unit levels (villages, firkas 2022+, watersheds) are not crawled.
7. torch is a CPU-only build (see Environment).

## Hypotheses to test later (not results)
Code-mixing reduces schema-linking accuracy; romanization raises tokenizer fertility; ambiguous place names
(e.g. `ramnagar` ×10 units across states) cause disproportionate failures; learned schema linking beats lexical
baselines; entity resolution improves execution accuracy; numeric grounding reduces unsupported numbers; agentic
decomposition helps only on a hard subset and costs more on simple queries.

## Next phase: INGRES-Bench (Phase 3)
Plan to confirm before building:
- Question sources: real schema, real entities; cross-year questions **restricted to state/year pairs with unchanged
  granularity** and carrying the comparability caveat.
- Gold SQL is executed through `src/utils/safe_sql.py`; gold results are stored; a QC script re-executes every item.
- Multilingual versions: English is the canonical text. Hindi / Hinglish / Dravidian versions need a translation protocol
  that preserves SQL semantics. **A decision is needed on which Dravidian language (Tamil / Telugu / Kannada / Malayalam) and
  who validates the translations**, because machine translation alone does not meet the benchmark requirement.
