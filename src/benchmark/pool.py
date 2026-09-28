"""Entity pool for INGRES-Bench: a fixed, seeded set of real states / districts / units.

Questions only mention pool entities, so every name that appears in a question has a curated
display form and Devanagari / Tamil transliterations (data/benchmark/transliterations.json).
"""
from __future__ import annotations

import random
import re

import pandas as pd

from src.utils.safe_sql import connect_ro, execute

# INGRES spellings -> how people write the state (English display form)
STATE_DISPLAY = {
    "ANDAMAN AND NICOBAR ISLANDS": "Andaman and Nicobar Islands", "ANDHRA PRADESH": "Andhra Pradesh",
    "ARUNACHAL PRADESH": "Arunachal Pradesh", "ASSAM": "Assam", "BIHAR": "Bihar", "CHANDIGARH": "Chandigarh",
    "CHHATTISGARH": "Chhattisgarh", "DADRA AND NAGAR HAVELI": "Dadra and Nagar Haveli", "DAMAN AND DIU": "Daman and Diu",
    "DELHI": "Delhi", "GOA": "Goa", "GUJARAT": "Gujarat", "HARYANA": "Haryana", "HIMACHAL PRADESH": "Himachal Pradesh",
    "JAMMU AND KASHMIR": "Jammu and Kashmir", "JHARKHAND": "Jharkhand", "KARNATAKA": "Karnataka", "KERALA": "Kerala",
    "LADAKH": "Ladakh", "LAKSHDWEEP": "Lakshadweep", "MADHYA PRADESH": "Madhya Pradesh", "MAHARASHTRA": "Maharashtra",
    "MANIPUR": "Manipur", "MEGHALAYA": "Meghalaya", "MIZORAM": "Mizoram", "NAGALAND": "Nagaland", "ODISHA": "Odisha",
    "PUDUCHERRY": "Puducherry", "PUNJAB": "Punjab", "RAJASTHAN": "Rajasthan", "SIKKIM": "Sikkim",
    "TAMILNADU": "Tamil Nadu", "TELANGANA": "Telangana", "TRIPURA": "Tripura", "UTTAR PRADESH": "Uttar Pradesh",
    "UTTARAKHAND": "Uttarakhand", "WEST BENGAL": "West Bengal",
}
# Himachal Pradesh districts are stored as 3-letter codes in INGRES
HP_CODES = {"SLN": "Solan", "KIN": "Kinnaur", "SRM": "Sirmaur", "KNG": "Kangra", "KUL": "Kullu", "UNA": "Una",
            "MND": "Mandi", "SHM": "Shimla", "BLS": "Bilaspur", "CHM": "Chamba", "LAS": "Lahaul and Spiti", "HMP": "Hamirpur"}

UNITS_PER_DISTRICT = 2
DISTRICTS_PER_STATE = 2
AMBIGUOUS_NAMES = 8         # unit names shared across >= 3 states, deliberately included
MAX_PER_AMBIGUOUS_NAME = 5
RESPELLED_UNITS = 12


def display(name: str) -> str:
    """Readable form of an INGRES name: underscores -> spaces, UPPER -> Title, collapse spaces."""
    if name in STATE_DISPLAY:
        return STATE_DISPLAY[name]
    if name in HP_CODES:
        return HP_CODES[name]
    s = re.sub(r"\s+", " ", name.replace("_", " ")).strip()
    if s.isupper():  # title-case each word and each hyphen part, keeping roman numerals (ALIPURDUAR-II)
        part = lambda p: p if re.fullmatch(r"[IVX]+", p) else p.capitalize()  # noqa: E731
        s = " ".join("-".join(part(p) for p in w.split("-")) for w in s.split())
    return s


def build_pool(db_path, seed: int = 13) -> pd.DataFrame:
    rng = random.Random(seed)
    con = connect_ro(db_path)
    q = lambda s: pd.DataFrame(execute(con, s).rows, columns=execute(con, s).columns)  # noqa: E731
    units = q("""SELECT u.unit_id, u.unit_name, u.unit_type, d.district_id, d.district_name, s.state_id, s.state_name,
                        (SELECT COUNT(*) FROM unit_assessments ua WHERE ua.unit_id = u.unit_id) AS n_years
                 FROM assessment_units u JOIN districts d ON d.district_id = u.district_id JOIN states s ON s.state_id = u.state_id
                 WHERE u.unit_id IN (SELECT unit_id FROM unit_assessments WHERE assessment_year = '2024-2025'
                                     AND category NOT IN ('Hilly Area'))""")
    # a unit is addressable by (name, district) only if that pair is unique -> required for name-based gold SQL
    units = units[~units.duplicated(["unit_name", "district_name", "state_name"], keep=False)]
    rows = []
    for st, g in units.groupby("state_name"):
        dists = sorted(g.district_name.unique())
        for d in rng.sample(dists, min(DISTRICTS_PER_STATE, len(dists))):
            gd = g[g.district_name == d].sort_values("unit_name")
            # prefer units present in several cycles (cross-year questions need them)
            gd = gd.sort_values("n_years", ascending=False, kind="stable")
            rows += gd.head(UNITS_PER_DISTRICT * 2).sample(min(UNITS_PER_DISTRICT, len(gd)), random_state=seed).to_dict("records")
    pool = pd.DataFrame(rows)
    # deliberately add a few ambiguous names (shared by units in >= 3 states), several occurrences each
    amb = units.assign(k=units.unit_name.str.lower()).groupby("k").state_name.nunique()
    names = rng.sample(sorted(amb[amb >= 3].index), AMBIGUOUS_NAMES)
    amb_units = (units[units.unit_name.str.lower().isin(names)].assign(k=lambda d: d.unit_name.str.lower())
                 .groupby("k", group_keys=False).apply(lambda g: g.sample(min(len(g), MAX_PER_AMBIGUOUS_NAME), random_state=seed),
                                                       include_groups=False))
    pool = pd.concat([pool[~pool.unit_name.str.lower().isin(names)], amb_units], ignore_index=True).drop_duplicates("unit_id")
    pool["is_ambiguous_name"] = pool.unit_name.str.lower().isin(names)
    # units with a real historical respelling in INGRES (crosswalk fuzzy links), used as naturally occurring noise
    ren = q("""SELECT DISTINCT canonical_id AS unit_id FROM location_crosswalk WHERE level = 'unit' AND match_method = 'fuzzy'""")
    cand = units[units.unit_id.isin(ren.unit_id) & ~units.unit_id.isin(pool.unit_id)].sort_values("unit_id")
    pool = pd.concat([pool, cand.sample(min(RESPELLED_UNITS, len(cand)), random_state=seed)], ignore_index=True)
    pool["has_respelling"] = pool.unit_id.isin(ren.unit_id)
    pool["is_ambiguous_name"] = pool.is_ambiguous_name.astype("boolean").fillna(False).astype(bool)
    return pool.sort_values(["state_name", "district_name", "unit_name"]).reset_index(drop=True)
