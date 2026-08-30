"""
F051 P02 — ReportCsvService Tests (15 tests)
==============================================

Covers: issue_summary_csv, incident_summary_csv generation.
"""

from __future__ import annotations

import pytest
from app.services.reporting.report_csv_service import ReportCsvService
from app.services.reporting.report_models import (
    IncidentDashboardSummary,
    IncidentPriorityCounts,
    IncidentSeverityCounts,
    IncidentStatusCounts,
    IssueDashboardSummary,
    IssueSeverityCounts,
    IssueStatusCounts,
    ResolutionTimeStats,
)


def _issue_summary(**overrides) -> IssueDashboardSummary:
    defaults = dict(
        status_counts=IssueStatusCounts(open=5, resolved=3, closed=2),
        severity_counts=IssueSeverityCounts(critical=1, major=2, minor=4, info=3),
        overdue_count=2,
        resolution_stats=ResolutionTimeStats(
            avg_hours=4.5, median_hours=3.0, p95_hours=12.0, total_resolved=3
        ),
    )
    defaults.update(overrides)
    return IssueDashboardSummary(**defaults)


def _incident_summary(**overrides) -> IncidentDashboardSummary:
    defaults = dict(
        status_counts=IncidentStatusCounts(open=3, acknowledged=1, resolved=2, closed=1),
        severity_counts=IncidentSeverityCounts(critical=2, major=1, minor=3, info=1),
        priority_counts=IncidentPriorityCounts(p1=2, p2=1, p3=3, p4=1),
        sla_breach_count=1,
        resolution_stats=ResolutionTimeStats(
            avg_hours=6.0, median_hours=5.0, p95_hours=18.0, total_resolved=2
        ),
    )
    defaults.update(overrides)
    return IncidentDashboardSummary(**defaults)


# ── Issue Summary CSV ────────────────────────────────────────────────────────


class TestIssueSummaryCsv:
    def test_has_header(self):
        svc = ReportCsvService()
        data = svc.issue_summary_csv(_issue_summary())
        text = data.decode("utf-8-sig")
        assert "Issue Dashboard Summary" in text

    def test_status_section(self):
        svc = ReportCsvService()
        data = svc.issue_summary_csv(_issue_summary())
        text = data.decode("utf-8-sig")
        assert "open,5" in text
        assert "resolved,3" in text
        assert "closed,2" in text

    def test_severity_section(self):
        svc = ReportCsvService()
        data = svc.issue_summary_csv(_issue_summary())
        text = data.decode("utf-8-sig")
        assert "critical,1" in text
        assert "major,2" in text

    def test_overdue_count(self):
        svc = ReportCsvService()
        data = svc.issue_summary_csv(_issue_summary())
        text = data.decode("utf-8-sig")
        assert "Overdue Count,2" in text

    def test_resolution_stats(self):
        svc = ReportCsvService()
        data = svc.issue_summary_csv(_issue_summary())
        text = data.decode("utf-8-sig")
        assert "avg_hours,4.5" in text
        assert "total_resolved,3" in text

    def test_includes_bom(self):
        svc = ReportCsvService()
        data = svc.issue_summary_csv(_issue_summary())
        assert data[:3] == b"\xef\xbb\xbf"

    def test_empty_summary(self):
        svc = ReportCsvService()
        summary = IssueDashboardSummary(
            status_counts=IssueStatusCounts(),
            severity_counts=IssueSeverityCounts(),
            overdue_count=0,
            resolution_stats=ResolutionTimeStats(),
        )
        data = svc.issue_summary_csv(summary)
        text = data.decode("utf-8-sig")
        assert "open,0" in text


# ── Incident Summary CSV ─────────────────────────────────────────────────────


class TestIncidentSummaryCsv:
    def test_has_header(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        text = data.decode("utf-8-sig")
        assert "Incident Dashboard Summary" in text

    def test_status_section(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        text = data.decode("utf-8-sig")
        assert "open,3" in text
        assert "acknowledged,1" in text

    def test_severity_section(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        text = data.decode("utf-8-sig")
        assert "critical,2" in text

    def test_priority_section(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        text = data.decode("utf-8-sig")
        assert "p1,2" in text
        assert "p4,1" in text

    def test_sla_breach(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        text = data.decode("utf-8-sig")
        assert "SLA Breach Count,1" in text

    def test_resolution_stats(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        text = data.decode("utf-8-sig")
        assert "avg_hours,6.0" in text
        assert "total_resolved,2" in text

    def test_includes_bom(self):
        svc = ReportCsvService()
        data = svc.incident_summary_csv(_incident_summary())
        assert data[:3] == b"\xef\xbb\xbf"

    def test_empty_summary(self):
        svc = ReportCsvService()
        summary = IncidentDashboardSummary(
            status_counts=IncidentStatusCounts(),
            severity_counts=IncidentSeverityCounts(),
            priority_counts=IncidentPriorityCounts(),
            sla_breach_count=0,
            resolution_stats=ResolutionTimeStats(),
        )
        data = svc.incident_summary_csv(summary)
        text = data.decode("utf-8-sig")
        assert "open,0" in text
