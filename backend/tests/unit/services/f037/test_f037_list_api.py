"""
F037 P01 — API-level tests for GET /workspaces/{workspace_id}/issues enhancements
===================================================================================

Tests parameter validation and response serialization for the extended list endpoint.
Uses the same sys.modules mock pattern from F033/F035.
All tests are synchronous (asyncio.run) — no pytest-asyncio needed.
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Stub out jose / workspace_auth before importing the endpoint module
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

# Now safe to import
from app.services.issues.issue_models import (
    VALID_SORT_COLUMNS,
    VALID_SORT_DIRECTIONS,
    IssueListItem,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2025, 7, 14, 12, 0, 0, tzinfo=UTC)
_WS = uuid4()
_ASSIGNEE_A = uuid4()


def _make_list_item(**overrides) -> IssueListItem:
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
        assignee_id=_ASSIGNEE_A,
        assignee_display_name="Alice",
        dataset_name="Orders",
        updated_at=_NOW,
    )
    defaults.update(overrides)
    return IssueListItem(**defaults)


# ===========================================================================
# Tests — Validation
# ===========================================================================


class TestInvalidSortBy:
    """AC-P01-011: invalid sort_by returns HTTP 400."""

    def test_invalid_sort_by(self):
        from app.api.v1.endpoints.issues import list_issues
        from fastapi import HTTPException

        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id=None,
                    dataset_id=None,
                    overdue=False,
                    sort_by="invalid_column",
                    sort_dir="desc",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )
        assert exc_info.value.status_code == 400
        assert "Invalid sort column" in exc_info.value.detail


class TestInvalidSortDir:
    """AC-P01-011: invalid sort_dir returns HTTP 400."""

    def test_invalid_sort_dir(self):
        from app.api.v1.endpoints.issues import list_issues
        from fastapi import HTTPException

        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id=None,
                    dataset_id=None,
                    overdue=False,
                    sort_by="opened_at",
                    sort_dir="invalid",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )
        assert exc_info.value.status_code == 400
        assert "Invalid sort direction" in exc_info.value.detail


class TestInvalidAssigneeId:
    """AC-P01-012: invalid assignee_id returns HTTP 400."""

    def test_invalid_assignee_id(self):
        from app.api.v1.endpoints.issues import list_issues
        from fastapi import HTTPException

        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id="not-a-uuid",
                    dataset_id=None,
                    overdue=False,
                    sort_by="opened_at",
                    sort_dir="desc",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )
        assert exc_info.value.status_code == 400
        assert "assignee_id" in exc_info.value.detail

    def test_unassigned_is_valid(self):
        """The literal 'unassigned' should NOT trigger validation error."""
        from app.api.v1.endpoints.issues import list_issues

        db = MagicMock()
        mock_items = [_make_list_item()]

        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_by_workspace.return_value = (mock_items, 1)
            resp = asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id="unassigned",
                    dataset_id=None,
                    overdue=False,
                    sort_by="opened_at",
                    sort_dir="desc",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )
        assert resp.status_code == 200


class TestInvalidDatasetId:
    """AC-P01-012: invalid dataset_id returns HTTP 400."""

    def test_invalid_dataset_id(self):
        from app.api.v1.endpoints.issues import list_issues
        from fastapi import HTTPException

        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id=None,
                    dataset_id="not-a-uuid",
                    overdue=False,
                    sort_by="opened_at",
                    sort_dir="desc",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )
        assert exc_info.value.status_code == 400
        assert "dataset_id" in exc_info.value.detail


# ===========================================================================
# Tests — Successful response
# ===========================================================================


class TestValidFiltersPassThrough:
    """AC-P01-013: valid params reach the repository."""

    def test_filters_forwarded_to_repo(self):
        from app.api.v1.endpoints.issues import list_issues

        db = MagicMock()
        assignee_uuid = str(uuid4())
        dataset_uuid = str(uuid4())
        mock_items = [_make_list_item()]

        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_by_workspace.return_value = (mock_items, 1)
            asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter="open",
                    severity="critical",
                    assignee_id=assignee_uuid,
                    dataset_id=dataset_uuid,
                    overdue=True,
                    sort_by="severity",
                    sort_dir="asc",
                    page=2,
                    page_size=25,
                    actor=_actor,
                    db=db,
                )
            )

        call_kwargs = mock_repo.list_by_workspace.call_args
        assert call_kwargs[1]["status"] == "open"
        assert call_kwargs[1]["severity"] == "critical"
        assert call_kwargs[1]["assignee_id"] == assignee_uuid
        assert str(call_kwargs[1]["dataset_id"]) == dataset_uuid
        assert call_kwargs[1]["overdue"] is True
        assert call_kwargs[1]["sort_by"] == "severity"
        assert call_kwargs[1]["sort_dir"] == "asc"
        assert call_kwargs[1]["page"] == 2
        assert call_kwargs[1]["page_size"] == 25


class TestResponseIncludesNewFields:
    """Verify the serialized response includes the F037 denormalized fields."""

    def test_response_fields(self):
        import json

        from app.api.v1.endpoints.issues import list_issues

        db = MagicMock()
        item = _make_list_item()
        mock_items = [item]

        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_by_workspace.return_value = (mock_items, 1)
            resp = asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id=None,
                    dataset_id=None,
                    overdue=False,
                    sort_by="opened_at",
                    sort_dir="desc",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )

        body = json.loads(resp.body)
        first = body["items"][0]
        assert "assignee_id" in first
        assert "assignee_display_name" in first
        assert "dataset_name" in first
        assert "updated_at" in first
        assert first["assignee_display_name"] == "Alice"
        assert first["dataset_name"] == "Orders"


class TestResponseNullFields:
    """Verify null denormalized fields serialize correctly."""

    def test_null_fields(self):
        import json

        from app.api.v1.endpoints.issues import list_issues

        db = MagicMock()
        item = _make_list_item(
            assignee_id=None,
            assignee_display_name=None,
            dataset_name=None,
            updated_at=None,
        )

        with patch("app.api.v1.endpoints.issues._repo") as mock_repo:
            mock_repo.list_by_workspace.return_value = ([item], 1)
            resp = asyncio.run(
                list_issues(
                    workspace_id=_WS,
                    status_filter=None,
                    severity=None,
                    assignee_id=None,
                    dataset_id=None,
                    overdue=False,
                    sort_by="opened_at",
                    sort_dir="desc",
                    page=1,
                    page_size=50,
                    actor=_actor,
                    db=db,
                )
            )

        body = json.loads(resp.body)
        first = body["items"][0]
        assert first["assignee_id"] is None
        assert first["assignee_display_name"] is None
        assert first["dataset_name"] is None
        assert first["updated_at"] is None
