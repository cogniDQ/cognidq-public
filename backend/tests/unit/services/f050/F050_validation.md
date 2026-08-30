# F050 — Issue and Incident Reporting — Validation Record

## Feature
**ID:** F050
**Title:** Issue and Incident Reporting
**Priority:** 29
**Dependencies:** F042 ✅, F052 ✅

## Packets

| Packet | Description | Tests | Status |
|--------|------------|-------|--------|
| P01 | Pydantic Models + IssueReportService | 15/15 ✅ | PASS |
| P02 | IncidentReportService | 15/15 ✅ | PASS |
| P03 | API Endpoints | 15/15 ✅ | PASS |

## Test Results

- **Feature tests:** 45/45 passed (0.81s)
- **Regression:** 1982 passed, 2 skipped, 0 failed (15.66s)
- **Pre-existing exclusions:** 6 LLM tests (ignored)

## Files Created

### Models
- `backend/app/services/reporting/report_models.py` — 8 Pydantic models (IssueStatusCounts, IssueSeverityCounts, ResolutionTimeStats, IssueDashboardSummary, IncidentStatusCounts, IncidentSeverityCounts, IncidentPriorityCounts, IncidentDashboardSummary)

### Services
- `backend/app/services/reporting/issue_report_service.py` — IssueReportService (count_by_status, count_by_severity, count_overdue, resolution_time_stats, dashboard_summary)
- `backend/app/services/reporting/incident_report_service.py` — IncidentReportService (count_by_status, count_by_severity, count_by_priority, sla_breach_count, resolution_time_stats, dashboard_summary)

### Endpoints
- `backend/app/api/v1/endpoints/issue_incident_reports.py` — 5 GET routes under /workspaces/{ws}/reports/

### Tests
- `backend/tests/unit/services/f050/test_p01_models_issue_report.py` — 15 tests
- `backend/tests/unit/services/f050/test_p02_incident_report.py` — 15 tests
- `backend/tests/unit/services/f050/test_p03_api.py` — 15 tests

## Notes
- Read-only analytics feature — no migration needed
- SLA breach detection via 3-table join (Incident → IncidentIssue → Issue)
- Resolution time stats: avg, median, p95 percentile computation in Python
