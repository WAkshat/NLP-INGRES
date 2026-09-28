"""Data-validation tests: the canonical DB must reproduce officially published national figures.
Skipped when data/processed/ingres.db has not been built (python scripts/build_schema.py)."""
from pathlib import Path

import pytest

from src.utils.safe_sql import connect_ro, execute

DB = Path(__file__).resolve().parents[1] / "data/processed/ingres.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="ingres.db not built")

# PIB press releases (see docs/DATA_ACCESS_REPORT.md); fresh groundwater, BCM
PUBLISHED = {
    "2021-2022": dict(recharge=437.60, extractable=398.08, extraction=239.16, soe=60.08),
    "2022-2023": dict(recharge=449.08, extraction=241.34, soe=59.23),
    "2023-2024": dict(recharge=446.90, extractable=406.19, extraction=245.64, soe=60.47),
    "2024-2025": dict(recharge=448.52, extractable=407.75, extraction=247.22, soe=60.63),
}
SQL = """SELECT SUM(annual_recharge_ham - recharge_poor_quality_ham) / 1e5,
                SUM(extractable_resource_ham - extractable_poor_quality_ham) / 1e5,
                SUM(extraction_total_ham - extraction_poor_quality_ham) / 1e5
         FROM state_assessments WHERE assessment_year = '{y}'"""


@pytest.mark.parametrize("year", PUBLISHED)
def test_national_totals_match_published(year):
    recharge, extractable, extraction = execute(connect_ro(DB), SQL.format(y=year)).rows[0]
    got = dict(recharge=recharge, extractable=extractable, extraction=extraction, soe=100 * extraction / extractable)
    for k, want in PUBLISHED[year].items():
        # INGRES values may be revised after publication: allow 0.1% (0.35 BCM on recharge 2023-24 is the worst case)
        assert got[k] == pytest.approx(want, rel=1e-3), (year, k, got[k], want)


def test_unit_categories_follow_soe_thresholds():
    rows = execute(connect_ro(DB), """SELECT category, stage_of_extraction_pct FROM unit_assessments
        WHERE assessment_year >= '2021-2022' AND category IN ('Safe','Semi-Critical','Critical','Over-Exploited')""").rows
    expect = lambda s: "Safe" if s <= 70 else "Semi-Critical" if s <= 90 else "Critical" if s <= 100 else "Over-Exploited"  # noqa: E731
    assert all(expect(s) == c for c, s in rows)


def test_foreign_keys_and_cross_year_link():
    con = connect_ro(DB)
    # every unit-year row points at a known unit; Punjab blocks link across all five cycles
    assert execute(con, "SELECT COUNT(*) FROM unit_assessments WHERE unit_id NOT IN (SELECT unit_id FROM assessment_units)").rows == [(0,)]
    n = execute(con, """SELECT COUNT(*) FROM (SELECT ua.unit_id FROM unit_assessments ua JOIN assessment_units u USING(unit_id)
        JOIN states s ON s.state_id = u.state_id WHERE s.state_name = 'PUNJAB' GROUP BY ua.unit_id
        HAVING COUNT(DISTINCT ua.assessment_year) = 5)""").rows[0][0]
    assert n >= 140
