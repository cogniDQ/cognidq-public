# F051 — CSV Export for Lists and Reports — Validation Record

## Feature
**ID:** F051
**Title:** CSV Export for Lists and Reports
**Priority:** 30
**Dependencies:** F050 ✅, F007 ✅, F037 ✅ (issue CSV), F042 ✅ (incident list)

## Packets

| Packet | Description | Tests | Status |
|--------|------------|-------|--------|
| P01 | IncidentCsvService + Repository Extension | 15/15 ✅ | PASS |
| P02 | ReportCsvService | 15/15 ✅ | PASS |
| P03 | API Endpoints | 15/15 ✅ | PASS |

## Test Results

- **Feature tests:** 45/45 passed (2.35s)
- **Regression:** 2027 passed, 2 skipped, 0 failed (16.99s)
- **Pre-existing exclusions:** 6 LLM tests (ignored)

## Files Created / Modified

### New Files
- `backend/app/services/incidents/incident_csv_service.py` — IncidentCsvService (formula injection defense, UTF-8 BOM, CSV generation)
- `backend/app/services/reporting/report_csv_service.py` — ReportCsvService (issue_summary_csv, incident_summary_csv)
- `backend/tests/unit/services/f051/test_p01_incident_csv.py` — 15 tests
- `backend/tests/unit/services/f051/test_p02_report_csv.py` — 15 tests
- `backend/tests/unit/services/f051/test_p03_api.py` — 15 tests

### Modified Files
- `backend/app/services/incidents/incident_repository.py` — Added `list_all_for_export()` (10k row cap)
- `backend/app/api/v1/endpoints/incidents.py` — Added `GET /incidents/export` endpoint
- `backend/app/api/v1/endpoints/issue_incident_reports.py` — Added `GET /reports/issues/export` and `GET /reports/incidents/export`

## Endpoints Added
| Method | Path | Description |
|--------|------|-------------|
| GET | /workspaces/{ws}/incidents/export | Incident list CSV export |
| GET | /workspaces/{ws}/reports/issues/export | Issue dashboard summary CSV |
| GET | /workspaces/{ws}/reports/incidents/export | Incident dashboard summary CSV |

## Security
- Formula injection defense via `safe_csv_value()` — prefixes `=+-@` with single quote
- UTF-8 BOM for Excel compatibility
- 10,000 row cap with truncation notice
