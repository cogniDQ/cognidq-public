"""
IssueLifecycleService — F035 Issue Assignment and Status Lifecycle
==================================================================

Encapsulates all mutation business logic for issues: status transitions,
assignee validation, due-date management, resolution-summary enforcement,
and lifecycle-timestamp side-effects.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit.hooks import build_issue_audit_entry
from app.services.audit.models import AuditContext, compute_audit_diff
from app.services.audit.service import AuditService
from app.services.issues.issue_detail_service import IssueDetailService
from app.services.issues.issue_models import EnrichedIssueDetail
from app.services.issues.issue_repository import IssueRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed status transitions (source → set of valid targets)
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "resolved", "closed"},
    "in_progress": {"open", "resolved", "closed"},
    "resolved": {"closed", "reopened"},
    "closed": {"reopened"},
    "reopened": {"in_progress", "resolved", "closed"},
}

RESOLUTION_REQUIRED_STATUSES = frozenset({"resolved", "closed"})
RESOLUTION_SUMMARY_MAX_LENGTH = 5000


# ---------------------------------------------------------------------------
# Domain exceptions (mapped to HTTP codes by the API layer)
# ---------------------------------------------------------------------------


class IssueNotFoundError(Exception):
    """Raised when the target issue does not exist in the workspace."""


class InvalidStatusTransitionError(Exception):
    """Raised when a status transition is not in the allowed map."""


class ResolutionSummaryRequiredError(Exception):
    """Raised when resolve/close is attempted without a resolution summary."""


class ResolutionSummaryTooLongError(Exception):
    """Raised when resolution_summary exceeds the max length."""


class InvalidAssigneeError(Exception):
    """Raised when assignee_id is not a member of the workspace."""


class EmptyUpdateError(Exception):
    """Raised when no recognised fields are provided in the update."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IssueLifecycleService:
    """Orchestrates issue mutation logic."""

    def __init__(
        self,
        repository: IssueRepository | None = None,
        detail_service: IssueDetailService | None = None,
    ) -> None:
        self._repo = repository or IssueRepository()
        self._detail = detail_service or IssueDetailService(repository=self._repo)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def update_issue(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
        *,
        fields_provided: set[str],
        status: str | None = None,
        assignee_id: UUID | None = None,
        due_at: datetime | None = None,
        resolution_summary: str | None = None,
        audit_ctx: AuditContext | None = None,
        audit_service: AuditService | None = None,
    ) -> EnrichedIssueDetail:
        """
        Validate and apply an issue update, then return the enriched detail.

        *fields_provided* is the set of field names present in the request
        body (from ``model_fields_set``), used to distinguish between
        "not provided" and "explicitly set to None".
        """
        # 0. At least one recognized field must be provided
        recognized = fields_provided & {"status", "assignee_id", "due_at", "resolution_summary"}
        if not recognized:
            raise EmptyUpdateError("No fields provided for update.")

        # 1. Fetch current issue
        current = self._repo.get_by_id_and_workspace(db, issue_id, workspace_id)
        if current is None:
            raise IssueNotFoundError("Issue not found.")

        updates: dict = {}

        # 2. Status transition validation
        if "status" in recognized and status is not None:
            self._validate_transition(current.status, status)
            updates["status"] = status

        target_status = updates.get("status", current.status)

        # 3. Resolution summary validation
        if "resolution_summary" in recognized:
            if (
                resolution_summary is not None
                and len(resolution_summary) > RESOLUTION_SUMMARY_MAX_LENGTH
            ):
                raise ResolutionSummaryTooLongError(
                    f"Resolution summary must not exceed {RESOLUTION_SUMMARY_MAX_LENGTH} characters."
                )
            updates["resolution_summary"] = resolution_summary

        # If transitioning to resolved/closed, ensure resolution_summary exists
        if "status" in recognized and target_status in RESOLUTION_REQUIRED_STATUSES:
            effective_summary = updates.get("resolution_summary", current.resolution_summary)
            if not effective_summary:
                raise ResolutionSummaryRequiredError(
                    "Resolution summary is required when resolving or closing an issue."
                )

        # 4. Assignee validation
        if "assignee_id" in recognized:
            if assignee_id is not None:
                self._check_workspace_membership(db, workspace_id, assignee_id)
            updates["assignee_id"] = assignee_id

        # 5. Due date
        if "due_at" in recognized:
            updates["due_at"] = due_at

        # 6. Timestamp side-effects
        if "status" in updates:
            ts_effects = self._compute_timestamp_effects(updates["status"])
            updates.update(ts_effects)

        # 7. Persist
        self._repo.update(db, issue_id, workspace_id, updates)

        # 7a. F052 audit hook — within same transaction as the update
        if audit_ctx is not None and audit_service is not None:
            _svc = audit_service
            before_fields = {
                "status": current.status,
                "assignee_id": str(current.assignee_id) if current.assignee_id else None,
                "due_at": current.due_at.isoformat() if current.due_at else None,
                "resolution_summary": current.resolution_summary,
            }
            after_fields = {
                k: (
                    v.isoformat()
                    if isinstance(v, datetime)
                    else str(v)
                    if isinstance(v, UUID)
                    else v
                )
                for k, v in updates.items()
                if k in ("status", "assignee_id", "due_at", "resolution_summary")
            }
            _before, _after = compute_audit_diff(before_fields, after_fields)
            if _after:
                # Determine primary action type
                if "status" in updates:
                    action = "issue_status_changed"
                elif "assignee_id" in updates:
                    action = "issue_assigned"
                else:
                    action = "issue_updated"
                entry = build_issue_audit_entry(
                    ctx=audit_ctx,
                    action=action,
                    workspace_id=workspace_id,
                    issue_id=issue_id,
                    after_state=_after,
                    before_state=_before,
                )
                _svc.write(db, entry)

        db.commit()

        # 8. Log
        if "status" in updates:
            logger.info(
                "issue_status_changed issue_id=%s workspace_id=%s from=%s to=%s",
                issue_id,
                workspace_id,
                current.status,
                updates["status"],
            )
        if "assignee_id" in updates:
            logger.info(
                "issue_assignee_changed issue_id=%s workspace_id=%s old=%s new=%s",
                issue_id,
                workspace_id,
                current.assignee_id,
                updates.get("assignee_id"),
            )

        # 9. Return enriched detail
        enriched = self._detail.get_enriched_detail(db, issue_id, workspace_id)
        return enriched  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Private validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_transition(current_status: str, target_status: str) -> None:
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Transition from '{current_status}' to '{target_status}' is not allowed."
            )

    @staticmethod
    def _check_workspace_membership(db: Session, workspace_id: UUID, user_id: UUID) -> None:
        row = db.execute(
            text(
                "SELECT 1 FROM control.workspace_role_assignments "
                "WHERE workspace_id = :ws AND user_id = :uid LIMIT 1"
            ),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if row is None:
            raise InvalidAssigneeError("Assignee must be a member of this workspace.")

    @staticmethod
    def _compute_timestamp_effects(target_status: str) -> dict:
        now = datetime.now(UTC)
        effects: dict = {}
        if target_status == "resolved":
            effects["resolved_at"] = now
        elif target_status == "closed":
            effects["closed_at"] = now
        elif target_status == "reopened":
            effects["resolved_at"] = None
            effects["closed_at"] = None
        return effects
