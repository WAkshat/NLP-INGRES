import sqlite3

import pytest

from src.evaluation.execution import execution_match, is_ordered, results_match
from src.utils.safe_sql import connect_ro


def test_unordered_multiset_and_tolerance():
    assert results_match([["b", 2.0], ["a", 1]], [["a", 1.0], ["b", 2.0000000001]], ordered=False)
    assert not results_match([["a", 1]], [["a", 1], ["a", 1]], ordered=False)      # multiset, not set
    assert not results_match([["a", 1.1]], [["a", 1.0]], ordered=False)


def test_ordered_and_column_count():
    assert not results_match([["b"], ["a"]], [["a"], ["b"]], ordered=True)
    assert results_match([["a"], ["b"]], [["a"], ["b"]], ordered=True)
    assert not results_match([["a", 1]], [["a"]], ordered=False)


def test_is_ordered_ignores_inner_order_by():
    assert is_ordered("SELECT x FROM t ORDER BY x DESC LIMIT 3")
    assert not is_ordered("SELECT d FROM (SELECT d FROM t ORDER BY v LIMIT 3)")
    assert not is_ordered("SELECT COUNT(*) FROM t")


@pytest.fixture()
def con(tmp_path):
    w = sqlite3.connect(tmp_path / "t.db")
    w.executescript("CREATE TABLE t(x INT); INSERT INTO t VALUES (1),(2);")
    w.close()
    return connect_ro(tmp_path / "t.db")


def test_execution_match_errors_and_refusals(con):
    assert execution_match(con, "SELECT SUM(x) FROM t", "SELECT 3", [[3]]).correct
    assert execution_match(con, "SELEC x", "SELECT 3", [[3]]).error
    assert "refused" in execution_match(con, "DELETE FROM t", "SELECT 3", [[3]]).error
    assert execution_match(con, "", "SELECT 3", [[3]]).error == "no_sql"
