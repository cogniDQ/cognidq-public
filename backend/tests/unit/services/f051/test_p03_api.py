"""
F051 P03 — CSV Export API Endpoint Tests (15 tests)
=====================================================

Covers:
  - GET /incidents/export                 (200)
  - GET /reports/issues/export            (200)
  - GET /reports/incidents/export         (200)
"""

from __future__ import annotations

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

INCIDENTS_EP = "app.api.v1.endpoints.incidents"
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


# ── Incident List CSV Export ─────────────────────────────────────────────────


class TestIncidentExport:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.incidents import export_incidents_csv

        with (
            patch(f"{INCIDENTS_EP}._repo") as mock_repo,
            patch(f"{INCIDENTS_EP}._csv_svc") as mock_csv,
        ):
            mock_repo.list_all_for_export.return_value = ([], False)
            mock_csv.generate_csv.return_value = b"\xef\xbb\xbfid\r\n"
            result = await export_incidents_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_csv(self):
        from app.api.v1.endpoints.incidents import export_incidents_csv

        with (
            patch(f"{INCIDENTS_EP}._repo") as mock_repo,
            patch(f"{INCIDENTS_EP}._csv_svc") as mock_csv,
        ):
            mock_repo.list_all_for_export.return_value = ([], False)
            mock_csv.generate_csv.return_value = b"\xef\xbb\xbfid\r\n"
            result = await export_incidents_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert "text/csv" in result.media_type

    @pytest.mark.asyncio
    async def test_has_content_disposition(self):
        from app.api.v1.endpoints.incidents import export_incidents_csv

        with (
            patch(f"{INCIDENTS_EP}._repo") as mock_repo,
            patch(f"{INCIDENTS_EP}._csv_svc") as mock_csv,
        ):
            mock_repo.list_all_for_export.return_value = ([], False)
            mock_csv.generate_csv.return_value = b"\xef\xbb\xbfid\r\n"
            result = await export_incidents_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert "content-disposition" in result.headers
        assert "incidents_export_" in result.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_calls_service(self):
        from app.api.v1.endpoints.incidents import export_incidents_csv

        with (
            patch(f"{INCIDENTS_EP}._repo") as mock_repo,
            patch(f"{INCIDENTS_EP}._csv_svc") as mock_csv,
        ):
            mock_repo.list_all_for_export.return_value = (["item1"], True)
            mock_csv.generate_csv.return_value = b"\xef\xbb\xbfid\r\n"
            await export_incidents_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        mock_csv.generate_csv.assert_called_once_with(["item1"], truncated=True)

    @pytest.mark.asyncio
    async def test_with_status_filter(self):
        from app.api.v1.endpoints.incidents import export_incidents_csv

        db = _db()
        with (
            patch(f"{INCIDENTS_EP}._repo") as mock_repo,
            patch(f"{INCIDENTS_EP}._csv_svc") as mock_csv,
        ):
            mock_repo.list_all_for_export.return_value = ([], False)
            mock_csv.generate_csv.return_value = b"\xef\xbb\xbfid\r\n"
            await export_incidents_csv(
                workspace_id=_WS,
                status_filter="open",
                actor=_mock_actor(),
                db=db,
            )
        call_kwargs = mock_repo.list_all_for_export.call_args
        assert call_kwargs[0][1] == _WS
        assert call_kwargs[1]["status"] == "open"


# ── Issue Summary CSV Export ─────────────────────────────────────────────────


class TestIssueSummaryExport:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import export_issue_summary_csv

        with (
            patch(f"{REPORTS_EP}._issue_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            mock_svc.dashboard_summary.return_value = _issue_summary()
            mock_csv.issue_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            result = await export_issue_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_csv(self):
        from app.api.v1.endpoints.issue_incident_reports import export_issue_summary_csv

        with (
            patch(f"{REPORTS_EP}._issue_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            mock_svc.dashboard_summary.return_value = _issue_summary()
            mock_csv.issue_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            result = await export_issue_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert "text/csv" in result.media_type

    @pytest.mark.asyncio
    async def test_has_content_disposition(self):
        from app.api.v1.endpoints.issue_incident_reports import export_issue_summary_csv

        with (
            patch(f"{REPORTS_EP}._issue_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            mock_svc.dashboard_summary.return_value = _issue_summary()
            mock_csv.issue_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            result = await export_issue_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert "issue_summary_" in result.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_calls_service(self):
        from app.api.v1.endpoints.issue_incident_reports import export_issue_summary_csv

        db = _db()
        with (
            patch(f"{REPORTS_EP}._issue_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            summary = _issue_summary()
            mock_svc.dashboard_summary.return_value = summary
            mock_csv.issue_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            await export_issue_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=db,
            )
        mock_svc.dashboard_summary.assert_called_once_with(db, _WS)

    @pytest.mark.asyncio
    async def test_wiring(self):
        from app.api.v1.endpoints.issue_incident_reports import export_issue_summary_csv

        with (
            patch(f"{REPORTS_EP}._issue_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            summary = _issue_summary()
            mock_svc.dashboard_summary.return_value = summary
            mock_csv.issue_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            await export_issue_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        mock_csv.issue_summary_csv.assert_called_once_with(summary)


# ── Incident Summary CSV Export ──────────────────────────────────────────────


class TestIncidentSummaryExport:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        from app.api.v1.endpoints.issue_incident_reports import export_incident_summary_csv

        with (
            patch(f"{REPORTS_EP}._incident_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            mock_svc.dashboard_summary.return_value = _incident_summary()
            mock_csv.incident_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            result = await export_incident_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_csv(self):
        from app.api.v1.endpoints.issue_incident_reports import export_incident_summary_csv

        with (
            patch(f"{REPORTS_EP}._incident_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            mock_svc.dashboard_summary.return_value = _incident_summary()
            mock_csv.incident_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            result = await export_incident_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert "text/csv" in result.media_type

    @pytest.mark.asyncio
    async def test_has_content_disposition(self):
        from app.api.v1.endpoints.issue_incident_reports import export_incident_summary_csv

        with (
            patch(f"{REPORTS_EP}._incident_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            mock_svc.dashboard_summary.return_value = _incident_summary()
            mock_csv.incident_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            result = await export_incident_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        assert "incident_summary_" in result.headers["content-disposition"]

    @pytest.mark.asyncio
    async def test_calls_service(self):
        from app.api.v1.endpoints.issue_incident_reports import export_incident_summary_csv

        db = _db()
        with (
            patch(f"{REPORTS_EP}._incident_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            summary = _incident_summary()
            mock_svc.dashboard_summary.return_value = summary
            mock_csv.incident_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            await export_incident_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=db,
            )
        mock_svc.dashboard_summary.assert_called_once_with(db, _WS)

    @pytest.mark.asyncio
    async def test_wiring(self):
        from app.api.v1.endpoints.issue_incident_reports import export_incident_summary_csv

        with (
            patch(f"{REPORTS_EP}._incident_svc") as mock_svc,
            patch(f"{REPORTS_EP}._csv_svc") as mock_csv,
        ):
            summary = _incident_summary()
            mock_svc.dashboard_summary.return_value = summary
            mock_csv.incident_summary_csv.return_value = b"\xef\xbb\xbfdata\r\n"
            await export_incident_summary_csv(
                workspace_id=_WS,
                actor=_mock_actor(),
                db=_db(),
            )
        mock_csv.incident_summary_csv.assert_called_once_with(summary)
