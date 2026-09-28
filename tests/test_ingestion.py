from src.ingestion.flatten import leaves, unit_type
from src.ingestion.ingres_api import children


def test_unit_type_plain_block():
    assert unit_type({"reportSummary": {"total": {"BLOCK": {"safe": 1}}}}) == "BLOCK"


def test_unit_type_skips_sub_units():
    # AP mandal: village breakdown listed first, the mandal itself is the sum-1 level
    rec = {"reportSummary": {"total": {"VILLAGE": {"safe": 15, "critical": 2}, "BLOCK": {"safe": 1}}}}
    assert unit_type(rec) == "BLOCK"


def test_unit_type_single_sub_unit_prefers_parent():
    rec = {"reportSummary": {"total": {"VILLAGE": {"safe": 1}, "BLOCK": {"safe": 1}}}}
    assert unit_type(rec) == "BLOCK"


def test_unit_type_missing():
    assert unit_type({"reportSummary": None}) is None


def test_leaves_flattens_and_drops_lists_and_nulls():
    got = dict(leaves({"a": {"b": 1.0, "c": None, "d": [1, 2]}, "e": "x"}))
    assert got == {"a.b": 1.0, "e": "x"}


def test_children_drops_total_row():
    assert children([{"locationName": "A"}, {"locationName": "total"}]) == [{"locationName": "A"}]
