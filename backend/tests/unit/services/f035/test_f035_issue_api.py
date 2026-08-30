"""
F035 P03 — API-level tests for PATCH /workspaces/{workspace_id}/issues/{issue_id}
==================================================================================

Uses the same sys.modules mock pattern from F033 to avoid the jose import chain.
All tests are synchronous (call handler via asyncio.run) — no pytest-asyncio needed.
"""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import UTC, datetime, timezone
from decimal import Decimal
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

# Minimal WorkspaceActorContext stand-in
_actor = MagicMock()
_actor.actor_id = uuid4()

_auth_stub.WorkspaceActorContext = type("WorkspaceActorContext", (), {})  # type: ignore[attr-defined]
_auth_stub.require_workspace_permission = lambda action: lambda: _actor  # type: ignore[attr-defined]

sys.modules.setdefault("jose", _jose_stub)
sys.modules.setdefault("jose.jwt", _jose_jwt_stub)
sys.modules.setdefault("app.api.v1.dependencies.workspace_auth", _auth_stub)

# Now safe to import the endpoint helpers and models
from app.services.issues.issue_lifecycle_service import (
    EmptyUpdateError,
    InvalidAssigneeError,
    InvalidStatusTransitionError,
    IssueNotFoundError,
    ResolutionSummaryRequiredError,
    ResolutionSummaryTooLongError,
)
from app.services.issues.issue_models import (
    EnrichedIssueDetail,
    IssueUpdateRequest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 31, 12, 0, 0, tzinfo=UTC)
_WORKSPACE_ID = uuid4()
_ISSUE_ID = uuid4()
_TENANT_ID = uuid4()
_EXEC_ID = uuid4()


def _make_enriched(**overrides) -> EnrichedIssueDetail:
    defaults = dict(
        id=_ISSUE_ID,
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        flow_execution_id=_EXEC_ID,
        issue_type="rule_failure",
        severity="major",
        status="in_progress",
        title="Test issue",
        resolution_summary=None,
        opened_at=_NOW,
        updated_at=_NOW,
        created_at=_NOW,
    )
    defaults.update(overrides)
    return EnrichedIssueDetail(**defaults)


# Import the actual endpoint function after stubs are in place
from app.api.v1.endpoints.issues import (
    _serialize_enriched_detail,
)
from app.api.v1.endpoints.issues import (
    update_issue as _update_issue_handler,
)

# We'll test the handler by patching _lifecycle_svc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPatchHappyPathStatus:
    """PATCH with a valid status change returns 200 with enriched detail."""

    def test_status_change_returns_200(self):
        enriched = _make_enriched(status="in_progress")
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.return_value = enriched
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"status": "in_progress"})

            resp = asyncio.run(
                _update_issue_handler(
                    workspace_id=_WORKSPACE_ID,
                    issue_id=_ISSUE_ID,
                    body=body,
                    actor=_actor,
                    db=db,
                )
            )
            assert resp.status_code == 200
            import json

            data = json.loads(resp.body.decode())
            assert data["status"] == "in_progress"
            assert data["id"] == str(_ISSUE_ID)


class TestPatchAssigneeChange:
    """PATCH with assignee_id returns enriched detail."""

    def test_assignee_change(self):
        user_id = uuid4()
        enriched = _make_enriched(assignee_id=user_id)
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.return_value = enriched
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"assignee_id": str(user_id)})

            resp = asyncio.run(
                _update_issue_handler(
                    workspace_id=_WORKSPACE_ID,
                    issue_id=_ISSUE_ID,
                    body=body,
                    actor=_actor,
                    db=db,
                )
            )
            assert resp.status_code == 200
            import json

            data = json.loads(resp.body.decode())
            assert data["assignee_id"] == str(user_id)


class TestPatchDueDateChange:
    """PATCH with due_at returns enriched detail."""

    def test_due_date_change(self):
        due = datetime(2026, 4, 15, tzinfo=UTC)
        enriched = _make_enriched(due_at=due)
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.return_value = enriched
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"due_at": due.isoformat()})

            resp = asyncio.run(
                _update_issue_handler(
                    workspace_id=_WORKSPACE_ID,
                    issue_id=_ISSUE_ID,
                    body=body,
                    actor=_actor,
                    db=db,
                )
            )
            assert resp.status_code == 200
            import json

            data = json.loads(resp.body.decode())
            assert data["due_at"] is not None


class TestPatchNotFound:
    """PATCH returns 404 for non-existent issue."""

    def test_not_found_returns_404(self):
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.side_effect = IssueNotFoundError("Issue not found.")
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"status": "in_progress"})

            with pytest.raises(Exception) as exc_info:
                asyncio.run(
                    _update_issue_handler(
                        workspace_id=_WORKSPACE_ID,
                        issue_id=_ISSUE_ID,
                        body=body,
                        actor=_actor,
                        db=db,
                    )
                )
            assert exc_info.value.status_code == 404


class TestPatchInvalidTransition:
    """PATCH returns 422 for invalid transition."""

    def test_invalid_transition_returns_422(self):
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.side_effect = InvalidStatusTransitionError(
                "Transition from 'closed' to 'in_progress' is not allowed."
            )
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"status": "in_progress"})

            with pytest.raises(Exception) as exc_info:
                asyncio.run(
                    _update_issue_handler(
                        workspace_id=_WORKSPACE_ID,
                        issue_id=_ISSUE_ID,
                        body=body,
                        actor=_actor,
                        db=db,
                    )
                )
            assert exc_info.value.status_code == 422


class TestPatchResolutionSummaryRequired:
    """PATCH returns 422 when resolution_summary is missing for resolve/close."""

    def test_missing_summary_returns_422(self):
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.side_effect = ResolutionSummaryRequiredError(
                "Resolution summary is required when resolving or closing an issue."
            )
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"status": "resolved"})

            with pytest.raises(Exception) as exc_info:
                asyncio.run(
                    _update_issue_handler(
                        workspace_id=_WORKSPACE_ID,
                        issue_id=_ISSUE_ID,
                        body=body,
                        actor=_actor,
                        db=db,
                    )
                )
            assert exc_info.value.status_code == 422


class TestPatchInvalidAssignee:
    """PATCH returns 422 for non-member assignee."""

    def test_invalid_assignee_returns_422(self):
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.side_effect = InvalidAssigneeError(
                "Assignee must be a member of this workspace."
            )
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({"assignee_id": str(uuid4())})

            with pytest.raises(Exception) as exc_info:
                asyncio.run(
                    _update_issue_handler(
                        workspace_id=_WORKSPACE_ID,
                        issue_id=_ISSUE_ID,
                        body=body,
                        actor=_actor,
                        db=db,
                    )
                )
            assert exc_info.value.status_code == 422


class TestPatchEmptyBody:
    """PATCH returns 422 for empty body."""

    def test_empty_body_returns_422(self):
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.side_effect = EmptyUpdateError("No fields provided for update.")
            db = MagicMock()
            body = IssueUpdateRequest.model_validate({})

            with pytest.raises(Exception) as exc_info:
                asyncio.run(
                    _update_issue_handler(
                        workspace_id=_WORKSPACE_ID,
                        issue_id=_ISSUE_ID,
                        body=body,
                        actor=_actor,
                        db=db,
                    )
                )
            assert exc_info.value.status_code == 422


class TestPatchEnrichedResponse:
    """PATCH response includes resolution_summary and enriched context."""

    def test_response_includes_resolution_summary(self):
        enriched = _make_enriched(
            status="resolved",
            resolution_summary="Fixed the ETL pipeline.",
        )
        with patch("app.api.v1.endpoints.issues._lifecycle_svc") as mock_svc:
            mock_svc.update_issue.return_value = enriched
            db = MagicMock()
            body = IssueUpdateRequest.model_validate(
                {
                    "status": "resolved",
                    "resolution_summary": "Fixed the ETL pipeline.",
                }
            )

            resp = asyncio.run(
                _update_issue_handler(
                    workspace_id=_WORKSPACE_ID,
                    issue_id=_ISSUE_ID,
                    body=body,
                    actor=_actor,
                    db=db,
                )
            )
            import json

            data = json.loads(resp.body.decode())
            assert data["resolution_summary"] == "Fixed the ETL pipeline."
            assert "rule" in data
            assert "dataset" in data
            assert "assignee" in data
            assert "flow_execution" in data
            assert "node_result" in data
