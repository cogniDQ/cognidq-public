"""
F037 P02 — Tests for CSV export endpoint and helpers
=====================================================

Tests CSV serialization, UTF-8 BOM, column order, injection prevention,
truncation behavior, and Content-Disposition header.
All tests are synchronous (asyncio.run).
"""

from __future__ import annotations

import asyncio
import csv
import io
import sys
import types
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Stub out jose / workspace_auth
# ---------------------------------------------------------------------------

_jose_stub = types.ModuleType("jose")
_jose_jwt_stub = types.ModuleType("jose.jwt")
_jose_stub.jwt = _jose_jwt_stub  # type: ignore[attr-defined]

_auth_stub = types.ModuleType("app.api.v1.dependencies.workspace_auth")

_actor = MagicMock()
_actor.actor_id = uuid4()

_auth_stub.WorkspaceActorContext = type("WorkspaceActorContext", (), {})  # type: ignore[attr-defined]
_auth_stub.require_workspace_permission = lambda action: lambda: _actor  # type: ignore[attr-defined]

sys.modules.setdefault("jose", _jose_stub)
sys.modules.setdefault("jose.jwt", _jose_jwt_stub)
sys.modules.setdefault("app.api.v1.dependencies.workspace_auth", _auth_stub)

from app.services.issues.issue_models import IssueListItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 7, 14, 12, 0, 0, tzinfo=UTC)
_WS = uuid4()


def _make_export_item(**overrides) -> IssueListItem:
    defaults = dict(
        id=uuid4(),
        workspace_id=_WS,
        issue_type="rule_failure",
        severity="major",
        status="open",
        title="Test issue",
        impact_summary="50 rows affected",
        failure_count=50,
        due_at=_NOW,
        opened_at=_NOW,
        assignee_id=uuid4(),
        assignee_display_name="Alice",
        dataset_name="Orders",
        updated_at=_NOW,
    )
    defaults.update(overrides)
    return IssueListItem(**defaults)


def _call_export(**kwargs):
    """Call the export endpoint with sensible defaults."""
    from app.api.v1.endpoints.issues import export_issues_csv

    defaults = dict(
        workspace_id=_WS,
        status_filter=None,
        severity=None,
        assignee_id=None,
        dataset_id=None,
        overdue=False,
        sort_by="opened_at",
        sort_dir="desc",
        actor=_actor,
        db=MagicMock(),
    )
    defaults.update(kwargs)
    return asyncio.run(export_issues_csv(**defaults))


def _parse_csv_body(resp) -> list[list[str]]:
    """Parse CSV from response body, stripping BOM."""
    body = resp.body
    # Strip BOM
    if body[:3] == b"\xef\xbb\xbf":
        body = body[3:]
    text = body.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    return list(reader)


# ===========================================================================
# Tests
# ===========================================================================


class TestExportContentType:
    """AC-P02-001: Content-Type is text/csv."""

    def test_content_type(self):
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([_make_export_item()], False)
            resp = _call_export()

        assert resp.media_type == "text/csv; charset=utf-8"


class TestExportBom:
    """AC-P02-002: CSV body starts with UTF-8 BOM."""

    def test_bom_present(self):
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([_make_export_item()], False)
            resp = _call_export()

        assert resp.body[:3] == b"\xef\xbb\xbf"


class TestExportColumnOrder:
    """AC-P02-003: CSV has the 14 required columns in correct order."""

    def test_column_order(self):
        expected = [
            "id",
            "title",
            "severity",
            "status",
            "assignee_display_name",
            "dataset_name",
            "issue_type",
            "failure_count",
            "due_at",
            "opened_at",
            "resolved_at",
            "closed_at",
            "updated_at",
            "impact_summary",
        ]
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([_make_export_item()], False)
            resp = _call_export()

        rows = _parse_csv_body(resp)
        assert rows[0] == expected


class TestExportAllRows:
    """AC-P02-004: All filtered issues included (not just one page)."""

    def test_multiple_rows(self):
        items = [_make_export_item(title=f"Issue {i}") for i in range(5)]
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = (items, False)
            resp = _call_export()

        rows = _parse_csv_body(resp)
        # 1 header + 5 data rows
        assert len(rows) == 6


class TestExportTruncation:
    """AC-P02-005: Truncation note when > 10,000 rows."""

    def test_truncation_note_present(self):
        items = [_make_export_item()]
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = (items, True)
            resp = _call_export()

        rows = _parse_csv_body(resp)
        last_row = rows[-1]
        assert "truncated" in last_row[0].lower()

    def test_no_truncation_note_when_not_truncated(self):
        items = [_make_export_item()]
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = (items, False)
            resp = _call_export()

        rows = _parse_csv_body(resp)
        # No truncation row
        assert len(rows) == 2  # header + 1 data


class TestExportInjectionPrevention:
    """AC-P02-006: Values starting with =, +, -, @ are prefixed with '."""

    def test_formula_injection_escaped(self):
        item = _make_export_item(title="=SUM(A1:A10)", impact_summary="+cmd")
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([item], False)
            resp = _call_export()

        rows = _parse_csv_body(resp)
        data_row = rows[1]
        # title is column index 1
        assert data_row[1].startswith("'")
        # impact_summary is column index 13
        assert data_row[13].startswith("'")


class TestExportEmptyResult:
    """AC-P02-007: Empty result returns headers only."""

    def test_empty_export(self):
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([], False)
            resp = _call_export()

        rows = _parse_csv_body(resp)
        assert len(rows) == 1  # header only


class TestExportContentDisposition:
    """AC-P02-008: Content-Disposition includes attachment with filename."""

    def test_content_disposition(self):
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([_make_export_item()], False)
            resp = _call_export()

        cd = resp.headers.get("content-disposition", "")
        assert cd.startswith("attachment")
        assert "issues_export_" in cd
        assert ".csv" in cd


class TestExportRepoLimit:
    """Verify the export repo method is called (no pagination params)."""

    def test_export_calls_repo(self):
        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([], False)
            _call_export()

        mock_repo.list_all_for_export.assert_called_once()
        call_kwargs = mock_repo.list_all_for_export.call_args
        # No page/page_size in the call
        assert "page" not in call_kwargs[1]
        assert "page_size" not in call_kwargs[1]


class TestExportFilterPassthrough:
    """Verify filters are passed to the repo export method."""

    def test_filters_forwarded(self):
        assignee_uuid = str(uuid4())
        dataset_uuid = str(uuid4())

        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_all_for_export.return_value = ([], False)
            _call_export(
                status_filter="open",
                severity="critical",
                assignee_id=assignee_uuid,
                dataset_id=dataset_uuid,
                overdue=True,
                sort_by="severity",
                sort_dir="asc",
            )

        call_kwargs = mock_repo.list_all_for_export.call_args
        assert call_kwargs[1]["status"] == "open"
        assert call_kwargs[1]["severity"] == "critical"
        assert call_kwargs[1]["assignee_id"] == assignee_uuid
        assert call_kwargs[1]["overdue"] is True
        assert call_kwargs[1]["sort_by"] == "severity"
        assert call_kwargs[1]["sort_dir"] == "asc"
