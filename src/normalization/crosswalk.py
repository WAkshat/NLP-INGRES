"""Cross-year location crosswalk.

INGRES location UUIDs are stable for most states, but some states re-issue every unit UUID in a
new cycle (new boundary-shapefile version; observed for Karnataka, Madhya Pradesh, Maharashtra,
West Bengal, Himachal Pradesh between 2023-2024 and 2024-2025), and some keep the UUID but fix
spellings. A canonical id is assigned per location, walking from the latest year backwards:

  1. uuid       - the same INGRES UUID already seen in a later year
  2. name       - same state + unit type + normalised parent-district name + normalised name
  3. name_state - normalised name unique within (state, unit type) in both years (parent district renamed/split)
  4. fuzzy      - same state + unit type + parent, mutual unique best SequenceMatcher ratio >= 0.75
  otherwise first_seen (no counterpart in any later year; the location gets its own canonical id). Ambiguous candidates are never matched.
The canonical id is the UUID the location has in the latest year it appears in.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

import pandas as pd

FUZZY_THRESHOLD = 0.75


def norm_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[\-_./(),']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio()


def _is_extension(a: str, b: str) -> bool:
    """One name is the other plus a qualifier (SANGANER -> SANGANER_RURAL, JABALPUR -> JABALPUR URBAN):
    signals a boundary split, not a respelling, so it must not be linked."""
    a, b = a.replace(" ", ""), b.replace(" ", "")
    short, long_ = sorted((a, b), key=len)
    return short in long_ and len(long_) - len(short) >= 3


# only I-IV as roman numerals: single letters like the "(V)"/"(E)" district initials on Tamil Nadu firkas are not ordinals
_ORDINAL = re.compile(r"\b(\d+|i{1,3}|iv)\b")
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4}


def _ordinals_differ(a: str, b: str) -> bool:
    """MYLAPORE-III vs MYLAPORE-II, LUDHIANA 1 vs LUDHIANA 2: numbered siblings, never the same unit.
    HOSHIARPUR-II vs Hoshiarpur-2 is the same ordinal."""
    val = lambda s: [_ROMAN.get(t) or int(t) for t in _ORDINAL.findall(s)]  # noqa: E731
    return val(a) != val(b)


def _mutual_best(rest: pd.DataFrame, pool: pd.DataFrame, threshold: float = FUZZY_THRESHOLD):
    """Pairs (uuid, canonical_id) that are each other's unique best match above threshold."""
    if rest.empty or pool.empty:
        return []
    s = [[0.0 if _is_extension(a, b) or _ordinals_differ(a, b) else _sim(a, b) for b in pool.n] for a in rest.n]
    pairs = []
    for i, row in enumerate(s):
        j = max(range(len(row)), key=row.__getitem__)
        col = [s[k][j] for k in range(len(s))]
        unique_row = sorted(row, reverse=True)[1:2] != [row[j]]
        unique_col = sorted(col, reverse=True)[1:2] != [col[i]]
        if row[j] >= threshold and max(col) == row[j] and unique_row and unique_col:
            pairs.append((rest.uuid.iloc[i], pool.canonical_id.iloc[j]))
    return pairs


def crosswalk(locs: pd.DataFrame, level: str, district_canon: dict | None = None) -> pd.DataFrame:
    """locs: non-total location rows (year, level, uuid, name, state_uuid, district_uuid).
    Returns (year, uuid, canonical_id, match_method)."""
    df = locs[locs.level == level].copy()
    df["n"] = df.name.map(norm_name)
    # name-based steps only compare locations of the same state AND unit type, so a Tamil Nadu firka is
    # never linked to a same-named taluk after the state switched granularity (MANDAL == BLOCK relabel).
    utype = df["unit_type"].fillna("").replace({"MANDAL": "BLOCK"}) if "unit_type" in df else ""
    df["scope"] = df.state_uuid.astype(str) + "|" + utype
    # parent key: for units, the *canonical* district if known, else the normalised district name
    if level == "unit":
        dnames = locs[locs.level == "district"].set_index(["year", "uuid"]).name.map(norm_name).to_dict()
        df["parent"] = [(district_canon or {}).get((y, d)) or dnames.get((y, d), "")
                        for y, d in zip(df.year, df.district_uuid)]
    else:
        df["parent"] = ""
    out = []
    known: dict[str, str] = {}        # uuid -> canonical
    seen = pd.DataFrame(columns=["canonical_id", "scope", "parent", "n"])  # canonical locations so far
    for year in sorted(df.year.unique(), reverse=True):
        cur = df[df.year == year]
        taken: set[str] = set()
        assigned = {}
        # 1. uuid
        for r in cur.itertuples():
            if r.uuid in known:
                assigned[r.uuid] = (known[r.uuid], "uuid")
                taken.add(known[r.uuid])
        rest = cur[~cur.uuid.isin(assigned)]
        pool = seen[~seen.canonical_id.isin(taken)]
        # 2. same state + parent + name, unique on both sides
        for keys, method in ((["scope", "parent", "n"], "name"), (["scope", "n"], "name_state")):
            if rest.empty or pool.empty:
                break
            pc = pool.groupby(keys).canonical_id.agg(list)
            rc = rest.groupby(keys).uuid.agg(list)
            for k, uu in rc.items():
                cands = pc.get(k)
                if len(uu) == 1 and cands is not None and len(cands) == 1 and cands[0] not in taken:
                    assigned[uu[0]] = (cands[0], method)
                    taken.add(cands[0])
            rest = rest[~rest.uuid.isin(assigned)]
            pool = pool[~pool.canonical_id.isin(taken)]
        # 4. fuzzy: same state + parent, mutual unique best string match (transliteration respellings,
        #    e.g. NOWGAON -> NOWGONG). Tagged so every such link can be audited.
        for key, grp in rest.groupby(["scope", "parent"]):
            cand = pool[(pool.scope == key[0]) & (pool.parent == key[1])]
            for u, cid in _mutual_best(grp, cand):
                assigned[u] = (cid, "fuzzy")
                taken.add(cid)
        rest = rest[~rest.uuid.isin(assigned)]
        for u in rest.uuid:
            assigned[u] = (u, "first_seen")
        for r in cur.itertuples():
            cid, how = assigned[r.uuid]
            known[r.uuid] = cid
            out.append((year, r.uuid, cid, how))
        latest_rows = cur.assign(canonical_id=[assigned[u][0] for u in cur.uuid])[["canonical_id", "scope", "parent", "n"]]
        seen = pd.concat([seen[~seen.canonical_id.isin(latest_rows.canonical_id)], latest_rows], ignore_index=True)
    return pd.DataFrame(out, columns=["year", "uuid", "canonical_id", "match_method"])
