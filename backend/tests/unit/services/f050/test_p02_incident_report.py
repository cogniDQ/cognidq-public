"""
F050 P02 — IncidentReportService Tests (15 tests)
===================================================

Covers incident aggregation methods: counts, severity, priority, SLA, resolution stats.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.reporting.incident_report_service import IncidentReportService
from app.services.reporting.report_models import (
    IncidentDashboardSummary,
    IncidentPriorityCounts,
    IncidentSeverityCounts,
    IncidentStatusCounts,
    ResolutionTimeStats,
)

_WS = uuid4()


def _mock_db():
    return MagicMock()


# ── Pydantic Model Tests ────────────────────────────────────────────────────


class TestIncidentPydanticModels:
    def test_incident_status_counts_defaults(self):
        counts = IncidentStatusCounts()
        assert counts.open == 0
        assert counts.acknowledged == 0
        assert counts.resolved == 0
        assert counts.closed == 0

    def test_incident_severity_counts_defaults(self):
        counts = IncidentSeverityCounts()
        assert counts.critical == 0
        assert counts.major == 0

    def test_incident_priority_counts_defaults(self):
        counts = IncidentPriorityCounts()
        assert counts.p1 == 0
        assert counts.p2 == 0
        assert counts.p3 == 0
        assert counts.p4 == 0

    def test_incident_dashboard_summary_fields(self):
        summary = IncidentDashboardSummary(
            status_counts=IncidentStatusCounts(),
            severity_counts=IncidentSeverityCounts(),
            priority_counts=IncidentPriorityCounts(),
            sla_breach_count=0,
            resolution_stats=ResolutionTimeStats(),
        )
        assert summary.sla_breach_count == 0
        assert summary.resolution_stats.total_resolved == 0


# ── IncidentReportService Tests ──────────────────────────────────────────────


class TestIncidentCountByStatus:
    def test_incident_count_by_status(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("open", 8),
            ("acknowledged", 2),
            ("resolved", 3),
            ("closed", 1),
        ]
        svc = IncidentReportService()
        result = svc.count_by_status(db, _WS)
        assert result.open == 8
        assert result.acknowledged == 2
        assert result.resolved == 3
        assert result.closed == 1

    def test_incident_count_by_status_empty(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        svc = IncidentReportService()
        result = svc.count_by_status(db, _WS)
        assert result.open == 0
        assert result.acknowledged == 0

    def test_incident_count_by_status_workspace_scoped(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("open", 3),
        ]
        svc = IncidentReportService()
        result = svc.count_by_status(db, _WS)
        assert result.open == 3
        db.query.assert_called_once()


class TestIncidentCountBySeverity:
    def test_incident_count_by_severity(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("critical", 1),
            ("major", 4),
            ("minor", 6),
            ("info", 2),
        ]
        svc = IncidentReportService()
        result = svc.count_by_severity(db, _WS)
        assert result.critical == 1
        assert result.major == 4
        assert result.minor == 6
        assert result.info == 2


class TestIncidentCountByPriority:
    def test_incident_count_by_priority(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ("P1", 2),
            ("P2", 5),
            ("P3", 3),
            ("P4", 1),
        ]
        svc = IncidentReportService()
        result = svc.count_by_priority(db, _WS)
        assert result.p1 == 2
        assert result.p2 == 5
        assert result.p3 == 3
        assert result.p4 == 1


class TestIncidentSLABreach:
    def test_incident_sla_breach_count(self):
        db = _mock_db()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.scalar.return_value = 3
        svc = IncidentReportService()
        result = svc.sla_breach_count(db, _WS)
        assert result == 3

    def test_incident_sla_breach_count_none(self):
        db = _mock_db()
        db.query.return_value.join.return_value.join.return_value.filter.return_value.scalar.return_value = 0
        svc = IncidentReportService()
        result = svc.sla_breach_count(db, _WS)
        assert result == 0


class TestIncidentResolutionTimeStats:
    def test_incident_resolution_time_stats(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.all.return_value = [
            (1.0,),
            (4.0,),
            (8.0,),
            (24.0,),
        ]
        svc = IncidentReportService()
        result = svc.resolution_time_stats(db, _WS)
        assert result.total_resolved == 4
        assert result.avg_hours == round((1 + 4 + 8 + 24) / 4, 2)
        assert result.p95_hours == 24.0

    def test_incident_resolution_time_stats_no_resolved(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.all.return_value = []
        svc = IncidentReportService()
        result = svc.resolution_time_stats(db, _WS)
        assert result.total_resolved == 0
        assert result.avg_hours == 0.0


class TestIncidentDashboard:
    def test_incident_dashboard_summary(self):
        svc = IncidentReportService()
        db = _mock_db()
        with (
            patch.object(svc, "count_by_status") as m_status,
            patch.object(svc, "count_by_severity") as m_sev,
            patch.object(svc, "count_by_priority") as m_pri,
            patch.object(svc, "sla_breach_count") as m_sla,
            patch.object(svc, "resolution_time_stats") as m_res,
        ):
            m_status.return_value = IncidentStatusCounts(
                open=4, acknowledged=1, resolved=2, closed=1
            )
            m_sev.return_value = IncidentSeverityCounts(critical=1, major=3, minor=2, info=2)
            m_pri.return_value = IncidentPriorityCounts(p1=1, p2=3, p3=2, p4=2)
            m_sla.return_value = 1
            m_res.return_value = ResolutionTimeStats(
                avg_hours=5.0, median_hours=4.0, p95_hours=12.0, total_resolved=3
            )

            result = svc.dashboard_summary(db, _WS)
            assert result.status_counts.open == 4
            assert result.severity_counts.critical == 1
            assert result.priority_counts.p1 == 1
            assert result.sla_breach_count == 1
            assert result.resolution_stats.avg_hours == 5.0

    def test_incident_dashboard_summary_empty(self):
        svc = IncidentReportService()
        db = _mock_db()
        with (
            patch.object(svc, "count_by_status") as m_status,
            patch.object(svc, "count_by_severity") as m_sev,
            patch.object(svc, "count_by_priority") as m_pri,
            patch.object(svc, "sla_breach_count") as m_sla,
            patch.object(svc, "resolution_time_stats") as m_res,
        ):
            m_status.return_value = IncidentStatusCounts()
            m_sev.return_value = IncidentSeverityCounts()
            m_pri.return_value = IncidentPriorityCounts()
            m_sla.return_value = 0
            m_res.return_value = ResolutionTimeStats()

            result = svc.dashboard_summary(db, _WS)
            assert result.status_counts.open == 0
            assert result.sla_breach_count == 0
            assert result.resolution_stats.total_resolved == 0
