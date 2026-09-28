import sqlite3

import pytest

from src.utils.safe_sql import UnsafeSQL, connect_ro, execute


@pytest.fixture()
def con(tmp_path):
    db = tmp_path / "t.db"
    w = sqlite3.connect(db)
    w.executescript("CREATE TABLE states(state_id TEXT, state_name TEXT);"
                    "INSERT INTO states VALUES ('a','PUNJAB'),('b','HARYANA');")
    w.close()
    return connect_ro(db)


def test_select_and_cte_allowed(con):
    assert execute(con, "SELECT COUNT(*) FROM states").rows == [(2,)]
    r = execute(con, "WITH x AS (SELECT state_name FROM states) SELECT * FROM x ORDER BY 1")
    assert r.rows == [("HARYANA",), ("PUNJAB",)] and r.columns == ["state_name"]
    assert execute(con, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n WHERE i<3) SELECT * FROM n").rows == [(1,), (2,), (3,)]


@pytest.mark.parametrize("sql", [
    "DROP TABLE states",
    "DELETE FROM states",
    "UPDATE states SET state_name='x'",
    "INSERT INTO states VALUES ('c','GOA')",
    "ALTER TABLE states ADD COLUMN x",
    "CREATE TABLE t(x)",
    "ATTACH DATABASE 'evil.db' AS e",
    "PRAGMA writable_schema=1",
    "PRAGMA table_info(states)",
    "SELECT 1; DROP TABLE states",
    "SELECT * FROM states WHERE state_name='x'; DELETE FROM states",
    "SELECT load_extension('evil')",
    "VACUUM INTO 'copy.db'",
])
def test_injection_and_writes_rejected(con, sql):
    with pytest.raises(UnsafeSQL):
        execute(con, sql)
    assert execute(con, "SELECT COUNT(*) FROM states").rows == [(2,)]


def test_syntax_error_is_reported_not_raised(con):
    r = execute(con, "SELEC nonsense")
    assert r.error and not r.rows


def test_timeout(con):
    r = execute(con, "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n) SELECT COUNT(*) FROM n", timeout_s=0.2)
    assert r.error and "interrupt" in r.error.lower()


def test_row_cap(con):
    r = execute(con, "SELECT * FROM states", max_rows=1)
    assert r.truncated and len(r.rows) == 1
