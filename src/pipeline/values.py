"""Value snapping: make every place-name literal in generated SQL an exact database value.

The LLM is given the exact spelling (place hints) but often rewrites it: 'Mahabubabad' -> 'MAHABUBABAD',
'E LUNGDAR' -> 'E Lungdah'. SQLite '=' is case-sensitive and a COUNT over zero rows returns 0 rather than an error,
so the repair loop never sees these failures. Before execution, each literal compared with state_name /
district_name / unit_name is checked against that column:
  1. exact value exists                       -> unchanged
  2. one case-insensitive match               -> replaced by the stored spelling
     several (e.g. 'KUDLIGI' and 'Kudligi')   -> replaced by the variant the place linker resolved, else the
                                                 comparison is made case-insensitive (COLLATE NOCASE)
  3. no match                                 -> the closest stored name of that level by folded similarity,
                                                 if similarity >= MIN_SIM and the runner-up is clearly worse
Every change is returned so the UI and the logs can show it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher, get_close_matches

from src.entity_resolution.gazetteer import fold

COLUMNS = {"state_name": ("states", "state"), "district_name": ("districts", "district"), "unit_name": ("assessment_units", "unit")}
_LIT = r"'((?:[^']|'')*)'"
# alias.col = 'x' | alias.col IN ('x', 'y') | UPPER(alias.col) = UPPER('x') ; LIKE patterns with % are left alone
_EQ = re.compile(rf"(?P<lhs>(?:UPPER|LOWER)\(\s*(?:\w+\.)?(?P<c1>state_name|district_name|unit_name)\s*\)|(?:\w+\.)?(?P<c2>state_name|district_name|unit_name))"
                 rf"\s*(?P<op>=|LIKE)\s*(?P<rhs>(?:UPPER|LOWER)\(\s*{_LIT}\s*\)|{_LIT})", re.I)
_IN = re.compile(rf"(?P<lhs>(?:\w+\.)?(?P<col>state_name|district_name|unit_name))\s+IN\s*\((?P<items>\s*{_LIT}(?:\s*,\s*{_LIT})*\s*)\)", re.I)
MIN_SIM = 0.80          # folded-string similarity needed to replace an unknown name
MARGIN = 0.05           # best must beat the runner-up by this much


class ValueSnapper:
    def __init__(self, con):
        self.exact, self.by_upper, self.by_fold = {}, {}, {}
        for col, (table, _) in COLUMNS.items():
            names = [r[0] for r in con.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IS NOT NULL")]
            self.exact[col] = set(names)
            up, fo = defaultdict(set), defaultdict(set)
            for n in names:
                up[n.upper()].add(n)
                fo[fold(n)].add(n)
            self.by_upper[col], self.by_fold[col] = up, fo

    def _snap(self, col: str, lit: str, prefer: set[str]):
        """(new literal or None, how). None means: make the comparison case-insensitive instead."""
        if lit in self.exact[col]:
            return lit, "exact"
        variants = self.by_upper[col].get(lit.upper(), set())
        if len(variants) == 1:
            return next(iter(variants)), "case"
        if variants:
            hit = variants & prefer
            return (next(iter(hit)), "case") if len(hit) == 1 else (None, "nocase")
        f = fold(lit)
        if f in self.by_fold[col] and len(self.by_fold[col][f]) == 1:
            return next(iter(self.by_fold[col][f])), "spelling"
        cands = get_close_matches(f, list(self.by_fold[col]), n=2, cutoff=MIN_SIM)
        if cands:
            best = SequenceMatcher(None, f, cands[0]).ratio()
            second = SequenceMatcher(None, f, cands[1]).ratio() if len(cands) > 1 else 0.0
            names = self.by_fold[col][cands[0]]
            if best - second >= MARGIN or names & prefer:
                pick = (names & prefer) or names
                if len(pick) == 1:
                    return next(iter(pick)), "spelling"
        return lit, "unknown"

    def snap(self, sql: str | None, places: list[dict] | None = None) -> tuple[str | None, list[dict]]:
        if not sql:
            return sql, []
        prefer = defaultdict(set)
        for p in places or []:
            prefer[{"state": "state_name", "district": "district_name", "unit": "unit_name"}[p["level"]]].add(p["db_name"])
        changes = []

        def eq(m):
            col = (m.group("c1") or m.group("c2")).lower()
            lit = (m.group(6) if m.group(6) is not None else m.group(7)).replace("''", "'")
            if m.group("op").upper() == "LIKE" and ("%" in lit or "_" in lit):
                return m.group(0)
            new, how = self._snap(col, lit, prefer[col])
            if how in ("exact", "unknown"):
                return m.group(0)
            changes.append({"column": col, "from": lit, "to": new, "how": how})
            if new is None:                       # ambiguous casing: compare case-insensitively
                return f"{m.group('lhs')} = '{lit.replace(chr(39), chr(39) * 2)}' COLLATE NOCASE"
            return f"{m.group('lhs')} {m.group('op')} " + m.group("rhs").replace(m.group(6) if m.group(6) is not None else m.group(7), new.replace("'", "''"), 1)

        def isin(m):
            col = m.group("col").lower()
            items = re.findall(_LIT, m.group("items"))
            out = []
            for it in items:
                lit = it.replace("''", "'")
                new, how = self._snap(col, lit, prefer[col])
                if how not in ("exact", "unknown") and new is not None:
                    changes.append({"column": col, "from": lit, "to": new, "how": how})
                    lit = new
                out.append("'" + lit.replace("'", "''") + "'")
            return f"{m.group('lhs')} IN ({', '.join(out)})"
        sql = _EQ.sub(eq, sql)
        sql = _IN.sub(isin, sql)
        return sql, changes
