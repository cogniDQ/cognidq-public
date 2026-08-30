"""
F038 Incident Repository
========================

Data-access layer for Incident and IncidentIssue ORM objects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentIssue


class IncidentRepository:
    """CRUD operations for the incidents table."""

    # -- write ----------------------------------------------------------------

    def insert(self, db: Session, incident: Incident) -> Incident:
        """Persist a new incident and flush to populate server defaults."""
        db.add(incident)
        db.flush()
        return incident

    def bulk_insert_links(
        self,
        db: Session,
        links: list[IncidentIssue],
    ) -> None:
        """Persist incident⟷issue junction rows."""
        db.add_all(links)
        db.flush()

    # -- read -----------------------------------------------------------------

    def get_issues_in_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        issue_ids: list[UUID],
    ) -> list[UUID]:
        """Return the subset of *issue_ids* that exist in *workspace_id*."""
        from app.models.issue import Issue

        rows = (
            db.query(Issue.id)
            .filter(Issue.workspace_id == workspace_id, Issue.id.in_(issue_ids))
            .all()
        )
        return [r[0] for r in rows]

    def get_by_id_and_workspace(
        self,
        db: Session,
        incident_id: UUID,
        workspace_id: UUID,
    ) -> Incident | None:
        """Fetch a single incident by PK + workspace scope, or None."""
        return (
            db.query(Incident)
            .filter(Incident.id == incident_id, Incident.workspace_id == workspace_id)
            .first()
        )

    def update(
        self,
        db: Session,
        incident_id: UUID,
        workspace_id: UUID,
        updates: dict,
    ) -> Incident:
        """Apply *updates* dict to the incident and flush."""
        inc = self.get_by_id_and_workspace(db, incident_id, workspace_id)
        for k, v in updates.items():
            setattr(inc, k, v)
        db.flush()
        return inc

    def count_linked_issues(
        self,
        db: Session,
        incident_id: UUID,
    ) -> int:
        """Return number of issues linked to this incident."""
        return db.query(IncidentIssue).filter(IncidentIssue.incident_id == incident_id).count()

    def get_linked_issue_ids(
        self,
        db: Session,
        incident_id: UUID,
    ) -> list[UUID]:
        """Return all issue IDs linked to this incident."""
        rows = (
            db.query(IncidentIssue.issue_id).filter(IncidentIssue.incident_id == incident_id).all()
        )
        return [r[0] for r in rows]

    def delete_links(
        self,
        db: Session,
        incident_id: UUID,
        issue_ids: list[UUID],
    ) -> int:
        """Delete junction rows for given issue_ids. Returns count deleted."""
        count = (
            db.query(IncidentIssue)
            .filter(
                IncidentIssue.incident_id == incident_id,
                IncidentIssue.issue_id.in_(issue_ids),
            )
            .delete(synchronize_session="fetch")
        )
        db.flush()
        return count

    # -- list / filter (F042) ------------------------------------------------

    def list_by_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        priority: str | None = None,
        owner_id: UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Incident], int]:
        """Return paginated incidents matching filters + total count."""
        q = db.query(Incident).filter(Incident.workspace_id == workspace_id)

        if status is not None:
            q = q.filter(Incident.status == status)
        if severity is not None:
            q = q.filter(Incident.severity == severity)
        if priority is not None:
            q = q.filter(Incident.priority == priority)
        if owner_id is not None:
            q = q.filter(Incident.owner_id == owner_id)

        total = q.count()
        items = q.order_by(Incident.opened_at.desc()).offset(offset).limit(limit).all()
        return items, total

    # -- export (F051) -------------------------------------------------------

    _MAX_EXPORT_ROWS: int = 10_000

    def list_all_for_export(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        priority: str | None = None,
        owner_id: UUID | None = None,
    ) -> tuple[list[Incident], bool]:
        """Return up to ``_MAX_EXPORT_ROWS`` incidents + truncation flag."""
        q = db.query(Incident).filter(Incident.workspace_id == workspace_id)

        if status is not None:
            q = q.filter(Incident.status == status)
        if severity is not None:
            q = q.filter(Incident.severity == severity)
        if priority is not None:
            q = q.filter(Incident.priority == priority)
        if owner_id is not None:
            q = q.filter(Incident.owner_id == owner_id)

        q = q.order_by(Incident.opened_at.desc())
        items = q.limit(self._MAX_EXPORT_ROWS + 1).all()

        truncated = len(items) > self._MAX_EXPORT_ROWS
        if truncated:
            items = items[: self._MAX_EXPORT_ROWS]

        return items, truncated

    def get_sla_info(
        self,
        db: Session,
        incident_ids: list[UUID],
    ) -> dict[UUID, tuple[datetime | None, bool]]:
        """Return SLA breach info for each incident.

        Returns ``{incident_id: (earliest_due_at, has_sla_breach)}``.
        ``has_sla_breach`` is True when any linked issue has ``due_at < now()``
        and is not resolved/closed.
        """
        if not incident_ids:
            return {}

        from app.models.issue import Issue

        now = datetime.now(UTC)

        rows = (
            db.query(
                IncidentIssue.incident_id,
                sa_func.min(Issue.due_at).label("earliest_due"),
                sa_func.bool_or(
                    (Issue.due_at < now) & (~Issue.status.in_(["resolved", "closed"]))
                ).label("has_breach"),
            )
            .join(Issue, Issue.id == IncidentIssue.issue_id)
            .filter(
                IncidentIssue.incident_id.in_(incident_ids),
                Issue.due_at.isnot(None),
                ~Issue.status.in_(["resolved", "closed"]),
            )
            .group_by(IncidentIssue.incident_id)
            .all()
        )

        result: dict[UUID, tuple[datetime | None, bool]] = {
            iid: (None, False) for iid in incident_ids
        }
        for row in rows:
            result[row.incident_id] = (row.earliest_due, bool(row.has_breach))
        return result
