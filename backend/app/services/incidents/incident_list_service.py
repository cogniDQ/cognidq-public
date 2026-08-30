"""
IncidentListService — F042 Incident List and SLA Visibility
=============================================================

Paginated incident listing with filter support and SLA enrichment.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.services.incidents.incident_models import (
    IncidentListItem,
    IncidentPage,
)
from app.services.incidents.incident_repository import IncidentRepository


class IncidentListService:
    """Read-only service for listing incidents with SLA info."""

    def __init__(
        self,
        repo: IncidentRepository | None = None,
    ) -> None:
        self._repo = repo or IncidentRepository()

    def list_incidents(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        priority: str | None = None,
        owner_id: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> IncidentPage:
        """Return a paginated, filtered list of incidents with SLA enrichment."""

        offset = (page - 1) * page_size

        items, total = self._repo.list_by_workspace(
            db,
            workspace_id,
            status=status,
            severity=severity,
            priority=priority,
            owner_id=owner_id,
            offset=offset,
            limit=page_size,
        )

        has_next = total > page * page_size

        if not items:
            return IncidentPage(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                has_next=False,
            )

        # Issue counts per incident
        inc_ids = [i.id for i in items]
        counts = {i.id: self._repo.count_linked_issues(db, i.id) for i in items}

        # SLA info
        sla = self._repo.get_sla_info(db, inc_ids)

        # Build list items
        result = []
        for inc in items:
            owner_name = getattr(inc.owner, "full_name", None) if inc.owner else None
            creator_name = getattr(inc.creator, "full_name", None) if inc.creator else None
            earliest_due, has_breach = sla.get(inc.id, (None, False))

            result.append(
                IncidentListItem(
                    id=inc.id,
                    title=inc.title,
                    severity=inc.severity,
                    priority=inc.priority,
                    status=inc.status,
                    impact_summary=inc.impact_summary,
                    owner_id=inc.owner_id,
                    owner_name=owner_name,
                    created_by_name=creator_name,
                    issue_count=counts.get(inc.id, 0),
                    has_sla_breach=has_breach,
                    earliest_due_at=earliest_due,
                    opened_at=inc.opened_at,
                    acknowledged_at=inc.acknowledged_at,
                    resolved_at=inc.resolved_at,
                    closed_at=inc.closed_at,
                )
            )

        return IncidentPage(
            items=result,
            total=total,
            page=page,
            page_size=page_size,
            has_next=has_next,
        )
