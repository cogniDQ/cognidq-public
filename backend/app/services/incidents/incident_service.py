"""
F038 Incident Service
=====================

Orchestrates manual incident creation: validation, persistence, audit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentIssue
from app.services.audit.hooks import build_incident_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.incidents.incident_models import IncidentResponse
from app.services.incidents.incident_repository import IncidentRepository

# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

VALID_SEVERITIES = frozenset({"critical", "major", "minor", "informational"})
VALID_PRIORITIES = frozenset({"P1", "P2", "P3", "P4"})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IncidentValidationError(Exception):
    """Raised when incident input fails validation."""


class IssueNotFoundError(Exception):
    """Raised when one or more issue_ids are not found in the workspace."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IncidentService:
    """Create (and later manage) incidents."""

    def __init__(
        self,
        repo: IncidentRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repo or IncidentRepository()
        self._audit = audit_service or AuditService()

    # --------------------------------------------------------------------- #
    # create_incident
    # --------------------------------------------------------------------- #

    def create_incident(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        created_by_user_id: UUID,
        title: str,
        severity: str,
        priority: str,
        impact_summary: str | None = None,
        owner_id: UUID | None = None,
        issue_ids: list[UUID],
        audit_ctx: AuditContext | None = None,
    ) -> IncidentResponse:
        """Validate, persist incident + links, audit, return response."""

        # --- 1. Validate scalars ---
        title = (title or "").strip()
        if not title or len(title) > 500:
            raise IncidentValidationError("title must be 1–500 characters")
        if severity not in VALID_SEVERITIES:
            raise IncidentValidationError(f"invalid severity: {severity}")
        if priority not in VALID_PRIORITIES:
            raise IncidentValidationError(f"invalid priority: {priority}")
        if not issue_ids:
            raise IncidentValidationError("issue_ids must contain at least one issue")

        # --- 2. Deduplicate issue_ids ---
        unique_ids = list(dict.fromkeys(issue_ids))

        # --- 3. Verify issues exist in workspace ---
        found = self._repo.get_issues_in_workspace(db, workspace_id, unique_ids)
        if len(found) != len(unique_ids):
            missing = set(unique_ids) - set(found)
            raise IssueNotFoundError(f"Issues not found in workspace: {missing}")

        # --- 4. Persist incident ---
        incident = Incident(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            title=title,
            severity=severity,
            priority=priority,
            impact_summary=impact_summary,
            owner_id=owner_id,
            created_by_user_id=created_by_user_id,
        )
        incident = self._repo.insert(db, incident)

        # --- 5. Persist junction links ---
        links = [
            IncidentIssue(
                incident_id=incident.id,
                issue_id=iid,
                linked_by_user_id=created_by_user_id,
            )
            for iid in unique_ids
        ]
        self._repo.bulk_insert_links(db, links)

        # --- 6. Audit ---
        if audit_ctx is not None:
            entry = build_incident_audit_entry(
                ctx=audit_ctx,
                action="incident_created",
                workspace_id=workspace_id,
                incident_id=incident.id,
                after_state={
                    "title": title,
                    "severity": severity,
                    "priority": priority,
                    "status": "open",
                    "issue_count": len(unique_ids),
                },
            )
            self._audit.write(db, entry)

        # --- 6b. incident_created alert trigger (best-effort, non-blocking) ---
        try:
            from app.services.alerts.alert_trigger_service import AlertTriggerService

            AlertTriggerService().trigger(
                db,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                trigger_type="incident_created",
                payload={
                    "incident_id": str(incident.id),
                    "title": title,
                    "severity": severity,
                    "priority": priority,
                    "status": "open",
                    "owner_id": str(owner_id) if owner_id else None,
                    "created_by_user_id": str(created_by_user_id) if created_by_user_id else None,
                    "issue_count": len(unique_ids),
                },
                audit_ctx=audit_ctx,
            )
        except Exception:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "incident_created alert trigger failed", exc_info=True
            )

        # --- 7. Resolve names ---
        owner_name = getattr(incident.owner, "full_name", None) if incident.owner else None
        creator_name = getattr(incident.creator, "full_name", None) if incident.creator else None

        # --- 8. Build response ---
        return IncidentResponse(
            id=incident.id,
            workspace_id=incident.workspace_id,
            title=incident.title,
            severity=incident.severity,
            priority=incident.priority,
            status=incident.status,
            impact_summary=incident.impact_summary,
            owner_id=incident.owner_id,
            owner_name=owner_name,
            created_by_user_id=incident.created_by_user_id,
            created_by_name=creator_name,
            issue_count=len(unique_ids),
            opened_at=incident.opened_at,
        )
