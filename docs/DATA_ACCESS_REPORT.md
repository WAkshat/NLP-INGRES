# INGRES Data-Access Report (Phase 1 gate)

_Audit date: 2026-09-28. All numbers below come from `reports/data_audit.json` (`python scripts/audit_data.py`),
`reports/crosswalk_*.csv` and queries on `data/processed/ingres.db` (`python scripts/build_schema.py`)._

## Verdict

**Viable.** Official INGRES assessment data can be pulled by script, without a login, at state,
district and assessment-unit level for five complete assessment cycles (GWRA 2020, 2022, 2023, 2024, 2025).
National aggregates computed from the extracted data reproduce the published national figures
(PIB releases) to within 0.1% for every cycle where a published figure could be located.
Cross-year analysis is feasible but **only with a crosswalk** and **only for states whose
assessment-unit granularity did not change** (see §8).

## 1. Where the data is hosted

| What | URL |
|---|---|
| Portal (Angular single-page app, title "GecDashboard") | https://ingres.iith.ac.in/home |
| Business-data endpoint (public, no auth) | `POST https://ingres.iith.ac.in/api/gec/getBusinessDataForUserOpen` |
| State hierarchy / assessment-unit type | `POST https://ingres.iith.ac.in/api/gec/stateHieAndAssmntData` body `{"st": <state uuid>, "aY": "<year>"}` |
| Location lists | `POST https://ingres.iith.ac.in/api/gec/parentChildType` body `{"pType","cType","puuid"}` (works COUNTRY→STATE; returned "No Child Location List" for district→block in AP) |
| CGWB assessment page (reports) | https://cgwb.gov.in/en/ground-water-resource-assessment-0 (TLS certificate chain failed verification from this machine) |

INGRES is a joint CGWB + IIT Hyderabad system implementing the GEC-2015 methodology.

## 2. Access method: what the portal exposes

| Format | Available? | Notes |
|---|---|---|
| Documented public API | **No** | No documentation found. A third-party paid wrapper exists (parse.bot); not used. |
| JS/API-backed JSON endpoints | **Yes** | Found by reading the portal's JS bundle (`main.617d2136bd981220a588.js`): `constants.API_URL = "https://ingres.iith.ac.in/api/"`, and `getTableDataforNonLogin()` posts to `gec/getBusinessDataForUserOpen` with no auth header. |
| Static HTML tables | No | The page HTML is an empty `<app-root>`; all content is rendered by JS. |
| CSV / Excel download | Not publicly | The bundle has `exceldownload` / `excelupload` only behind admin roles (`GEC_STATE_SUPER_ADMIN`, `GEC_FIELD_ADMIN`). |
| Database dump | No | — |
| PDF reports | Yes (portal + CGWB) | `gec/getReport` exists; national/state PDFs are published by CGWB. Not used, because the JSON API gives the same numbers in structured form. |

**The portal is JS-heavy**, but the data does not need a headless browser: plain HTTPS POSTs are enough.

### Request format
```json
{"parentLocName":"INDIA","locname":"<name>","loctype":"COUNTRY|STATE|DISTRICT","view":"admin",
 "locuuid":"<uuid>","year":"2024-2025","computationType":"normal","component":"recharge",
 "period":"annual","category":"safe","mapOnClickParams":"false","verificationStatus":1,
 "approvalLevel":1,"parentuuid":"<parent uuid>","stateuuid":null}
```
`loctype` is the type of the location being *opened*; the response lists its **children** plus a synthetic
`total` row: COUNTRY (uuid `ffce954d-24e1-494b-ba7e-0931d8ad6085`) → states, STATE → districts,
DISTRICT → assessment units. `category`, `component` and `period` did not filter the business values in our tests.

## 3. Raw-data format and extraction method
- Raw format: JSON list of location records. Each record holds nested objects: `rechargeData`
  (rainfall / canal / surface_irrigation / gw_irrigation / water_body / artificial_structure / pipeline /
  sewage / total, each split into command / non_command / poor_quality / total), `draftData` (extraction:
  agriculture / domestic / industry / total), `currentAvailabilityForAllPurposes`, `loss`,
  `availabilityForFutureUse`, `stageOfExtraction`, `gwallocation`, `area`, `rainfall`, `category`,
  `reportSummary`, plus unit-only `computationSummary`, `gwlevelData`, water-table trend fields.
- Extraction: `scripts/crawl_ingres.py` (`src/ingestion/ingres_api.py`) walks country → state → district
  for each year, sequentially, with a 0.5 s delay between requests. Every response is cached verbatim, gzipped, with its
  request body and timestamp (`data/raw/ingres_api/<year>/<LOCTYPE>_<uuid>.json.gz`); the crawl is
  resumable and atomic per file. Full crawl of 7 years: 5,299 requests, ~80 min (18:27-19:46 IST), **0 failed requests or retries**.
- Flattening: `src/ingestion/flatten.py` turns every scalar leaf into a long table
  (`data/interim/facts_long.parquet`, 6,217,844 rows, 235 distinct raw field paths) plus
  `locations.parquet`. `computationSummary` and `gwlevelData` (water-level series) are nested; they are kept only in raw.
- Snapshot: `python scripts/snapshot_raw.py pack` → `dist/ingres_raw_2026-09-28.tar` (139.4 MB, 5,299 files,
  per-file SHA-256 manifest; sha256 of tar `1da3b2c8…04ce7c`). `restore` re-extracts and verifies every file (tested).

## 4. Units (verified)
Quantities are in **hectare-metres (ham)**; 1 BCM = 10⁵ ham. Areas are in ha, rainfall in mm.
Verified by reconciliation (§7): state sums in ham / 10⁵ equal the published BCM figures.

## 5. Years found

| API label | = published report | States/UTs | Districts | Units | Status |
|---|---|---:|---:|---:|---|
| 2003-04, 2008-09, 2010-11, 2014-15 | — | — | — | — | labels exist in the JS; API returns nothing |
| 2012-2013 | GWRA 2013 | — | — | — | returns only 2 rows; unusable |
| 2016-2017 | GWRA 2017 | 33 | 668 | 5,279 | **excluded**: 4 states missing (Ladakh, Sikkim, Telangana, West Bengal), national totals ~2× published (recharge 839.6 vs 431.86 BCM published) |
| 2019-2020 | GWRA 2020 | 37 | 721 | 6,737 | included |
| 2021-2022 | GWRA 2022 | 37 | 746 | 7,168 | included |
| 2022-2023 | GWRA 2023 | 37 | 734 | 6,670 | included |
| 2023-2024 | GWRA 2024 | 37 | 730 | 6,965 | included |
| 2024-2025 | GWRA 2025 | 37 | 735 | 6,984 | included |
| 2025-2026 | GWRA 2026 (not yet published) | 35 | 705 | 6,354 | **excluded**: Andhra Pradesh and Lakshadweep missing; cycle likely in progress |

The mapping "API label YYYY-(YYYY+1) = GWRA report of year YYYY+1" is confirmed by matching national
stage of extraction and totals (§7). "37 states/UTs" is the INGRES list (it has Ladakh, and keeps Daman and Diu
separate from Dadra and Nagar Haveli).

## 6. Geographic hierarchy

The admin view is `COUNTRY → STATE → DISTRICT → assessment unit`. The unit type differs by state
(`stateHieAndAssmntData` gives each state's hierarchy):

| Unit type (2024-25) | States |
|---|---|
| BLOCK | most states; for AP / Telangana the "BLOCK" level is the **mandal** (labelled `MANDAL` in 2019-20) |
| TALUK | Goa, Gujarat, Karnataka, Maharashtra, Tamil Nadu, Puducherry |
| TEHSIL | Delhi |
| DISTRICT (district is its own unit) | Chandigarh, Dadra & Nagar Haveli, Daman & Diu; Lakshadweep islands (see below) |
| ISLAND / REGION / VALLEY | Andaman & Nicobar, Puducherry, Himachal Pradesh (earlier years) / Ladakh |

Sub-unit levels exist below the crawled level and were **not crawled**: villages (AP, Telangana), firkas
(Tamil Nadu from 2022-23 onward), watersheds (Maharashtra's primary "BASIN" view). The crawled level is the one
whose category shares match the published national shares: 2024-25 excluding Hilly Area is Safe 73.17% / Semi-Critical 11.15% /
Critical 2.99% / Over-Exploited 10.80% / Saline 1.89%, against the published 73.14 / 11.21 / 2.97 / 10.8 / 1.88.

Anomalies:
- **Himachal Pradesh** districts use 3-letter codes in INGRES (SLN, KIN, SRM, KNG, KUL, UNA, MND, SHM, BLS, CHM,
  LAS, HMP), and only some districts have units (HP assesses valley areas). Names are kept as in the source;
  code→name aliases belong in the entity-resolution gazetteer (Phase 6).
- **Lakshadweep** islands are returned as districts that carry their own category and metrics but no child units.
  The DB adds each such district as its own unit, flagged `is_district_as_unit = 1` (41 unit-year rows in total).
- "RANA AND KUTCH" (Gujarat) is a district-level entry with no metrics.

## 7. Reconciliation with published figures

Fresh groundwater = total − `poor_quality` (saline) component. Published figures are for fresh groundwater only.

| Cycle | Recharge BCM (DB / published) | Extractable | Extraction | Stage of extraction % | Source |
|---|---|---|---|---|---|
| GWRA 2020 | 436.20 / — | 397.68 / — | 244.92 / "245" | 61.59 / — | [PIB 1848469](https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1848469) (extraction only; other figures **not verified**) |
| GWRA 2022 | 437.61 / 437.60 | 398.09 / 398.08 | 239.18 / 239.16 | 60.08 / 60.08 | [PIB 1874808](https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=1874808) |
| GWRA 2023 | 449.05 / 449.08 | 407.19 / — | 241.31 / 241.34 | 59.26 / 59.23 | [PIB 1981600](https://www.pib.gov.in/PressReleaseIframePage.aspx?PRID=1981600) |
| GWRA 2024 | 446.58 / 446.90 | 406.18 / 406.19 | 245.65 / 245.64 | 60.48 / 60.47 | [PIB 2089039](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2089039) |
| GWRA 2025 | 448.51 / 448.52 | 407.76 / 407.75 | 247.22 / 247.22 | 60.63 / 60.63 | [PIB 2220203](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2220203) |

The largest deviation is 0.07% (GWRA 2024 recharge), which is consistent with post-publication revisions in INGRES.
These checks run as `tests/test_db_against_published.py`. Published assessment-unit counts: 7,089 (2022) and
6,553 (2023). The API has 7,168 and 6,670 units, or 7,044 and 6,512 excluding Hilly Area units. Counts therefore
agree to within about 1-2% but not exactly; the exact published counting rule is unknown.

Internal consistency:
- Sum of a state's districts = the state's reported value: 100% of states, every year, 0 difference.
- Unit sums vs reported district value (recharge): 97.8-98.8% of districts within 0.1% in the included years;
  the maximum relative difference is 0.85 (2019-20). A small number of districts' units do not sum to the district figure. **Cause unknown**.
- Category vs the official thresholds (Safe ≤70 < Semi-Critical ≤90 < Critical ≤100 < Over-Exploited): 100% agreement for
  2021-22 onward; 98.81% in 2019-20, where the mismatches are units just above a threshold (e.g. 70.04% labelled Safe).
  Presumably those were categorised before rounding.

## 8. Cross-year joinability and methodology comparability

**State UUIDs are stable. District and unit UUIDs are not always stable.** Several states re-issue every unit UUID
in a new cycle, which fits new boundary-shapefile versions (the bundle references `indgec_vers_<state>` layers).
Unit UUID Jaccard overlap between consecutive cycles: 2019-20→2021-22 **0.14**, 2021-22→2022-23 0.70,
2022-23→2023-24 0.71, 2023-24→2024-25 0.69. No UUID ever changed name, and no unit UUID moved to a different parent district.

`src/normalization/crosswalk.py` therefore assigns canonical cross-year ids. It walks backwards from 2024-25 and
matches in this order: (1) same UUID; (2) same state + unit type + parent district + normalised name;
(3) name unique within (state, unit type); (4) fuzzy: same state + unit type + district, mutual unique best
`SequenceMatcher` ratio ≥ 0.75, rejecting names that differ only by an added qualifier (split units such as
`SANGANER` → `SANGANER_RURAL`) or by a different ordinal (`…-II` vs `…-III`). Ambiguous candidates are never linked.

| Unit links (per cycle) | uuid | name | name_state | fuzzy | first_seen |
|---|---:|---:|---:|---:|---:|
| 2019-2020 | 1,716 | 4,189 | 218 | 280 | 334 |
| 2021-2022 | 5,691 | 164 | 15 | 0 | 1,298 |
| 2022-2023 | 5,655 | 895 | 0 | 11 | 109 |
| 2023-2024 | 5,697 | 1,223 | 7 | 25 | 13 |

Quality of fuzzy links: a random sample of 40 was reviewed by hand against district context
(`reports/crosswalk_fuzzy_review_sample.csv`). **37/40 were correct (92.5%, Wilson 95% CI 80.1-97.4%)**. One error
type (differing ordinals) is now blocked by a rule; two doubtful links remain (`KUSHESWARSTHAN (E)` →
`Kusheswar Asthan`, `SHAHNAGAR` → `SHAHGARH`). All 445 links whose name differs from the canonical name (309 fuzzy, 98 name_state, 38 name) are listed in `reports/crosswalk_renames.csv`.
Most are transliteration variants such as NOWGAON→NOWGONG, SONKUTCH→SONKATCH and BIHAR SHARIFF→Biharsharif, which makes them useful for the entity-resolution study.

Share of units in each cycle that link to a 2024-25 unit: 2019-20 74.3%, 2021-22 80.2%, 2022-23 98.2%,
2023-24 99.8%. 5,015 canonical units appear in all five cycles.

**Methodology and comparability concerns (these must be carried into any cross-year answer):**
1. **The assessment-unit granularity changed** in several states (see the `state_unit_granularity` table):
   Tamil Nadu firka (≈1,166) → taluk (≈314) from 2022-23; J&K district-level (20) → block (327) from 2023-24;
   Assam, Arunachal, Meghalaya and Nagaland district-level → block from 2022-23; Sikkim → block in 2024-25; Karnataka
   block → taluk from 2021-22; Uttarakhand 95 → 20 units in 2023-24; HP valleys vary. Units in these states **cannot be
   compared across the change**. Their 2019-20→2024-25 link rate is 0%, by design.
2. District reorganisations (e.g. the new MP districts Mauganj, Pandhurna and Maihar seen in the crosswalk; AP units 331 → 635 between
   2019-20 and 2021-22) change district
   aggregates even when units are unchanged. Unit-level comparisons via canonical ids are safer than district-level ones.
3. All included cycles use GEC-2015, but input data, parameters and boundaries are revised every cycle. Differences
   are "historical change detection under methodology comparability constraints", **not trends or forecasts**.
4. `Hilly Area` units have no extraction or stage-of-extraction values (structural, not missing data).

## 9. Missing values (assessment-unit level, share of units lacking the field)

| Field | 2019-20 | 2021-22 | 2022-23 | 2023-24 | 2024-25 |
|---|---:|---:|---:|---:|---:|
| annual recharge | 1.41% | 1.80% | 1.66% | 0.03% | 0.04% |
| extractable resource | 0 | 0.01% | 0.01% | 0.01% | 0 |
| extraction (total) / stage of extraction | 1.80% | 1.73% | 2.37% | 3.73% | 3.72% |
| extraction for irrigation / domestic / industrial | 1.23% | ≈1.1% | ≈0 | ≈0 | ≈0 |
| rainfall | 5.39% | 1.80% | 1.65% | 0.03% | 0.04% |
| category | 0 | 0.01% | 0.01% | 0.01% | 0 |

The missing extraction values in 2023-25 are exactly the Hilly Area units (260 in 2024-25). Zero values are common for
industrial extraction (33-56% of units per year). This matches the source and should not be read as missing data.

**Poor-quality columns:** the API leaves out the `poor_quality` key when a location has no saline component (absent for 68%
of state rows). Left as NULL, `SUM(total - poor_quality)` silently drops those rows, which produced a wrong national extraction of
128 BCM in a first test. The DB therefore stores 0 when the parent metric exists and the poor-quality key is absent.
The raw absence is preserved in `interim/`.

## 10. Duplicates
- Duplicate (year, level, UUID) rows: **0**.
- Name ambiguity (2024-25): 235 unit names are shared by more than one unit, 232 across different districts and **169 across different states**
  (`ramnagar` ×10; `kalyanpur`, `patan` ×6; `maharajganj`, `ramgarh`, `rajpur`, … ×5). District names in two states:
  Balrampur, Pratapgarh. 360 units have exactly the same name as their own district (block vs district ambiguity).
  This is real ambiguity that INGRES-Bench and entity resolution must handle.

## 11. Encoding and name hygiene
- All names are ASCII; no mojibake, non-NFC or non-ASCII names were found.
- 387 names contain underscores, brackets or other unusual punctuation (`ONGOLE_RURAL`, `ADONI_1`, `Ganpur_stn`,
  `ANDAL ( ANDAL+PANDAB`); 12 contain double spaces (`UDHAGA  MANDALAM`). One name is truncated in 2019-20
  (`KHARCHI (MARWAR JUNC`).
- Casing is inconsistent between states: UPPER in some (e.g. `MAUGANJ`), Title in others (e.g. `Ludhiana`). Values are kept
  **as in the source**; case-insensitive matching is the query layer's job.
- State spellings are INGRES's own: `TAMILNADU`, `LAKSHDWEEP`.

## 12. Canonical database
`data/processed/ingres.db` (SQLite, 21.8 MB) with 5 cycles, 37 states, 770 canonical districts, 8,751 canonical units
and 34,565 unit-year rows. Tables: `assessment_years`, `states`, `districts`, `assessment_units`, `state_assessments`,
`district_assessments`, `unit_assessments`, `state_unit_granularity`, `location_crosswalk`.
Documentation: `docs/INGRES_SCHEMA.md` and `data/schema/schema.json` (descriptions, units, null rates, example values;
descriptions inferred only from field names are marked **UNCERTAIN**).

## 13. Limitations
- Relies on an undocumented endpoint; it may change without notice. The raw snapshot plus manifest makes the current dataset reproducible.
- The crawled level is one level above villages (AP, Telangana), firkas (Tamil Nadu 2022-23+) and watersheds (Maharashtra).
- The GWRA 2020 national figures (other than extraction ≈245 BCM) were not verified against a primary source.
- The cause of the ~1.5% of districts whose units do not sum to the district value is unknown.
- Fuzzy crosswalk links have an estimated precision of 92.5% (n=40). They make up ~1% of all links.
- Field semantics for `pipeline` / `sewage` recharge, domestic allocation and rainfall averaging are inferred from names only (marked UNCERTAIN).

## Reproduce
```bash
python scripts/crawl_ingres.py --years 2019-2020 2021-2022 2022-2023 2023-2024 2024-2025   # or restore the snapshot:
python scripts/snapshot_raw.py restore dist/ingres_raw_2026-09-28.tar
python scripts/audit_data.py
python scripts/build_schema.py
python -m pytest
```
