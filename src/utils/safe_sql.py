"""Read-only SQL execution against ingres.db.

Defence in depth, all stdlib:
  1. connection opened with `mode=ro` (SQLite refuses writes at the file level)
  2. sqlite3 authorizer allowing only SELECT / READ / FUNCTION / RECURSIVE (CTEs);
     everything else (INSERT, UPDATE, DELETE, DROP, ATTACH, PRAGMA, CREATE ...) is denied
     at prepare time, so no string-matching bypass is possible
  3. a single statement only (sqlite3.execute already rejects multiple statements)
  4. a progress-handler timeout and a row cap
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
_DENIED_FUNCS = {"load_extension", "readfile", "writefile", "fts3_tokenizer"}


class UnsafeSQL(Exception):
    pass


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    elapsed_s: float = 0.0
    error: str | None = None
    meta: dict = field(default_factory=dict)


def _authorizer(action, arg1, arg2, dbname, source):
    if action not in _ALLOWED:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _DENIED_FUNCS:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def connect_ro(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, check_same_thread=False)
    con.set_authorizer(_authorizer)
    return con


def execute(con: sqlite3.Connection, sql: str, max_rows: int = 10_000, timeout_s: float = 10.0) -> QueryResult:
    """Run one read-only statement. Raises UnsafeSQL for anything the authorizer denies."""
    t0 = time.perf_counter()
    deadline = t0 + timeout_s
    con.set_progress_handler(lambda: int(time.perf_counter() > deadline), 10_000)
    try:
        cur = con.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
    except sqlite3.DatabaseError as e:
        msg = str(e)
        if any(k in msg for k in ("not authorized", "authorization denied", "readonly", "one statement at a time")):
            raise UnsafeSQL(msg) from e
        return QueryResult([], [], error=f"{type(e).__name__}: {e}", elapsed_s=time.perf_counter() - t0)
    finally:
        con.set_progress_handler(None, 0)
    cols = [d[0] for d in cur.description or []]
    return QueryResult(cols, rows[:max_rows], truncated=len(rows) > max_rows, elapsed_s=time.perf_counter() - t0)
