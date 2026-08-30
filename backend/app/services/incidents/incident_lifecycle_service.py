"""
IncidentLifecycleService — F040 Incident Acknowledgement and Resolution
========================================================================

Encapsulates status transitions, owner changes, resolution-summary
enforcement, and lifecycle-timestamp side-effects for incidents.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.audit.hooks import build_incident_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.incidents.incident_models import IncidentResponse
from app.services.incidents.incident_repository import IncidentRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged"},
    "acknowledged": {"mitigated", "resolved", "closed"},
    "mitigated": {"resolved", "closed"},
    "resolved": {"closed"},
    "closed": {"reopened"},
    "reopened": {"acknowledged", "mitigated", "resolved", "closed"},
}

RESOLUTION_REQUIRED_STATUSES = frozenset({"resolved", "closed"})
RESOLUTION_SUMMARY_MAX_LENGTH = 5000


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IncidentNotFoundError(Exception):
    pass


class InvalidStatusTransitionError(Exception):
    pass


class ResolutionSummaryRequiredError(Exception):
    pass


class EmptyUpdateError(Exception):
    pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IncidentLifecycleService:
    """Orchestrates incident lifecycle mutations."""

    def __init__(
        self,
        repo: IncidentRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repo or IncidentRepository()
        self._audit = audit_service or AuditService()

    def update_incident(
        self,
        db: Session,
        incident_id: UUID,
        workspace_id: UUID,
        *,
        fields_provided: set[str],
        status: str | None = None,
        owner_id: UUID | None = None,
        impact_summary: str | None = None,
        resolution_summary: str | None = None,
        audit_ctx: AuditContext | None = None,
    ) -> IncidentResponse:
        """Validate and apply an incident update."""

        # 0. At least one recognized field
        recognized = fields_provided & {
            "status",
            "owner_id",
            "impact_summary",
            "resolution_summary",
        }
        if not recognized:
            raise EmptyUpdateError("No fields provided for update.")

        # 1. Fetch
        current = self._repo.get_by_id_and_workspace(db, incident_id, workspace_id)
        if current is None:
            raise IncidentNotFoundError("Incident not found.")

        updates: dict = {}

        # 2. Status transition
        if "status" in recognized and status is not None:
            self._validate_transition(current.status, status)
            updates["status"] = status

        target_status = updates.get("status", current.status)

        # 3. Resolution summary
        if "resolution_summary" in recognized:
            updates["resolution_summary"] = resolution_summary

        if "status" in recognized and target_status in RESOLUTION_REQUIRED_STATUSES:
            effective = updates.get("resolution_summary", current.resolution_summary)
            if not effective:
                raise ResolutionSummaryRequiredError(
                    "Resolution summary is required when resolving or closing."
                )

        # 4. Owner
        if "owner_id" in recognized:
            updates["owner_id"] = owner_id

        # 5. Impact summary
        if "impact_summary" in recognized:
            updates["impact_summary"] = impact_summary

        # 6. Timestamp side-effects
        if "status" in updates:
            ts = self._compute_timestamp_effects(updates["status"])
            updates.update(ts)

        # 7. Persist
        self._repo.update(db, incident_id, workspace_id, updates)

        # 8. Audit
        if audit_ctx is not None:
            if "status" in updates:
                action = "incident_status_changed"
            elif "owner_id" in updates:
                action = "incident_owner_changed"
            else:
                action = "incident_updated"

            entry = build_incident_audit_entry(
                ctx=audit_ctx,
                action=action,
                workspace_id=workspace_id,
                incident_id=incident_id,
                after_state={k: str(v) if v is not None else None for k, v in updates.items()},
            )
            self._audit.write(db, entry)

        # 8b. Alert triggers (best-effort, non-blocking)
        try:
            from app.services.alerts.alert_trigger_service import AlertTriggerService

            _trigger_svc = AlertTriggerService()
            if "status" in updates:
                _trigger_svc.trigger_for_workspace(
                    db,
                    workspace_id=workspace_id,
                    trigger_type="incident_status_changed",
                    payload={
                        "incident_id": str(incident_id),
                        "title": current.title,
                        "old_status": current.status,
                        "new_status": updates["status"],
                    },
                    audit_ctx=audit_ctx,
                )
            if "owner_id" in updates and updates["owner_id"] is not None:
                _trigger_svc.trigger_for_workspace(
                    db,
                    workspace_id=workspace_id,
                    trigger_type="incident_assigned",
                    payload={
                        "incident_id": str(incident_id),
                        "title": current.title,
                        "owner_id": str(updates["owner_id"]),
                        "previous_owner_id": str(current.owner_id) if current.owner_id else None,
                    },
                    audit_ctx=audit_ctx,
                )
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "incident lifecycle alert trigger failed", exc_info=True
            )

        # 9. Refresh and build response
        db.refresh(current)
        issue_count = self._repo.count_linked_issues(db, incident_id)
        owner_name = getattr(current.owner, "full_name", None) if current.owner else None
        creator_name = getattr(current.creator, "full_name", None) if current.creator else None

        return IncidentResponse(
            id=current.id,
            workspace_id=current.workspace_id,
            title=current.title,
            severity=current.severity,
            priority=current.priority,
            status=current.status,
            impact_summary=current.impact_summary,
            resolution_summary=current.resolution_summary,
            owner_id=current.owner_id,
            owner_name=owner_name,
            created_by_user_id=current.created_by_user_id,
            created_by_name=creator_name,
            issue_count=issue_count,
            opened_at=current.opened_at,
        )

    # -- Internals --------------------------------------------------------

    @staticmethod
    def _validate_transition(current_status: str, target_status: str) -> None:
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Cannot transition from '{current_status}' to '{target_status}'."
            )

    @staticmethod
    def _compute_timestamp_effects(target_status: str) -> dict:
        now = datetime.now(UTC)
        effects: dict = {}
        if target_status == "acknowledged":
            effects["acknowledged_at"] = now
        elif target_status == "resolved":
            effects["resolved_at"] = now
        elif target_status == "closed":
            effects["closed_at"] = now
        return effects
