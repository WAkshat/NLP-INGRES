"""INGRES data-access / data-quality audit.

Reads cached raw API responses (run scripts/crawl_ingres.py first), writes the lossless
interim tables and a machine-readable audit used to write docs/DATA_ACCESS_REPORT.md:
    data/interim/locations.parquet, data/interim/facts_long.parquet
    reports/data_audit.json
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ingestion.flatten import flatten  # noqa: E402

HAM_PER_BCM = 1e5  # 1 BCM = 1e9 m3 = 1e5 ham (1 ham = 1e4 m3)

# Official national figures (fresh groundwater, BCM) from PIB press releases, used to
# confirm the year-label mapping and units. INGRES label "YYYY-(YYYY+1)" == GWRA YYYY+1.
PUBLISHED = {
    "2019-2020": {"gwra": 2020, "extraction_approx": 245,
                  "src": "https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1848469 (only '245 BCM' extraction located; other figures NOT verified)"},
    "2021-2022": {"gwra": 2022, "recharge": 437.60, "extractable": 398.08, "extraction": 239.16, "soe": 60.08, "units": 7089,
                  "src": "https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=1874808"},
    "2022-2023": {"gwra": 2023, "recharge": 449.08, "extraction": 241.34, "soe": 59.23, "units": 6553,
                  "src": "https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1981600"},
    "2023-2024": {"gwra": 2024, "recharge": 446.90, "extractable": 406.19, "extraction": 245.64, "soe": 60.47,
                  "src": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2089039"},
    "2024-2025": {"gwra": 2025, "recharge": 448.52, "extractable": 407.75, "extraction": 247.22, "soe": 60.63,
                  "src": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2220203"},
}

KEY_FIELDS = {  # canonical metric -> raw field path (unit level)
    "recharge_total": "rechargeData.total.total",
    "extractable_total": "currentAvailabilityForAllPurposes.total",
    "extraction_total": "draftData.total.total",
    "extraction_irrigation": "draftData.agriculture.total",
    "extraction_domestic": "draftData.domestic.total",
    "extraction_industrial": "draftData.industry.total",
    "stage_of_extraction": "stageOfExtraction.total",
    "future_availability": "availabilityForFutureUse.total",
    "natural_discharge": "loss.total",
    "rainfall_mm": "rainfall.total",
    "total_area": "area.total.totalArea",
    "category": "category.total",
}


def soe_category(soe: float) -> str:
    return "safe" if soe <= 70 else "semi_critical" if soe <= 90 else "critical" if soe <= 100 else "over_exploited"


def name_issues(name: str) -> list[str]:
    out = []
    if name != name.strip():
        out.append("leading/trailing whitespace")
    if "  " in name:
        out.append("double space")
    if any(ord(c) > 127 for c in name):
        out.append("non-ascii")
    if "�" in name or re.search(r"Ã|â€", name):
        out.append("mojibake")
    if unicodedata.normalize("NFC", name) != name:
        out.append("not NFC")
    if re.search(r"[^A-Za-z0-9 .()\-/&']", name):
        out.append("unusual punctuation")
    return out


def main():
    cfg = yaml.safe_load((ROOT / "configs/data.yaml").read_text())
    locs, facts = flatten(ROOT / cfg["raw_dir"])
    interim = ROOT / cfg["interim_dir"]
    interim.mkdir(parents=True, exist_ok=True)
    locs.to_parquet(interim / "locations.parquet", index=False)
    facts.to_parquet(interim / "facts_long.parquet", index=False)

    audit: dict = {"raw_files": int(locs.raw_file.nunique()), "fact_rows": len(facts),
                   "distinct_raw_fields": int(facts.field.nunique())}
    real = locs[~locs.is_total_row]

    # 1. coverage
    audit["rows_by_year_level"] = {f"{y}|{lv}": int(n) for (y, lv), n in real.groupby(["year", "level"]).size().items()}
    audit["unit_types_by_year"] = {y: g.unit_type.value_counts(dropna=False).to_dict()
                                   for y, g in real[real.level == "unit"].groupby("year")}
    audit["unit_types_by_state"] = (real[real.level == "unit"].merge(
        real[real.level == "state"][["year", "uuid", "name"]].rename(columns={"uuid": "state_uuid", "name": "state"}),
        on=["year", "state_uuid"]).groupby("state").unit_type.agg(lambda s: sorted(s.dropna().unique())).to_dict())
    states_per_year = real[real.level == "state"].groupby("year").name.apply(set)
    all_states = set().union(*states_per_year)
    audit["states_missing_by_year"] = {y: sorted(all_states - s) for y, s in states_per_year.items()}

    dist = real[real.level == "district"]
    with_metrics = set(zip(facts[(facts.level == "district") & (facts.field == "rechargeData.total.total")].uuid,
                           facts[(facts.level == "district") & (facts.field == "rechargeData.total.total")].year))
    nm = dist[[(u, y) not in with_metrics for u, y in zip(dist.uuid, dist.year)]]
    audit["districts_without_metrics"] = {y: sorted(f"{r.name} ({r.parent_name})" for r in g.itertuples())
                                          for y, g in nm.groupby("year")}
    has_units = set(zip(real[real.level == "unit"].district_uuid, real[real.level == "unit"].year))
    nu = dist[[(u, y) not in has_units for u, y in zip(dist.uuid, dist.year)]]
    audit["districts_without_child_units"] = {y: sorted(f"{r.name} ({r.parent_name})" for r in g.itertuples())
                                              for y, g in nu.groupby("year")}

    # 2. missing values for canonical fields (unit level)
    uf = facts[facts.level == "unit"]
    units = real[real.level == "unit"][["year", "uuid"]]
    miss = {}
    for canon, fp in KEY_FIELDS.items():
        got = uf[uf.field == fp][["year", "uuid"]].drop_duplicates()
        m = units.merge(got, how="left", indicator=True)
        miss[canon] = {y: round(float((g._merge == "left_only").mean()), 4) for y, g in m.groupby("year")}
    audit["missing_rate_unit_fields"] = miss
    wide = uf[uf.field.isin(KEY_FIELDS.values())].pivot_table(
        index=["year", "uuid"], columns="field", values="value_num", aggfunc="first")
    audit["zero_rate_unit_fields"] = {c: {y: round(float((g[c] == 0).mean()), 4) for y, g in wide.groupby(level=0)}
                                      for c in wide.columns}

    # 3. duplicates
    audit["duplicate_uuid_within_year_level"] = int(real.duplicated(["year", "level", "uuid"]).sum())
    audit["duplicate_uuid_rows_sample"] = real[real.duplicated(["year", "level", "uuid"], keep=False)].head(10)[
        ["year", "level", "uuid", "name", "parent_name"]].to_dict("records")
    u24 = real[(real.level == "unit")]
    latest = u24[u24.year == max(cfg["years"])]
    lname = latest.assign(n=latest.name.str.strip().str.lower())
    by_name = lname.groupby("n").agg(k=("uuid", "nunique"), districts=("district_uuid", "nunique"),
                                     states=("state_uuid", "nunique"))
    audit["ambiguous_unit_names_latest_year"] = {
        "unit_names_shared_by_>1_unit": int((by_name.k > 1).sum()),
        "shared_across_districts": int((by_name.districts > 1).sum()),
        "shared_across_states": int((by_name.states > 1).sum()),
        "examples": by_name[by_name.states > 1].sort_values("k", ascending=False).head(15).k.to_dict()}
    d_latest = real[(real.level == "district") & (real.year == max(cfg["years"]))]
    dn = d_latest.assign(n=d_latest.name.str.strip().str.lower()).groupby("n").state_uuid.nunique()
    audit["district_names_in_multiple_states_latest_year"] = dn[dn > 1].to_dict()
    unit_district_same_name = latest.merge(d_latest[["uuid", "name"]].rename(columns={"uuid": "district_uuid", "name": "dname"}))
    audit["units_named_like_their_district_latest_year"] = int(
        (unit_district_same_name.name.str.lower().str.strip() == unit_district_same_name.dname.str.lower().str.strip()).sum())

    # 4. encoding / name hygiene
    iss = real.assign(issues=real.name.map(name_issues))
    iss = iss[iss.issues.str.len() > 0]
    audit["name_issues"] = {k: int(v) for k, v in iss.explode("issues").issues.value_counts().items()}
    audit["name_issue_examples"] = iss.drop_duplicates("name").head(25)[["level", "name", "issues"]].to_dict("records")
    case = real.assign(n=real.name.str.lower().str.strip()).groupby(["level", "uuid"]).name.nunique()
    audit["uuids_with_multiple_name_spellings_across_years"] = {lv: int((g > 1).sum()) for lv, g in case.groupby(level=0)}
    ex = real[real.uuid.isin(case[case > 1].index.get_level_values(1))].groupby("uuid").name.apply(
        lambda s: sorted(set(s))).head(20)
    audit["name_change_examples"] = ex.to_dict()

    # 5. cross-year joinability (uuid overlap between consecutive configured years)
    yrs = [y for y in sorted(real.year.unique())]
    overlap = {}
    for lv in ["state", "district", "unit"]:
        s = {y: set(real[(real.level == lv) & (real.year == y)].uuid) for y in yrs}
        overlap[lv] = {f"{a}->{b}": {"a": len(s[a]), "b": len(s[b]), "common": len(s[a] & s[b]),
                                      "jaccard": round(len(s[a] & s[b]) / max(1, len(s[a] | s[b])), 4)}
                       for a, b in zip(yrs, yrs[1:])}
    audit["uuid_overlap_consecutive_years"] = overlap
    un = real[real.level == "unit"]
    moved = un.groupby("uuid").district_uuid.nunique()
    audit["units_that_changed_parent_district"] = int((moved > 1).sum())
    audit["units_changed_parent_examples"] = [
        f"{g['name'].iloc[-1]}: " + " -> ".join(f"{p}@{y}" for p, y in zip(g.parent_name, g.year))
        for _, g in list(un[un.uuid.isin(moved[moved > 1].index)].sort_values("year").groupby("uuid"))[:10]]
    audit["units_present_in_all_years"] = int((un.groupby("uuid").year.nunique() == len(yrs)).sum())
    audit["units_total_distinct"] = int(un.uuid.nunique())

    # 6. reconciliation
    nat = facts[(facts.level == "state") & facts.uuid.str.startswith("total:")]
    rec = {}
    for y, g in nat.groupby("year"):
        v = dict(zip(g.field, g.value_num))
        fresh = lambda k: (v.get(f"{k}.total", 0) - v.get(f"{k}.poor_quality", 0)) / HAM_PER_BCM  # noqa: E731
        r = {"recharge_total_bcm": v.get("rechargeData.total.total", 0) / HAM_PER_BCM,
             "recharge_fresh_bcm": fresh("rechargeData.total"),
             "extractable_fresh_bcm": fresh("currentAvailabilityForAllPurposes"),
             "extraction_fresh_bcm": fresh("draftData.total"),
             "soe_api": v.get("stageOfExtraction.total")}
        r = {k: round(x, 2) if x is not None else None for k, x in r.items()}
        yu = real[(real.level == "unit") & (real.year == y)]
        r["units_api"] = int(len(yu))
        cats = uf[(uf.year == y) & (uf.field == "category.total")].value_str
        r["units_api_excl_hilly"] = int((~cats.isin(["Hilly Area", "hilly"])).sum())
        if y in PUBLISHED:
            r["published"] = PUBLISHED[y]
        rec[y] = r
    audit["national_reconciliation"] = rec

    # child sums vs parent aggregates, recharge + extraction
    def child_vs_parent(child_level, parent_level, key):
        c = facts[(facts.level == child_level) & (facts.field == key) & ~facts.uuid.str.startswith("total:")]
        c = c.merge(real[real.level == child_level][["year", "uuid", "parent_uuid"]], on=["year", "uuid"])
        cs = c.groupby(["year", "parent_uuid"]).value_num.sum().rename("child_sum")
        p = facts[(facts.level == parent_level) & (facts.field == key)].set_index(["year", "uuid"]).value_num
        p.index.names = ["year", "parent_uuid"]
        j = pd.concat([cs, p.rename("parent")], axis=1, join="inner")
        rel = ((j.child_sum - j.parent).abs() / j.parent.abs().clip(lower=1e-9))
        return {y: {"parents": int(len(g)), "within_0.1pct": round(float((g <= 1e-3).mean()), 4),
                    "max_rel_diff": round(float(g.max()), 4)} for y, g in rel.groupby(level=0)}
    audit["unit_sum_vs_district"] = {k: child_vs_parent("unit", "district", k)
                                     for k in ["rechargeData.total.total", "draftData.total.total"]}
    audit["district_sum_vs_state"] = {k: child_vs_parent("district", "state", k)
                                      for k in ["rechargeData.total.total", "draftData.total.total"]}

    # category consistency with published SoE thresholds (safe<=70<semi<=90<critical<=100<OE)
    cat = uf[uf.field == "category.total"][["year", "uuid", "value_str"]]
    soe = uf[uf.field == "stageOfExtraction.total"][["year", "uuid", "value_num"]]
    cs = cat.merge(soe, on=["year", "uuid"])
    audit["unit_category_values"] = {y: g.value_str.value_counts().to_dict() for y, g in cat.groupby("year")}
    std = cs[cs.value_str.isin(["safe", "semi_critical", "critical", "over_exploited"])].copy()
    std["expected"] = std.value_num.map(soe_category)
    audit["category_matches_soe_threshold"] = {y: round(float((g.expected == g.value_str).mean()), 4)
                                               for y, g in std.groupby("year")}
    audit["category_mismatch_examples"] = std[std.expected != std.value_str].head(10).to_dict("records")

    out = ROOT / "reports/data_audit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(audit, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ["rows_by_year_level", "national_reconciliation",
                                             "category_matches_soe_threshold"]}, indent=1, default=str))
    print("full audit ->", out)


if __name__ == "__main__":
    main()
