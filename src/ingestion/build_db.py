"""Interim long tables -> canonical SQLite database (data/processed/ingres.db).

Schema (one fact table per administrative level, so "district vs block" is a real
schema-linking decision, as it is for users of the portal):

    assessment_years(assessment_year PK, gwra_year, is_complete, methodology, caveat)
    states(state_id PK, state_name)
    districts(district_id PK, district_name, state_id FK)
    assessment_units(unit_id PK, unit_name, unit_type, district_id FK, state_id FK)
    state_assessments   (state_id,    assessment_year, <metrics>)
    district_assessments(district_id, assessment_year, <metrics>)
    unit_assessments    (unit_id,     assessment_year, district_id, ingres_uuid, category, <metrics>)
    location_crosswalk  (level, assessment_year, ingres_uuid, canonical_id, match_method)

district_id / unit_id are canonical cross-year ids (src/normalization/crosswalk.py): some states
re-issue every UUID in a new cycle, so raw UUIDs cannot be used to join years.

Dimension names/parents come from the most recent year a location appears in.
unit_assessments keeps the district the unit was reported under *in that year*, because
districts are re-organised between cycles. Values are copied unchanged from the API.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.normalization.crosswalk import crosswalk

# canonical column -> (raw field path, unit, description). Descriptions are ours, grounded in
# the GEC-2015 terminology used by the portal and the published reports; see docs/INGRES_SCHEMA.md.
METRICS: dict[str, tuple[str, str, str]] = {
    "annual_recharge_ham": ("rechargeData.total.total", "ham", "Total annual ground water recharge (all sources)"),
    "recharge_rainfall_ham": ("rechargeData.rainfall.total", "ham", "Recharge from rainfall"),
    "recharge_canal_ham": ("rechargeData.canal.total", "ham", "Recharge from canal seepage"),
    "recharge_surface_irrigation_ham": ("rechargeData.surface_irrigation.total", "ham", "Recharge from return flow of surface-water irrigation"),
    "recharge_gw_irrigation_ham": ("rechargeData.gw_irrigation.total", "ham", "Recharge from return flow of groundwater irrigation"),
    "recharge_water_bodies_ham": ("rechargeData.water_body.total", "ham", "Recharge from tanks, ponds and other water bodies"),
    "recharge_artificial_structures_ham": ("rechargeData.artificial_structure.total", "ham", "Recharge from water conservation / artificial recharge structures"),
    "recharge_pipeline_ham": ("rechargeData.pipeline.total", "ham", "Recharge from pipeline leakage (UNCERTAIN: inferred from field name)"),
    "recharge_sewage_ham": ("rechargeData.sewage.total", "ham", "Recharge from sewage (UNCERTAIN: inferred from field name)"),
    "natural_discharge_ham": ("loss.total", "ham", "Total natural discharges (portal field `loss`)"),
    "extractable_resource_ham": ("currentAvailabilityForAllPurposes.total", "ham", "Annual extractable ground water resource"),
    "extraction_total_ham": ("draftData.total.total", "ham", "Annual ground water extraction for all uses"),
    "extraction_irrigation_ham": ("draftData.agriculture.total", "ham", "Annual ground water extraction for irrigation"),
    "extraction_domestic_ham": ("draftData.domestic.total", "ham", "Annual ground water extraction for domestic use"),
    "extraction_industrial_ham": ("draftData.industry.total", "ham", "Annual ground water extraction for industrial use"),
    "stage_of_extraction_pct": ("stageOfExtraction.total", "%", "Stage of ground water extraction = extraction / extractable resource x 100"),
    "domestic_allocation_ham": ("gwallocation.domestic.total", "ham", "Projected allocation for domestic use (projection year UNCERTAIN)"),
    "future_availability_ham": ("availabilityForFutureUse.total", "ham", "Net annual ground water availability for future use"),
    "recharge_poor_quality_ham": ("rechargeData.total.poor_quality", "ham", "Portion of annual recharge in poor-quality (saline) groundwater zones"),
    "extractable_poor_quality_ham": ("currentAvailabilityForAllPurposes.poor_quality", "ham", "Portion of extractable resource in poor-quality zones"),
    "extraction_poor_quality_ham": ("draftData.total.poor_quality", "ham", "Portion of extraction in poor-quality zones"),
    "rainfall_mm": ("rainfall.total", "mm", "Rainfall used in the assessment (averaging method UNCERTAIN)"),
    "total_area_ha": ("area.total.totalArea", "ha", "Total geographical area"),
    "recharge_worthy_area_ha": ("area.recharge_worthy.totalArea", "ha", "Recharge-worthy area"),
}

CATEGORIES = {"safe": "Safe", "semi_critical": "Semi-Critical", "critical": "Critical",
              "over_exploited": "Over-Exploited", "saline": "Saline", "salinity": "Saline",
              "Hilly Area": "Hilly Area", "hilly": "Hilly Area"}

YEAR_META = {  # assessment_year -> (gwra_year, caveat). INGRES label "YYYY-(YYYY+1)" == GWRA YYYY+1 (verified vs PIB).
    "2016-2017": (2017, "FLAGGED: incomplete coverage in INGRES and national totals inconsistent with later cycles; do not compare."),
    "2019-2020": (2020, None),
    "2021-2022": (2022, None),
    "2022-2023": (2023, None),
    "2023-2024": (2024, None),
    "2024-2025": (2025, None),
    "2025-2026": (2026, "FLAGGED: cycle possibly in progress (fewer states); values may change."),
}
METHOD_CAVEAT = ("All cycles use GEC-2015 methodology, but assessment-unit boundaries, district "
                 "reorganisations, input data and parameter revisions differ between cycles; "
                 "treat cross-year differences as historical change detection, not trend estimates.")


def canonicalise(locs: pd.DataFrame, facts: pd.DataFrame):
    """Replace year-specific INGRES UUIDs of districts/units by cross-year canonical ids."""
    dcw = crosswalk(locs, "district")
    dmap = dict(zip(zip(dcw.year, dcw.uuid), dcw.canonical_id))
    ucw = crosswalk(locs, "unit", district_canon=dmap)
    umap = dict(zip(zip(ucw.year, ucw.uuid), ucw.canonical_id))
    maps = {"district": dmap, "unit": umap}
    locs = locs.copy()
    locs["ingres_uuid"] = locs.uuid
    locs["uuid"] = [maps.get(lv, {}).get((y, u), u) for lv, y, u in zip(locs.level, locs.year, locs.uuid)]
    locs["district_uuid"] = [dmap.get((y, d), d) for y, d in zip(locs.year, locs.district_uuid)]
    facts = facts.copy()
    facts["uuid"] = [maps.get(lv, {}).get((y, u), u) for lv, y, u in zip(facts.level, facts.year, facts.uuid)]
    cw = pd.concat([dcw.assign(level="district"), ucw.assign(level="unit")], ignore_index=True).rename(
        columns={"year": "assessment_year", "uuid": "ingres_uuid"})
    return locs, facts, cw[["level", "assessment_year", "ingres_uuid", "canonical_id", "match_method"]]


def build(locations: pd.DataFrame, facts: pd.DataFrame, years: list[str], db_path: Path) -> dict[str, int]:
    locs = locations[~locations.is_total_row & locations.year.isin(years)]
    facts = facts[facts.year.isin(years) & ~facts.uuid.str.startswith("total:")]
    locs, facts, cw = canonicalise(locs, facts)
    latest = locs.sort_values("year").groupby(["level", "uuid"]).tail(1)
    lv = lambda name: latest[latest.level == name]  # noqa: E731

    states = lv("state").assign(state_id=lambda d: d.uuid, state_name=lambda d: d.name)[["state_id", "state_name"]]
    districts = lv("district").assign(district_id=lambda d: d.uuid, district_name=lambda d: d.name,
                                      state_id=lambda d: d.state_uuid)[["district_id", "district_name", "state_id"]]
    units = lv("unit").assign(unit_id=lambda d: d.uuid, unit_name=lambda d: d.name, district_id=lambda d: d.district_uuid,
                              state_id=lambda d: d.state_uuid)[["unit_id", "unit_name", "unit_type", "district_id", "state_id"]]

    wanted = {fp: col for col, (fp, _, _) in METRICS.items()}
    num = facts[facts.field.isin(wanted)].assign(col=lambda d: d.field.map(wanted))
    wide = num.pivot_table(index=["level", "uuid", "year"], columns="col", values="value_num", aggfunc="first").reset_index()
    for c in METRICS:
        if c not in wide:
            wide[c] = None
    metric_cols = list(METRICS)

    def fact(level, idcol):
        w = wide[wide.level == level].rename(columns={"uuid": idcol, "year": "assessment_year"})
        return w[[idcol, "assessment_year"] + metric_cols]

    # level filter matters: in small UTs the district is its own assessment unit (same uuid at both levels)
    cat = facts[(facts.level == "unit") & (facts.field == "category.total")][["uuid", "year", "value_str"]].rename(
        columns={"uuid": "unit_id", "year": "assessment_year"})
    unmapped = set(cat.value_str) - set(CATEGORIES)
    if unmapped:
        raise ValueError(f"unmapped category values: {unmapped}")
    cat["category"] = cat.value_str.map(CATEGORIES)
    ua = (locs[locs.level == "unit"][["uuid", "year", "district_uuid", "ingres_uuid"]]
          .rename(columns={"uuid": "unit_id", "year": "assessment_year", "district_uuid": "district_id"})
          .merge(cat[["unit_id", "assessment_year", "category"]], how="left")
          .merge(fact("unit", "unit_id"), how="left"))

    # Lakshadweep islands: the district record itself carries the official category but the API
    # returns no child units, so the district is its own assessment unit (as INGRES already does
    # explicitly for Chandigarh / Daman / DNH). Flagged via is_district_as_unit.
    dcat = facts[(facts.level == "district") & (facts.field == "category.total")][["uuid", "year", "value_str"]]
    have_units = set(zip(locs[locs.level == "unit"].district_uuid, locs[locs.level == "unit"].year))
    dcat = dcat[[(u, y) not in have_units for u, y in zip(dcat.uuid, dcat.year)]]
    extra = (dcat.rename(columns={"uuid": "unit_id", "year": "assessment_year"})
             .assign(district_id=lambda d: d.unit_id, ingres_uuid=None, category=lambda d: d.value_str.map(CATEGORIES))
             .drop(columns="value_str")
             .merge(fact("district", "district_id").rename(columns={"district_id": "unit_id"}), how="left"))
    ua = pd.concat([ua.assign(is_district_as_unit=0), extra.assign(is_district_as_unit=1)], ignore_index=True)
    ua = ua[["unit_id", "assessment_year", "district_id", "ingres_uuid", "category", "is_district_as_unit"] + metric_cols]
    extra_dims = (lv("district")[lv("district").uuid.isin(set(extra.unit_id))]
                  .assign(unit_id=lambda d: d.uuid, unit_name=lambda d: d.name, unit_type="DISTRICT",
                          district_id=lambda d: d.uuid, state_id=lambda d: d.state_uuid)
                  [["unit_id", "unit_name", "unit_type", "district_id", "state_id"]])
    units = pd.concat([units, extra_dims], ignore_index=True).drop_duplicates("unit_id")

    ym = pd.DataFrame([{"assessment_year": y, "gwra_year": YEAR_META[y][0],
                        "is_complete": int(YEAR_META[y][1] is None), "methodology": "GEC-2015",
                        "caveat": YEAR_META[y][1] or METHOD_CAVEAT} for y in years])

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    mcols = ",\n  ".join(f"{c} REAL" for c in metric_cols)
    con.executescript(f"""
CREATE TABLE assessment_years (assessment_year TEXT PRIMARY KEY, gwra_year INTEGER, is_complete INTEGER,
  methodology TEXT, caveat TEXT);
CREATE TABLE states (state_id TEXT PRIMARY KEY, state_name TEXT NOT NULL);
CREATE TABLE districts (district_id TEXT PRIMARY KEY, district_name TEXT NOT NULL,
  state_id TEXT NOT NULL REFERENCES states(state_id));
CREATE TABLE assessment_units (unit_id TEXT PRIMARY KEY, unit_name TEXT NOT NULL, unit_type TEXT,
  district_id TEXT REFERENCES districts(district_id), state_id TEXT REFERENCES states(state_id));
CREATE TABLE state_assessments (state_id TEXT NOT NULL REFERENCES states(state_id),
  assessment_year TEXT NOT NULL REFERENCES assessment_years(assessment_year),
  {mcols}, PRIMARY KEY (state_id, assessment_year));
CREATE TABLE district_assessments (district_id TEXT NOT NULL REFERENCES districts(district_id),
  assessment_year TEXT NOT NULL REFERENCES assessment_years(assessment_year),
  {mcols}, PRIMARY KEY (district_id, assessment_year));
CREATE TABLE unit_assessments (unit_id TEXT NOT NULL REFERENCES assessment_units(unit_id),
  assessment_year TEXT NOT NULL REFERENCES assessment_years(assessment_year),
  district_id TEXT REFERENCES districts(district_id), ingres_uuid TEXT, category TEXT, is_district_as_unit INTEGER,
  {mcols}, PRIMARY KEY (unit_id, assessment_year));
CREATE TABLE location_crosswalk (level TEXT, assessment_year TEXT, ingres_uuid TEXT, canonical_id TEXT,
  match_method TEXT, PRIMARY KEY (level, assessment_year, ingres_uuid));
""")
    tables = {"assessment_years": ym, "states": states, "districts": districts, "assessment_units": units,
              "state_assessments": fact("state", "state_id"), "district_assessments": fact("district", "district_id"),
              "unit_assessments": ua, "location_crosswalk": cw}
    for name, df in tables.items():
        df.to_sql(name, con, if_exists="append", index=False)
    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    con.commit()
    con.close()
    if bad:
        raise ValueError(f"{len(bad)} foreign-key violations, e.g. {bad[:3]}")
    return {k: len(v) for k, v in tables.items()}
