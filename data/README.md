# Data directories

| dir | contents | in git? | produced by |
|---|---|---|---|
| `raw/ingres_api/<year>/` | verbatim gzipped INGRES API responses + request metadata | no (~13 MB/year, regenerable) | `scripts/crawl_ingres.py` |
| `interim/` | `locations.parquet`, `facts_long.parquet` (lossless flattening), `crawl.log` | no | `scripts/audit_data.py` |
| `processed/ingres.db` | canonical SQLite database | no (regenerable) | `scripts/build_schema.py` |
| `schema/schema.json` | machine-readable schema with descriptions + examples | yes | `scripts/build_schema.py` |
| `benchmark/` | INGRES-Bench (later phase) | yes | — |
