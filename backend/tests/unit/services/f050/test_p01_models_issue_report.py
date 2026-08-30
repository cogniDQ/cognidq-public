"""
F050 P01 — Pydantic Models + IssueReportService Tests (15 tests)
=================================================================

Covers report Pydantic models and IssueReportService aggregation methods.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.services.reporting.issue_report_service import IssueReportService
from app.services.reporting.report_models import (
    IssueDashboardSummary,
    IssueSeverityCounts,
    IssueStatusCounts,
    ResolutionTimeStats,
)

_WS = uuid4()


def _mock_db():
    return MagicMock()


SVC_MODULE = "app.services.reporting.issue_report_service"


# ── Pydantic Model Tests ────────────────────────────────────────────────────


class TestPydanticModels:
    def test_issue_status_counts_defaults(self):
        counts = IssueStatusCounts()
        assert counts.open == 0
        assert counts.resolved == 0
        assert counts.closed == 0

    def test_issue_severity_counts_defaults(self):
        counts = IssueSeverityCounts()
        assert counts.critical == 0
        assert counts.major == 0
        assert counts.minor == 0
        assert counts.info == 0

    def test_resolution_time_stats_fields(self):
        stats = ResolutionTimeStats()
        assert stats.avg_hours == 0.0
        assert stats.median_hours == 0.0
        assert stats.p95_hours == 0.0
        assert stats.total_resolved == 0

    def test_issue_dashboard_summary_fields(self):
        summary = IssueDashboardSummary(
            status_counts=IssueStatusCounts(),
            severity_counts=IssueSeverityCounts(),
            overdue_count=0,
            resolution_stats=ResolutionTimeStats(),
        )
        assert summary.status_counts.open == 0
        assert summary.severity_counts.critical == 0
        assert summary.resolution_stats.avg_hours == 0.0


# ── IssueReportService Tests ────────────────────────────────────────────────


class TestIssueCountByStatus:
    def test_issue_count_by_status(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("open", 10),
            ("resolved", 5),
            ("closed", 3),
        ]
        svc = IssueReportService()
        result = svc.count_by_status(db, _WS)
        assert result.open == 10
        assert result.resolved == 5
        assert result.closed == 3

    def test_issue_count_by_status_empty(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        svc = IssueReportService()
        result = svc.count_by_status(db, _WS)
        assert result.open == 0
        assert result.resolved == 0
        assert result.closed == 0

    def test_issue_count_by_status_excludes_other_workspaces(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("open", 7),
        ]
        svc = IssueReportService()
        result = svc.count_by_status(db, _WS)
        # Only workspace-scoped results returned
        assert result.open == 7
        assert result.resolved == 0
        db.query.assert_called_once()


class TestIssueCountBySeverity:
    def test_issue_count_by_severity(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("critical", 2),
            ("major", 5),
            ("minor", 8),
            ("info", 1),
        ]
        svc = IssueReportService()
        result = svc.count_by_severity(db, _WS)
        assert result.critical == 2
        assert result.major == 5
        assert result.minor == 8
        assert result.info == 1

    def test_issue_count_by_severity_empty(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        svc = IssueReportService()
        result = svc.count_by_severity(db, _WS)
        assert result.critical == 0
        assert result.major == 0


class TestIssueOverdue:
    def test_issue_count_overdue(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.scalar.return_value = 4
        svc = IssueReportService()
        result = svc.count_overdue(db, _WS)
        assert result == 4

    def test_issue_count_overdue_none(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.scalar.return_value = 0
        svc = IssueReportService()
        result = svc.count_overdue(db, _WS)
        assert result == 0


class TestIssueResolutionTimeStats:
    def test_issue_resolution_time_stats(self):
        db = _mock_db()
        # 3 resolved issues: 2h, 5h, 10h
        db.query.return_value.filter.return_value.all.return_value = [
            (2.0,),
            (5.0,),
            (10.0,),
        ]
        svc = IssueReportService()
        result = svc.resolution_time_stats(db, _WS)
        assert result.total_resolved == 3
        assert result.avg_hours == round((2 + 5 + 10) / 3, 2)
        assert result.median_hours == 5.0
        assert result.p95_hours == 10.0

    def test_issue_resolution_time_stats_no_resolved(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.all.return_value = []
        svc = IssueReportService()
        result = svc.resolution_time_stats(db, _WS)
        assert result.total_resolved == 0
        assert result.avg_hours == 0.0


class TestIssueDashboard:
    def test_issue_dashboard_summary(self):
        svc = IssueReportService()
        db = _mock_db()
        # Mock individual methods
        with (
            patch.object(svc, "count_by_status") as m_status,
            patch.object(svc, "count_by_severity") as m_sev,
            patch.object(svc, "count_overdue") as m_overdue,
            patch.object(svc, "resolution_time_stats") as m_res,
        ):
            m_status.return_value = IssueStatusCounts(open=5, resolved=3, closed=2)
            m_sev.return_value = IssueSeverityCounts(critical=1, major=3, minor=4, info=2)
            m_overdue.return_value = 2
            m_res.return_value = ResolutionTimeStats(
                avg_hours=4.5, median_hours=3.0, p95_hours=10.0, total_resolved=5
            )

            result = svc.dashboard_summary(db, _WS)
            assert result.status_counts.open == 5
            assert result.severity_counts.critical == 1
            assert result.overdue_count == 2
            assert result.resolution_stats.avg_hours == 4.5

    def test_issue_dashboard_summary_empty_workspace(self):
        svc = IssueReportService()
        db = _mock_db()
        with (
            patch.object(svc, "count_by_status") as m_status,
            patch.object(svc, "count_by_severity") as m_sev,
            patch.object(svc, "count_overdue") as m_overdue,
            patch.object(svc, "resolution_time_stats") as m_res,
        ):
            m_status.return_value = IssueStatusCounts()
            m_sev.return_value = IssueSeverityCounts()
            m_overdue.return_value = 0
            m_res.return_value = ResolutionTimeStats()

            result = svc.dashboard_summary(db, _WS)
            assert result.status_counts.open == 0
            assert result.overdue_count == 0
            assert result.resolution_stats.total_resolved == 0
