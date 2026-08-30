"""
IncidentLinkService — F041 Issue-to-Incident Linkage
=====================================================

Add / remove issue links on an existing incident.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.incident import IncidentIssue
from app.services.audit.hooks import build_incident_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.incidents.incident_models import LinkOperationResponse
from app.services.incidents.incident_repository import IncidentRepository

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IncidentNotFoundError(Exception):
    pass


class IssueNotFoundError(Exception):
    pass


class MinimumLinkError(Exception):
    pass


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IncidentLinkService:
    """Manages issue links on an existing incident."""

    def __init__(
        self,
        repo: IncidentRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repo or IncidentRepository()
        self._audit = audit_service or AuditService()

    # ------------------------------------------------------------------ #
    # add_links
    # ------------------------------------------------------------------ #

    def add_links(
        self,
        db: Session,
        incident_id: UUID,
        workspace_id: UUID,
        *,
        issue_ids: list[UUID],
        actor_id: UUID,
        audit_ctx: AuditContext | None = None,
    ) -> LinkOperationResponse:
        """Link additional issues to an incident (idempotent for duplicates)."""

        # 1. Validate incident
        incident = self._repo.get_by_id_and_workspace(db, incident_id, workspace_id)
        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        # 2. Deduplicate input
        unique_ids = list(dict.fromkeys(issue_ids))

        # 3. Validate issues exist in workspace
        found = self._repo.get_issues_in_workspace(db, workspace_id, unique_ids)
        if len(found) != len(unique_ids):
            missing = set(unique_ids) - set(found)
            raise IssueNotFoundError(f"Issues not found in workspace: {missing}")

        # 4. Filter out already-linked
        existing = set(self._repo.get_linked_issue_ids(db, incident_id))
        new_ids = [iid for iid in unique_ids if iid not in existing]

        # 5. Bulk insert new links
        if new_ids:
            links = [
                IncidentIssue(
                    incident_id=incident_id,
                    issue_id=iid,
                    linked_by_user_id=actor_id,
                )
                for iid in new_ids
            ]
            self._repo.bulk_insert_links(db, links)

        # 6. Audit
        if audit_ctx is not None and new_ids:
            entry = build_incident_audit_entry(
                ctx=audit_ctx,
                action="incident_links_added",
                workspace_id=workspace_id,
                incident_id=incident_id,
                after_state={"added_issue_ids": [str(i) for i in new_ids]},
            )
            self._audit.write(db, entry)

        # 7. Return
        all_linked = self._repo.get_linked_issue_ids(db, incident_id)
        return LinkOperationResponse(
            incident_id=incident_id,
            issue_count=len(all_linked),
            linked_issue_ids=all_linked,
        )

    # ------------------------------------------------------------------ #
    # remove_links
    # ------------------------------------------------------------------ #

    def remove_links(
        self,
        db: Session,
        incident_id: UUID,
        workspace_id: UUID,
        *,
        issue_ids: list[UUID],
        audit_ctx: AuditContext | None = None,
    ) -> LinkOperationResponse:
        """Unlink issues from an incident. At least one link must remain."""

        # 1. Validate incident
        incident = self._repo.get_by_id_and_workspace(db, incident_id, workspace_id)
        if incident is None:
            raise IncidentNotFoundError("Incident not found.")

        # 2. Current links
        existing = set(self._repo.get_linked_issue_ids(db, incident_id))

        # 3. Compute what would remain
        to_remove = set(issue_ids) & existing
        remaining = existing - to_remove
        if not remaining:
            raise MinimumLinkError(
                "Cannot remove all links. An incident must have at least one linked issue."
            )

        # 4. Delete
        if to_remove:
            self._repo.delete_links(db, incident_id, list(to_remove))

        # 5. Audit
        if audit_ctx is not None and to_remove:
            entry = build_incident_audit_entry(
                ctx=audit_ctx,
                action="incident_links_removed",
                workspace_id=workspace_id,
                incident_id=incident_id,
                after_state={"removed_issue_ids": [str(i) for i in to_remove]},
            )
            self._audit.write(db, entry)

        # 6. Return
        all_linked = self._repo.get_linked_issue_ids(db, incident_id)
        return LinkOperationResponse(
            incident_id=incident_id,
            issue_count=len(all_linked),
            linked_issue_ids=all_linked,
        )
