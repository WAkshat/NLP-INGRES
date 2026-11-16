"""Regression tests for the fixes made after the baseline-v1 audit (docs/00_INGRES_BASELINE_AUDIT.md)."""
from src.entity_resolution.gazetteer import Entity, devoice, fold, romanise
from src.entity_resolution.resolver import Resolver
from src.pipeline.years import render, year_labels


def test_tamil_romanisation_is_unvoiced_not_aspirated():          # audit B1: was 'gharnadhagha'
    assert romanise("கர்நாடகா") == "karnaatakaa"
    assert fold("கர்நாடகா") == fold("Karnataka")
    assert romanise("மதிப்பீட்டில்").startswith("matipp")


def test_devoiced_forms_match_across_scripts():
    for ta, en in (("சென்னை", "Chennai"), ("தூத்துக்குடி", "Thoothukudi"), ("பகல்பூர்", "Bhagalpur")):
        assert devoice(fold(ta)) == devoice(fold(en)), (ta, en)


def test_anusvara_is_homorganic():                                 # audit B4: was 'bamgala'
    assert romanise("बंगाल") == "bangala"
    assert romanise("चंपा").startswith("camp")


def test_resolver_ranks_tamil_script_state_first():
    gaz = [Entity("1", "state", "KARNATAKA", "Karnataka", "KARNATAKA", None, {"KARNATAKA", "Karnataka"}),
           Entity("2", "district", "Gadag", "Gadag", "KARNATAKA", "Gadag", {"Gadag"}),
           Entity("3", "state", "KERALA", "Kerala", "KERALA", None, {"KERALA", "Kerala"})]
    r = Resolver(gaz)                                               # no embedder, no ranker: string features only
    assert r.resolve("கர்நாடகா", k=1)[0][0].db_name == "KARNATAKA"
    assert r.resolve("Karnatak", k=1)[0][0].db_name == "KARNATAKA"


def test_year_labels():
    assert year_labels("How many blocks were safe in 2024-25?") == ["2024-2025"]
    assert year_labels("2025 ke assessment mein kitne units critical the?") == ["2024-2025"]
    assert year_labels("2023 के आकलन में पंजाब") == ["2022-2023"]
    assert year_labels("ஹரியானா மாநிலத்தில் 2025 மதிப்பீட்டில்") == ["2024-2025"]
    assert year_labels("from 2019-20 to 2024-2025") == ["2019-2020", "2024-2025"]
    assert year_labels("२०२४-२५ में") == ["2024-2025"]
    assert year_labels("blocks above 70% in Punjab") == [] and year_labels("in 2020-21") == []   # not an INGRES cycle
    assert render([]) == "" and "'2024-2025'" in render(["2024-2025"])


def test_error_category_looks_at_the_sql_not_the_linker():         # audit B3
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("rp", Path(__file__).parents[1] / "scripts/run_pipeline.py")
    rp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rp)
    gold = {"sql": "SELECT ua.category FROM x WHERE s.state_name = 'PUNJAB' AND ua.assessment_year = '2024-2025'",
            "entities": [{"db_name": "PUNJAB"}]}
    row = {"exec_error": None, "places_ok": 0,
           "sql": "SELECT ua.category FROM x WHERE s.state_name = 'PUNJAB' AND ua.assessment_year = '2023-2024'"}
    assert rp.error_category(row, gold) == "wrong assessment year"
    assert rp.error_category({**row, "sql": "SELECT 1"}, gold) == "gold place literal missing from SQL"
