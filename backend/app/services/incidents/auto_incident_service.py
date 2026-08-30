"""
F039 — Automatic Incident Creation Service
=============================================

Evaluates a newly-created or grouped issue against the workspace's incident
policy and, if criteria are met, auto-creates an incident linked to that issue.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentIssue
from app.services.incidents.auto_incident_models import (
    DEFAULT_INCIDENT_POLICY,
    IncidentPolicy,
)
from app.services.incidents.incident_repository import IncidentRepository

logger = logging.getLogger(__name__)


class AutoIncidentService:
    """Evaluate issue against policy; create incident when criteria are met."""

    def __init__(self, repo: IncidentRepository | None = None) -> None:
        self._repo = repo or IncidentRepository()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def evaluate_and_create(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        issue_id: UUID,
        issue_severity: str,
        issue_failure_count: int,
        issue_title: str,
        policy: IncidentPolicy | None = None,
    ) -> UUID | None:
        """Evaluate *issue* against *policy*; return incident id or None.

        Parameters
        ----------
        db : Session
            Caller-owned session (service flushes but does NOT commit).
        workspace_id, tenant_id :
            Scoping identifiers.
        issue_id :
            The issue that triggered evaluation.
        issue_severity :
            Severity string from the issue (critical/major/minor/informational).
        issue_failure_count :
            Current failure_count on the issue (≥1 for new, ≥2 for grouped).
        issue_title :
            Used to derive the incident title.
        policy :
            The workspace incident policy.  ``None`` → use disabled default.

        Returns
        -------
        UUID | None
            The ID of the newly-created incident, or ``None`` when the policy
            is disabled or criteria are not met.
        """
        pol = policy or DEFAULT_INCIDENT_POLICY

        if not pol.enabled:
            return None

        if not pol.severity_met(issue_severity):
            logger.debug(
                "F039 skip: severity %s below min %s",
                issue_severity,
                pol.min_severity,
            )
            return None

        if not pol.recurrence_met(issue_failure_count):
            logger.debug(
                "F039 skip: failure_count %d below threshold %d",
                issue_failure_count,
                pol.recurrence_threshold,
            )
            return None

        # Check if issue is already linked to an open incident
        if self._issue_has_open_incident(db, issue_id, workspace_id):
            logger.debug(
                "F039 skip: issue %s already linked to open incident",
                issue_id,
            )
            return None

        # All criteria met — create incident
        priority = pol.derive_priority(issue_severity)
        title = f"[Auto] {issue_title}"
        if len(title) > 500:
            title = title[:497] + "..."

        incident = Incident(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            title=title,
            severity=issue_severity,
            priority=priority,
            status="open",
            impact_summary=f"Auto-created by incident policy for issue severity={issue_severity}",
            owner_id=pol.auto_owner_user_id,
            created_by_user_id=None,  # system-created
        )
        incident = self._repo.insert(db, incident)

        link = IncidentIssue(
            incident_id=incident.id,
            issue_id=issue_id,
            linked_by_user_id=None,  # system-linked
        )
        self._repo.bulk_insert_links(db, [link])

        logger.info(
            "F039 auto-incident created: incident_id=%s issue_id=%s severity=%s priority=%s",
            incident.id,
            issue_id,
            issue_severity,
            priority,
        )

        return incident.id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _issue_has_open_incident(
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
    ) -> bool:
        """Return True if issue is linked to an incident with status='open'."""
        row = (
            db.query(Incident.id)
            .join(IncidentIssue, IncidentIssue.incident_id == Incident.id)
            .filter(
                IncidentIssue.issue_id == issue_id,
                Incident.workspace_id == workspace_id,
                Incident.status == "open",
            )
            .first()
        )
        return row is not None
