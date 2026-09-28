import pandas as pd

from src.normalization.crosswalk import crosswalk, norm_name


def _locs(rows):
    return pd.DataFrame(rows, columns=["year", "level", "uuid", "name", "state_uuid", "district_uuid"])


def test_norm_name():
    assert norm_name("  Ludhiana-1 ") == "ludhiana 1"
    assert norm_name("Sidhwan_Bet") == norm_name("Sidhwan Bet")


def test_uuid_then_name_then_unmatched():
    rows = [
        # district D (stable uuid) in both years
        ("2023", "district", "D", "Dist", "S", "D"), ("2024", "district", "D", "Dist", "S", "D"),
        # unit A: same uuid
        ("2023", "unit", "a1", "Alpha", "S", "D"), ("2024", "unit", "a1", "Alpha", "S", "D"),
        # unit B: uuid re-issued, same name
        ("2023", "unit", "b_old", "Beta", "S", "D"), ("2024", "unit", "b_new", "BETA", "S", "D"),
        # unit C: renamed and re-issued -> must NOT be guessed
        ("2023", "unit", "c_old", "Gamma", "S", "D"), ("2024", "unit", "c_new", "Delta", "S", "D"),
    ]
    cw = crosswalk(_locs(rows), "unit").set_index(["year", "uuid"])
    assert cw.loc[("2023", "a1")].tolist() == ["a1", "uuid"]
    assert cw.loc[("2023", "b_old")].tolist() == ["b_new", "name"]
    assert cw.loc[("2023", "c_old")].match_method == "first_seen"
    assert cw.loc[("2024", "c_new")].canonical_id == "c_new"


def test_fuzzy_respelling_matched_within_district():
    rows = [
        ("2023", "district", "D", "Dist", "S", "D"), ("2024", "district", "D", "Dist", "S", "D"),
        ("2023", "unit", "o1", "NOWGAON", "S", "D"), ("2024", "unit", "n1", "NOWGONG", "S", "D"),
        ("2023", "unit", "o2", "SONKUTCH", "S", "D"), ("2024", "unit", "n2", "SONKATCH", "S", "D"),
    ]
    cw = crosswalk(_locs(rows), "unit").set_index(["year", "uuid"])
    assert cw.loc[("2023", "o1")].tolist() == ["n1", "fuzzy"]
    assert cw.loc[("2023", "o2")].tolist() == ["n2", "fuzzy"]


def test_ambiguous_names_not_matched():
    rows = [
        ("2023", "district", "D1", "One", "S", "D1"), ("2023", "district", "D2", "Two", "S", "D2"),
        ("2024", "district", "D3", "Three", "S", "D3"),
        ("2023", "unit", "x1", "Rajpur", "S", "D1"), ("2023", "unit", "x2", "Rajpur", "S", "D2"),
        ("2024", "unit", "y1", "Rajpur", "S", "D3"),
    ]
    cw = crosswalk(_locs(rows), "unit").set_index(["year", "uuid"])
    assert set(cw.loc["2023"].match_method) == {"first_seen"}


def test_name_state_fallback_when_district_renamed():
    rows = [
        ("2023", "district", "D1", "Old Dist", "S", "D1"), ("2024", "district", "D9", "New Dist", "S", "D9"),
        ("2023", "unit", "u_old", "Unique Block", "S", "D1"), ("2024", "unit", "u_new", "Unique Block", "S", "D9"),
    ]
    cw = crosswalk(_locs(rows), "unit").set_index(["year", "uuid"])
    assert cw.loc[("2023", "u_old")].tolist() == ["u_new", "name_state"]
