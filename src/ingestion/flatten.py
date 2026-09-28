"""Raw INGRES JSON -> lossless interim tables.

locations.parquet : one row per (year, location) with hierarchy (state/district/unit uuids + names)
facts_long.parquet: one row per (year, location, field_path) numeric/string leaf value

Skipped (kept only in raw): `computationSummary` (per-unit intermediate computation tree) and
`gwlevelData` (pre/post-monsoon water-level series) -- nested, not part of the published assessment table.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.ingestion.ingres_api import load_raw

SKIP = {"computationSummary", "gwlevelData", "reportSummary", "locationName", "locationUUID"}
LEVEL_OF_CHILDREN = {"COUNTRY": "state", "STATE": "district", "DISTRICT": "unit"}


def leaves(x, prefix=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from leaves(v, f"{prefix}{k}.")
    elif x is not None and not isinstance(x, list):
        yield prefix[:-1], x


def unit_type(rec: dict) -> str | None:
    """The unit's own level is the reportSummary["total"] entry whose category counts sum to 1:
    Punjab block : {"total": {"BLOCK": {"safe": 1}}}                       -> BLOCK
    AP mandal    : {"total": {"VILLAGE": {"safe": 15}, "BLOCK": {"safe": 1}}} -> BLOCK (villages are sub-units)
    """
    total = (rec.get("reportSummary") or {}).get("total") or {}
    own = [lvl for lvl, c in total.items() if isinstance(c, dict) and sum(c.values()) == 1]
    # a parent with exactly one sub-unit has two sum-1 levels; the parent is the unit we crawled
    own.sort(key=lambda lvl: lvl in SUB_UNIT_LEVELS)
    return own[0] if own else None


SUB_UNIT_LEVELS = {"VILLAGE", "FIRKA", "WATERSHED"}


def flatten(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    locs, facts = [], []
    for path in sorted(raw_dir.glob("*/*.json.gz")):
        raw = load_raw(path)
        req = raw["request"]
        year, ptype = req["year"], req["loctype"]
        level = LEVEL_OF_CHILDREN[ptype]
        for rec in raw["response"]:
            is_total = rec.get("locationName") == "total"
            uuid = rec.get("locationUUID") or f"total:{req['locuuid']}"
            loc = {"year": year, "level": level, "uuid": uuid, "name": rec.get("locationName"),
                   "is_total_row": is_total, "parent_uuid": req["locuuid"], "parent_name": req["locname"],
                   "unit_type": unit_type(rec) if level == "unit" else None,
                   "state_uuid": {"state": uuid, "district": req["locuuid"], "unit": req["parentuuid"]}[level],
                   "district_uuid": {"state": None, "district": uuid, "unit": req["locuuid"]}[level],
                   "raw_file": path.name}
            locs.append(loc)
            for k, v in rec.items():
                if k in SKIP:
                    continue
                for fp, val in leaves({k: v}):
                    facts.append((year, level, uuid, fp, val if isinstance(val, str) else None,
                                  None if isinstance(val, str) else float(val)))
    locations = pd.DataFrame(locs)
    facts_long = pd.DataFrame(facts, columns=["year", "level", "uuid", "field", "value_str", "value_num"])
    return locations, facts_long
