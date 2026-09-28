"""Build data/processed/ingres.db + data/schema/schema.json + docs/INGRES_SCHEMA.md.

Requires data/interim/*.parquet (python scripts/audit_data.py).
"""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ingestion.build_db import CATEGORIES, METRICS, build  # noqa: E402

UNCERTAIN = "UNCERTAIN"
TABLE_DOC = {
    "assessment_years": ("Assessment cycles available in INGRES. `assessment_year` is the portal label; "
                         "`gwra_year` is the year of the published national report (label 2023-2024 == GWRA 2024, "
                         "verified against PIB national totals).", "none", "one row per cycle"),
    "states": ("States and Union Territories as named in INGRES (UPPER CASE, INGRES spellings e.g. TAMILNADU, LAKSHDWEEP).",
               "state", "static (latest name)"),
    "districts": ("Districts as named in INGRES (case varies by state).", "district, child of state", "static (latest name/parent)"),
    "assessment_units": ("Groundwater assessment units (block / taluk / mandal / firka / tehsil / ...; see unit_type). "
                         "Names are NOT unique across the country.", "assessment unit, child of district", "static (latest name/parent)"),
    "state_assessments": ("Official state-level aggregates reported by INGRES for each cycle.", "state", "per assessment_year"),
    "district_assessments": ("Official district-level aggregates reported by INGRES for each cycle.", "district", "per assessment_year"),
    "unit_assessments": ("Assessment-unit results per cycle, incl. official category. district_id is the district the unit "
                         "was reported under in that cycle.", "assessment unit", "per assessment_year"),
    "location_crosswalk": ("Maps each year-specific INGRES UUID to the canonical cross-year id used in all other tables, "
                           "with how the match was made (uuid / name / name_state / fuzzy / first_seen). Some states re-issue all UUIDs "
                           "in a new cycle, so cross-year joins must use the canonical ids.", "district, unit", "per assessment_year"),
}
COL_DOC = {
    "assessment_year": "Assessment cycle label, e.g. '2024-2025'",
    "gwra_year": "Year of the corresponding published Dynamic Ground Water Resource Assessment report",
    "is_complete": "1 if the cycle has full national coverage and is not flagged (see caveat); national reconciliation status per year is in docs/DATA_ACCESS_REPORT.md",
    "methodology": "Assessment methodology (GEC-2015 for all included cycles)",
    "caveat": "Comparability caveat to surface when comparing years",
    "state_id": "INGRES location UUID of the state (stable across cycles)",
    "state_name": "State/UT name as spelled in INGRES",
    "district_id": "Canonical cross-year district id (the district's INGRES UUID in the latest cycle it appears in)",
    "district_name": "District name as spelled in INGRES",
    "unit_id": "Canonical cross-year assessment-unit id (INGRES UUID in the latest cycle it appears in); join years on this",
    "ingres_uuid": "The year-specific INGRES location UUID as returned by the API",
    "canonical_id": "Canonical cross-year id (see unit_id / district_id)",
    "level": "Location level: district or unit",
    "match_method": "uuid = same INGRES UUID; name = same state+district+normalised name; name_state = name unique in state; fuzzy = mutual best string match in same district; first_seen = no counterpart in a later cycle",
    "unit_name": "Assessment unit name as spelled in INGRES",
    "unit_type": "Type of assessment unit (BLOCK, TALUK, MANDAL, FIRKA, ...)",
    "is_district_as_unit": "1 if the district itself is the assessment unit and the unit row was derived from "
                           "the district record (Lakshadweep islands); 0 for units returned by the API",
    "category": "Official categorisation: Safe (SoE<=70%), Semi-Critical (70-90%), Critical (90-100%), "
                "Over-Exploited (>100%), Saline, Hilly Area",
}


def main():
    cfg = yaml.safe_load((ROOT / "configs/data.yaml").read_text())
    interim = ROOT / cfg["interim_dir"]
    locs = pd.read_parquet(interim / "locations.parquet")
    facts = pd.read_parquet(interim / "facts_long.parquet")
    db = ROOT / cfg["processed_db"]
    counts = build(locs, facts, cfg["years"], db)
    print("rows:", counts)

    con = sqlite3.connect(db)
    (ROOT / "reports").mkdir(exist_ok=True)
    pd.read_sql("SELECT level, assessment_year, match_method, COUNT(*) AS n FROM location_crosswalk GROUP BY 1,2,3 ORDER BY 1,2,3",
                con).to_csv(ROOT / "reports/crosswalk_summary.csv", index=False)
    # every non-trivial link, old name -> canonical (latest) name, for manual review
    names = locs[~locs.is_total_row][["year", "uuid", "name"]].drop_duplicates(["year", "uuid"])
    names = dict(zip(zip(names.year, names.uuid), names.name))
    cw = pd.read_sql("""SELECT cw.*, COALESCE(u.unit_name, d.district_name) AS canonical_name FROM location_crosswalk cw
        LEFT JOIN assessment_units u ON cw.level='unit' AND u.unit_id=cw.canonical_id
        LEFT JOIN districts d ON cw.level='district' AND d.district_id=cw.canonical_id
        WHERE match_method IN ('name','name_state','fuzzy')""", con)
    cw["name_in_year"] = [names.get((y, u)) for y, u in zip(cw.assessment_year, cw.ingres_uuid)]
    cw[cw.name_in_year.str.lower() != cw.canonical_name.str.lower()].to_csv(
        ROOT / "reports/crosswalk_renames.csv", index=False)
    schema = {"database": str(db.relative_to(ROOT)).replace("\\", "/"), "dialect": "sqlite",
              "units": {"ham": "hectare-metre = 10,000 m3; 1 BCM = 100,000 ham", "ha": "hectare", "mm": "millimetre", "%": "percent"},
              "source": "INGRES getBusinessDataForUserOpen API; see docs/DATA_ACCESS_REPORT.md",
              "tables": []}
    for t, (desc, geo, yr) in TABLE_DOC.items():
        cols = con.execute(f"PRAGMA table_info({t})").fetchall()
        fks = con.execute(f"PRAGMA foreign_key_list({t})").fetchall()
        tcols = []
        for _, name, typ, notnull, _, pk in cols:
            if name in METRICS:
                raw, unit, d = METRICS[name]
                cdesc, source_field = d, raw
            else:
                unit, cdesc, source_field = None, COL_DOC.get(name, UNCERTAIN), None
            ex = [r[0] for r in con.execute(
                f"SELECT DISTINCT {name} FROM {t} WHERE {name} IS NOT NULL ORDER BY RANDOM() LIMIT 5")]
            nnull = con.execute(f"SELECT AVG({name} IS NULL) FROM {t}").fetchone()[0]
            tcols.append({"name": name, "type": typ, "unit": unit, "description": cdesc,
                          "uncertain": UNCERTAIN in cdesc, "source_field": source_field,
                          "null_rate": round(nnull or 0, 4), "examples": ex})
        schema["tables"].append({
            "name": t, "description": desc, "geographic_semantics": geo, "year_semantics": yr,
            "row_count": con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0],
            "primary_key": [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5]],
            "foreign_keys": [{"column": f[3], "references": f"{f[2]}({f[4]})"} for f in fks],
            "columns": tcols})
    schema["category_values"] = sorted(set(CATEGORIES.values()))
    con.close()
    out = ROOT / "data/schema/schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")

    md = ["# INGRES canonical schema", "",
          "_Generated by `scripts/build_schema.py` from `data/processed/ingres.db`; do not edit by hand._", "",
          f"Units: {'; '.join(f'`{k}` = {v}' for k, v in schema['units'].items())}.", "",
          "Descriptions marked **UNCERTAIN** are inferred from raw field names only and are not confirmed by source documentation.", ""]
    for t in schema["tables"]:
        md += [f"## `{t['name']}` ({t['row_count']:,} rows)", "", t["description"], "",
               f"- Primary key: `{', '.join(t['primary_key'])}`",
               f"- Foreign keys: {', '.join(f'`{f['column']}` -> `{f['references']}`' for f in t['foreign_keys']) or 'none'}",
               f"- Geography: {t['geographic_semantics']}; Year: {t['year_semantics']}", "",
               "| column | type | unit | null % | description | raw INGRES field | examples |",
               "|---|---|---|---:|---|---|---|"]
        for c in t["columns"]:
            ex = ", ".join(str(round(e, 2) if isinstance(e, float) else e) for e in c["examples"][:3])
            desc = c["description"].replace(UNCERTAIN, f"**{UNCERTAIN}**")
            md.append(f"| `{c['name']}` | {c['type']} | {c['unit'] or ''} | {c['null_rate']*100:.1f} | {desc} | "
                      f"{('`' + c['source_field'] + '`') if c['source_field'] else ''} | {ex} |")
        md.append("")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs/INGRES_SCHEMA.md").write_text("\n".join(md), encoding="utf-8")
    print("wrote", out, "and docs/INGRES_SCHEMA.md")


if __name__ == "__main__":
    main()
