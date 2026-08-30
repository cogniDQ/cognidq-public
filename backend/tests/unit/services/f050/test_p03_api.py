"""
F050 P03 — Issue/Incident Report API Endpoint Tests (15 tests)
===============================================================

Covers:
  - GET /reports/issues/summary          (200)
  - GET /reports/issues/by-status        (200)
  - GET /reports/issues/by-severity      (200)
  - GET /reports/incidents/summary       (200)
  - GET /reports/incidents/by-status     (200)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
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

REPORTS_EP = "app.api.v1.endpoints.issue_incident_reports"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.user_id = _USER
    actor.role = "admin"
    return actor


def _db():
    return MagicMock()


def _issue_summary() -> IssueDashboardSummary:
    return IssueDashboardSummary(
        status_counts=IssueStatusCounts(open=5, resolved=3, closed=2),
        severity_counts=IssueSeverityCounts(critical=1, major=2, minor=4, info=3),
        overdue_count=2,
        resolution_stats=ResolutionTimeStats(
            avg_hours=4.5, median_hours=3.0, p95_hours=12.0, total_resolved=3
        ),
    )


def _incident_summary() -> IncidentDashboardSummary:
    return IncidentDashboardSummary(
        status_counts=IncidentStatusCounts(open=3, acknowledged=1, resolved=2, closed=1),
        severity_counts=IncidentSeverityCounts(critical=2, major=1, minor=3, info=1),
        priority_counts=IncidentPriorityCounts(p1=2, p2=1, p3=3, p4=1),
        sla_breach_count=1,
        resolution_stats=ResolutionTimeStats(
            avg_hours=6.0, median_hours=5.0, p95_hours=18.0, total_resolved=2
        ),
    )


# ── Issue Summary ────────────────────────────────────────────────────────────


class TestGetIssueSummary:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issue_summary

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _issue_summary()
            result = await get_issue_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_response_contains_status_counts(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issue_summary

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _issue_summary()
            result = await get_issue_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["status_counts"]["open"] == 5
        assert body["status_counts"]["resolved"] == 3

    @pytest.mark.asyncio
    async def test_response_contains_overdue(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issue_summary

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _issue_summary()
            result = await get_issue_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["overdue_count"] == 2

    @pytest.mark.asyncio
    async def test_response_contains_resolution_stats(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issue_summary

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _issue_summary()
            result = await get_issue_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["resolution_stats"]["avg_hours"] == 4.5
        assert body["resolution_stats"]["total_resolved"] == 3


# ── Issue By-Status ──────────────────────────────────────────────────────────


class TestGetIssuesByStatus:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issues_by_status

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.count_by_status.return_value = IssueStatusCounts(open=7, resolved=2, closed=1)
            result = await get_issues_by_status(workspace_id=_WS, actor=_mock_actor(), db=_db())
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_response_body(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issues_by_status

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.count_by_status.return_value = IssueStatusCounts(open=7, resolved=2, closed=1)
            result = await get_issues_by_status(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["open"] == 7
        assert body["resolved"] == 2
        assert body["closed"] == 1


# ── Issue By-Severity ────────────────────────────────────────────────────────


class TestGetIssuesBySeverity:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issues_by_severity

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.count_by_severity.return_value = IssueSeverityCounts(
                critical=3, major=2, minor=1, info=0
            )
            result = await get_issues_by_severity(workspace_id=_WS, actor=_mock_actor(), db=_db())
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_response_body(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issues_by_severity

        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.count_by_severity.return_value = IssueSeverityCounts(
                critical=3, major=2, minor=1, info=0
            )
            result = await get_issues_by_severity(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["critical"] == 3
        assert body["info"] == 0


# ── Incident Summary ────────────────────────────────────────────────────────


class TestGetIncidentSummary:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import get_incident_summary

        with patch(f"{REPORTS_EP}._incident_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _incident_summary()
            result = await get_incident_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_response_contains_status_counts(self):
        from app.api.v1.endpoints.issue_incident_reports import get_incident_summary

        with patch(f"{REPORTS_EP}._incident_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _incident_summary()
            result = await get_incident_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["status_counts"]["open"] == 3
        assert body["status_counts"]["acknowledged"] == 1

    @pytest.mark.asyncio
    async def test_response_contains_sla_breach(self):
        from app.api.v1.endpoints.issue_incident_reports import get_incident_summary

        with patch(f"{REPORTS_EP}._incident_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _incident_summary()
            result = await get_incident_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["sla_breach_count"] == 1

    @pytest.mark.asyncio
    async def test_response_contains_priority_counts(self):
        from app.api.v1.endpoints.issue_incident_reports import get_incident_summary

        with patch(f"{REPORTS_EP}._incident_svc") as mock_svc:
            mock_svc.dashboard_summary.return_value = _incident_summary()
            result = await get_incident_summary(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["priority_counts"]["p1"] == 2
        assert body["priority_counts"]["p4"] == 1


# ── Incident By-Status ──────────────────────────────────────────────────────


class TestGetIncidentsByStatus:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import get_incidents_by_status

        with patch(f"{REPORTS_EP}._incident_svc") as mock_svc:
            mock_svc.count_by_status.return_value = IncidentStatusCounts(
                open=4, acknowledged=2, resolved=1, closed=0
            )
            result = await get_incidents_by_status(workspace_id=_WS, actor=_mock_actor(), db=_db())
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_response_body(self):
        from app.api.v1.endpoints.issue_incident_reports import get_incidents_by_status

        with patch(f"{REPORTS_EP}._incident_svc") as mock_svc:
            mock_svc.count_by_status.return_value = IncidentStatusCounts(
                open=4, acknowledged=2, resolved=1, closed=0
            )
            result = await get_incidents_by_status(workspace_id=_WS, actor=_mock_actor(), db=_db())
        body = json.loads(result.body)
        assert body["open"] == 4
        assert body["acknowledged"] == 2
        assert body["closed"] == 0


# ── Service Wiring ───────────────────────────────────────────────────────────


class TestServiceWiring:
    @pytest.mark.asyncio
    async def test_issue_svc_receives_workspace_id(self):
        from app.api.v1.endpoints.issue_incident_reports import get_issues_by_status

        db = _db()
        with patch(f"{REPORTS_EP}._issue_svc") as mock_svc:
            mock_svc.count_by_status.return_value = IssueStatusCounts()
            await get_issues_by_status(workspace_id=_WS, actor=_mock_actor(), db=db)
        mock_svc.count_by_status.assert_called_once_with(db, _WS)
