"""Execution accuracy (EX), Spider/BIRD-style, as specified in docs/INGRES_BENCH.md §7.

A prediction is correct iff its SQL executes (read-only) and its result equals the gold result:
multiset of rows (order-sensitive only when the gold SQL has ORDER BY), same number of columns,
numbers equal within tolerance, strings equal exactly.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from src.utils.safe_sql import UnsafeSQL, execute

REL_TOL, ABS_TOL = 1e-6, 1e-9


def _norm_cell(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return float(v)
    return v


def cells_equal(a, b) -> bool:
    a, b = _norm_cell(a), _norm_cell(b)
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def rows_equal(r1, r2) -> bool:
    return len(r1) == len(r2) and all(cells_equal(a, b) for a, b in zip(r1, r2))


def results_match(pred: list, gold: list, ordered: bool) -> bool:
    if len(pred) != len(gold):
        return False
    if gold and pred and len(pred[0]) != len(gold[0]):
        return False
    if ordered:
        return all(rows_equal(p, g) for p, g in zip(pred, gold))
    remaining = list(gold)  # multiset match with tolerance (results are small; O(n^2) is fine)
    for p in pred:
        for i, g in enumerate(remaining):
            if rows_equal(p, g):
                del remaining[i]
                break
        else:
            return False
    return True


def is_ordered(gold_sql: str) -> bool:
    # only the outermost ORDER BY matters; ORDER BY inside a CTE/subquery with LIMIT still yields a set
    return bool(re.search(r"\bORDER\s+BY\b(?![^()]*\))", gold_sql, re.I))


@dataclass
class ExResult:
    correct: bool
    error: str | None = None          # execution error / refusal / empty prediction
    n_rows: int | None = None


def execution_match(con, pred_sql: str | None, gold_sql: str, gold_rows: list) -> ExResult:
    if not pred_sql or not pred_sql.strip():
        return ExResult(False, "no_sql")
    try:
        res = execute(con, pred_sql)
    except UnsafeSQL as e:
        return ExResult(False, f"refused: {e}")
    if res.error:
        return ExResult(False, res.error)
    rows = [list(r) for r in res.rows]
    return ExResult(results_match(rows, gold_rows, is_ordered(gold_sql)), None, len(rows))
