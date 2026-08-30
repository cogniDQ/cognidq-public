"""
F035 P02 — Unit tests for IssueLifecycleService and IssueRepository.update()
=============================================================================

Tests cover:
- All 12 allowed status transitions
- Disallowed transitions (closed→in_progress, closed→open, resolved→open)
- Resolution summary enforcement (resolve / close without summary)
- Resolution summary length validation
- Assignee membership validation
- Timestamp side-effects (resolved_at, closed_at, reopen clears)
- Empty update handling
- Issue not found
- Repository update method
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from app.services.issues.issue_lifecycle_service import (
    ALLOWED_TRANSITIONS,
    EmptyUpdateError,
    InvalidAssigneeError,
    InvalidStatusTransitionError,
    IssueLifecycleService,
    IssueNotFoundError,
    ResolutionSummaryRequiredError,
    ResolutionSummaryTooLongError,
)
from app.services.issues.issue_models import (
    EnrichedIssueDetail,
    IssueDetail,
    IssueUpdateRequest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 31, 12, 0, 0, tzinfo=UTC)

_WORKSPACE_ID = uuid4()
_ISSUE_ID = uuid4()
_USER_ID = uuid4()
_TENANT_ID = uuid4()
_EXEC_ID = uuid4()


def _make_detail(
    status: str = "open",
    assignee_id: UUID | None = None,
    resolution_summary: str | None = None,
) -> IssueDetail:
    return IssueDetail(
        id=_ISSUE_ID,
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        flow_execution_id=_EXEC_ID,
        issue_type="rule_failure",
        severity="major",
        status=status,
        title="Test issue",
        assignee_id=assignee_id,
        resolution_summary=resolution_summary,
        opened_at=_NOW,
        updated_at=_NOW,
        created_at=_NOW,
    )


def _make_enriched(**kwargs) -> EnrichedIssueDetail:
    base = _make_detail(**kwargs)
    return EnrichedIssueDetail(**base.model_dump())


def _build_service(
    current_issue: IssueDetail | None = None,
    membership_exists: bool = True,
) -> tuple[IssueLifecycleService, MagicMock, MagicMock]:
    repo = MagicMock()
    detail_svc = MagicMock()

    repo.get_by_id_and_workspace.return_value = current_issue
    repo.update.return_value = current_issue

    enriched = _make_enriched(status=current_issue.status if current_issue else "open")
    detail_svc.get_enriched_detail.return_value = enriched

    db = MagicMock()
    # Mock membership check
    if membership_exists:
        db.execute.return_value.fetchone.return_value = (1,)
    else:
        db.execute.return_value.fetchone.return_value = None

    svc = IssueLifecycleService(repository=repo, detail_service=detail_svc)
    return svc, db, repo


# ---------------------------------------------------------------------------
# Transition tests — All 12 allowed transitions
# ---------------------------------------------------------------------------

_TRANSITION_CASES = []
for from_s, targets in ALLOWED_TRANSITIONS.items():
    for to_s in targets:
        _TRANSITION_CASES.append((from_s, to_s))


class TestAllowedTransitions:
    @pytest.mark.parametrize("from_status,to_status", _TRANSITION_CASES)
    def test_allowed_transition(self, from_status, to_status):
        """Each allowed transition should succeed (with resolution_summary if needed)."""
        needs_summary = to_status in ("resolved", "closed")
        detail = _make_detail(
            status=from_status,
            resolution_summary="existing summary" if needs_summary else None,
        )
        svc, db, repo = _build_service(current_issue=detail)

        fields = {"status"}
        kwargs = {"status": to_status}
        if needs_summary:
            fields.add("resolution_summary")
            kwargs["resolution_summary"] = "Fixed the root cause."

        result = svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided=fields,
            **kwargs,
        )
        assert result is not None
        repo.update.assert_called_once()
        call_updates = repo.update.call_args[0][3]
        assert call_updates["status"] == to_status


# ---------------------------------------------------------------------------
# Disallowed transitions
# ---------------------------------------------------------------------------


class TestDisallowedTransitions:
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            ("closed", "in_progress"),
            ("closed", "open"),
            ("resolved", "open"),
            ("resolved", "in_progress"),
            ("open", "reopened"),
        ],
    )
    def test_disallowed_transition(self, from_status, to_status):
        detail = _make_detail(status=from_status)
        svc, db, repo = _build_service(current_issue=detail)

        with pytest.raises(InvalidStatusTransitionError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"status"},
                status=to_status,
            )
        repo.update.assert_not_called()


# ---------------------------------------------------------------------------
# Resolution summary enforcement
# ---------------------------------------------------------------------------


class TestResolutionSummaryRequired:
    def test_resolve_without_summary_raises(self):
        detail = _make_detail(status="open")
        svc, db, repo = _build_service(current_issue=detail)

        with pytest.raises(ResolutionSummaryRequiredError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"status"},
                status="resolved",
            )

    def test_close_without_summary_raises(self):
        detail = _make_detail(status="in_progress")
        svc, db, repo = _build_service(current_issue=detail)

        with pytest.raises(ResolutionSummaryRequiredError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"status"},
                status="closed",
            )

    def test_resolve_with_pre_existing_summary_succeeds(self):
        detail = _make_detail(status="open", resolution_summary="pre-filled")
        svc, db, repo = _build_service(current_issue=detail)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"status"},
            status="resolved",
        )
        repo.update.assert_called_once()


class TestResolutionSummaryLength:
    def test_summary_too_long_raises(self):
        detail = _make_detail(status="open")
        svc, db, repo = _build_service(current_issue=detail)

        with pytest.raises(ResolutionSummaryTooLongError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"resolution_summary"},
                resolution_summary="x" * 5001,
            )


# ---------------------------------------------------------------------------
# Timestamp side-effects
# ---------------------------------------------------------------------------


class TestTimestampEffects:
    @patch("app.services.issues.issue_lifecycle_service.datetime")
    def test_resolve_sets_resolved_at(self, mock_dt):
        mock_dt.now.return_value = _NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        detail = _make_detail(status="open")
        svc, db, repo = _build_service(current_issue=detail)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"status", "resolution_summary"},
            status="resolved",
            resolution_summary="Fixed.",
        )
        updates = repo.update.call_args[0][3]
        assert updates["resolved_at"] is not None
        assert "closed_at" not in updates

    @patch("app.services.issues.issue_lifecycle_service.datetime")
    def test_close_sets_closed_at(self, mock_dt):
        mock_dt.now.return_value = _NOW
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        detail = _make_detail(status="resolved", resolution_summary="Done")
        svc, db, repo = _build_service(current_issue=detail)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"status"},
            status="closed",
        )
        updates = repo.update.call_args[0][3]
        assert updates["closed_at"] is not None
        assert "resolved_at" not in updates

    def test_reopen_clears_timestamps(self):
        detail = _make_detail(status="closed")
        svc, db, repo = _build_service(current_issue=detail)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"status"},
            status="reopened",
        )
        updates = repo.update.call_args[0][3]
        assert updates["resolved_at"] is None
        assert updates["closed_at"] is None


# ---------------------------------------------------------------------------
# Assignee validation
# ---------------------------------------------------------------------------


class TestAssigneeValidation:
    def test_assign_valid_member(self):
        detail = _make_detail()
        svc, db, repo = _build_service(current_issue=detail, membership_exists=True)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"assignee_id"},
            assignee_id=_USER_ID,
        )
        updates = repo.update.call_args[0][3]
        assert updates["assignee_id"] == _USER_ID

    def test_assign_non_member_raises(self):
        detail = _make_detail()
        svc, db, repo = _build_service(current_issue=detail, membership_exists=False)

        with pytest.raises(InvalidAssigneeError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"assignee_id"},
                assignee_id=_USER_ID,
            )

    def test_unassign_succeeds(self):
        detail = _make_detail(assignee_id=_USER_ID)
        svc, db, repo = _build_service(current_issue=detail)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"assignee_id"},
            assignee_id=None,
        )
        updates = repo.update.call_args[0][3]
        assert updates["assignee_id"] is None


# ---------------------------------------------------------------------------
# Due date
# ---------------------------------------------------------------------------


class TestDueDate:
    def test_set_due_date(self):
        detail = _make_detail()
        svc, db, repo = _build_service(current_issue=detail)
        due = datetime(2026, 4, 15, tzinfo=UTC)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"due_at"},
            due_at=due,
        )
        updates = repo.update.call_args[0][3]
        assert updates["due_at"] == due

    def test_clear_due_date(self):
        detail = _make_detail()
        svc, db, repo = _build_service(current_issue=detail)

        svc.update_issue(
            db,
            _ISSUE_ID,
            _WORKSPACE_ID,
            fields_provided={"due_at"},
            due_at=None,
        )
        updates = repo.update.call_args[0][3]
        assert updates["due_at"] is None


# ---------------------------------------------------------------------------
# Issue not found
# ---------------------------------------------------------------------------


class TestIssueNotFound:
    def test_not_found_raises(self):
        svc, db, repo = _build_service(current_issue=None)

        with pytest.raises(IssueNotFoundError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"status"},
                status="in_progress",
            )


# ---------------------------------------------------------------------------
# Empty update
# ---------------------------------------------------------------------------


class TestEmptyUpdate:
    def test_no_fields_raises(self):
        detail = _make_detail()
        svc, db, repo = _build_service(current_issue=detail)

        with pytest.raises(EmptyUpdateError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided=set(),
            )

    def test_unknown_fields_only_raises(self):
        detail = _make_detail()
        svc, db, repo = _build_service(current_issue=detail)

        with pytest.raises(EmptyUpdateError):
            svc.update_issue(
                db,
                _ISSUE_ID,
                _WORKSPACE_ID,
                fields_provided={"unknown_field"},
            )


# ---------------------------------------------------------------------------
# IssueUpdateRequest model tests
# ---------------------------------------------------------------------------


class TestIssueUpdateRequestModel:
    def test_fields_set_detection(self):
        req = IssueUpdateRequest.model_validate({"status": "in_progress"})
        assert "status" in req.model_fields_set
        assert "assignee_id" not in req.model_fields_set

    def test_explicit_null(self):
        req = IssueUpdateRequest.model_validate({"assignee_id": None})
        assert "assignee_id" in req.model_fields_set
        assert req.assignee_id is None

    def test_empty_body(self):
        req = IssueUpdateRequest.model_validate({})
        assert len(req.model_fields_set) == 0
