"""
IssueRepository — F031 Automatic Issue Creation / F037 Triage List

Provides data-access methods for the `issues` table.
All methods accept an open SQLAlchemy Session; callers are responsible for
commit / rollback.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, MetaData, String, Table, case, func, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.user import User

# ---------------------------------------------------------------------------
# Lightweight reflection of control.datasets — used only for the LEFT JOIN
# that enriches list results with a human-readable dataset name.
# We do *not* map this as a full ORM model to avoid migrating it.
# ---------------------------------------------------------------------------
_DATASETS_TABLE = Table(
    "datasets",
    MetaData(),
    Column("dataset_id", PGUUID(as_uuid=True)),
    Column("dataset_name", String),
    schema="control",
)
from app.services.issues.issue_models import (
    IssueDetail,
    IssueDomain,
    IssueListItem,
)


class IssueRepository:
    """Data-access layer for the issues table."""

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert(self, db: Session, issue: IssueDomain) -> IssueDomain:
        """
        Persist a new issue and return the populated domain model.

        The method calls ``db.flush()`` so that database-generated defaults
        (id, opened_at, created_at) are reflected back onto the ORM object
        before mapping to the return value.  The caller must ``commit()``.
        """
        orm_obj = Issue(
            tenant_id=issue.tenant_id,
            workspace_id=issue.workspace_id,
            flow_execution_id=issue.flow_execution_id,
            flow_node_result_id=issue.flow_node_result_id,
            rule_id=issue.rule_id,
            dataset_id=issue.dataset_id,
            assignee_id=issue.assignee_id,
            issue_type=issue.issue_type,
            severity=issue.severity,
            status=issue.status,
            title=issue.title,
            impact_summary=issue.impact_summary,
            failure_count=issue.failure_count,
            rows_scanned=issue.rows_scanned,
            pass_rate=issue.pass_rate,
            due_at=issue.due_at,
        )
        db.add(orm_obj)
        db.flush()
        return IssueDomain.model_validate(orm_obj)

    # ------------------------------------------------------------------
    # Sort helpers (F037)
    # ------------------------------------------------------------------

    _SEVERITY_ORDER = case(
        (Issue.severity == "critical", 1),
        (Issue.severity == "major", 2),
        (Issue.severity == "minor", 3),
        (Issue.severity == "informational", 4),
        else_=5,
    )

    _STATUS_ORDER = case(
        (Issue.status == "open", 1),
        (Issue.status == "in_progress", 2),
        (Issue.status == "reopened", 3),
        (Issue.status == "resolved", 4),
        (Issue.status == "closed", 5),
        else_=6,
    )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def _build_list_query(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        assignee_id: str | None = None,
        dataset_id: UUID | None = None,
        overdue: bool = False,
        sort_by: str = "opened_at",
        sort_dir: str = "desc",
    ):
        """Build the filtered/sorted query with LEFT JOINs for denormalized fields."""
        assignee_display = func.coalesce(User.full_name, User.email).label("assignee_display_name")

        query = (
            db.query(
                Issue,
                assignee_display,
                _DATASETS_TABLE.c.dataset_name.label("dataset_name"),
            )
            .outerjoin(User, Issue.assignee_id == User.id)
            .outerjoin(
                _DATASETS_TABLE,
                Issue.dataset_id == _DATASETS_TABLE.c.dataset_id,
            )
            .filter(Issue.workspace_id == workspace_id)
        )

        # --- Filters ---
        if status is not None:
            query = query.filter(Issue.status == status)
        if severity is not None:
            query = query.filter(Issue.severity == severity)
        if assignee_id is not None:
            if assignee_id == "unassigned":
                query = query.filter(Issue.assignee_id.is_(None))
            else:
                query = query.filter(Issue.assignee_id == UUID(assignee_id))
        if dataset_id is not None:
            query = query.filter(Issue.dataset_id == dataset_id)
        if overdue:
            query = query.filter(
                Issue.due_at.isnot(None),
                Issue.due_at < func.now(),
                Issue.status.notin_(["closed", "resolved"]),
            )

        # --- Sort ---
        if sort_by == "severity":
            order_col = self._SEVERITY_ORDER
        elif sort_by == "status":
            order_col = self._STATUS_ORDER
        elif sort_by == "due_at":
            col = Issue.due_at
            if sort_dir == "asc":
                query = query.order_by(col.asc().nullslast())
            else:
                query = query.order_by(col.desc().nullslast())
            return query
        else:
            order_col = getattr(Issue, sort_by)

        if sort_dir == "asc":
            query = query.order_by(order_col.asc())
        else:
            query = query.order_by(order_col.desc())

        return query

    def _row_to_list_item(self, row) -> IssueListItem:
        """Map a (Issue, assignee_display_name, dataset_name) row to IssueListItem."""
        issue, assignee_display_name, dataset_name = row
        return IssueListItem(
            id=issue.id,
            workspace_id=issue.workspace_id,
            issue_type=issue.issue_type,
            severity=issue.severity,
            status=issue.status,
            title=issue.title,
            impact_summary=issue.impact_summary,
            failure_count=issue.failure_count,
            due_at=issue.due_at,
            opened_at=issue.opened_at,
            assignee_id=issue.assignee_id,
            assignee_display_name=assignee_display_name,
            dataset_name=dataset_name,
            updated_at=issue.updated_at,
        )

    def _count_filtered(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        assignee_id: str | None = None,
        dataset_id: UUID | None = None,
        overdue: bool = False,
    ) -> int:
        """
        Return the total number of issues matching the given filters.

        Built as a separate query without text-based JOINs so that
        SQLAlchemy can compile the COUNT without hitting the
        ``'TextClause' object has no attribute 'selectable'`` error.
        """
        q = db.query(func.count(Issue.id)).filter(Issue.workspace_id == workspace_id)
        if status is not None:
            q = q.filter(Issue.status == status)
        if severity is not None:
            q = q.filter(Issue.severity == severity)
        if assignee_id is not None:
            if assignee_id == "unassigned":
                q = q.filter(Issue.assignee_id.is_(None))
            else:
                q = q.filter(Issue.assignee_id == UUID(assignee_id))
        if dataset_id is not None:
            q = q.filter(Issue.dataset_id == dataset_id)
        if overdue:
            q = q.filter(
                Issue.due_at.isnot(None),
                Issue.due_at < func.now(),
                Issue.status.notin_(["closed", "resolved"]),
            )
        return q.scalar() or 0

    def list_by_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        assignee_id: str | None = None,
        dataset_id: UUID | None = None,
        overdue: bool = False,
        sort_by: str = "opened_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueListItem], int]:
        """
        Return a paginated list of issues for *workspace_id*.

        Returns a ``(items, total)`` tuple where *total* is the filtered row
        count (before pagination) and *items* is the current page.
        """
        total: int = self._count_filtered(
            db,
            workspace_id,
            status=status,
            severity=severity,
            assignee_id=assignee_id,
            dataset_id=dataset_id,
            overdue=overdue,
        )

        query = self._build_list_query(
            db,
            workspace_id,
            status=status,
            severity=severity,
            assignee_id=assignee_id,
            dataset_id=dataset_id,
            overdue=overdue,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        offset = (page - 1) * page_size
        rows = query.limit(page_size).offset(offset).all()

        items = [self._row_to_list_item(row) for row in rows]
        return items, total

    def list_all_for_export(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status: str | None = None,
        severity: str | None = None,
        assignee_id: str | None = None,
        dataset_id: UUID | None = None,
        overdue: bool = False,
        sort_by: str = "opened_at",
        sort_dir: str = "desc",
        limit: int = 10_000,
    ) -> tuple[list[IssueListItem], bool]:
        """
        Return all matching issues (up to *limit*) for CSV export.

        Returns ``(items, truncated)`` where *truncated* is True if the
        result set was capped.
        """
        query = self._build_list_query(
            db,
            workspace_id,
            status=status,
            severity=severity,
            assignee_id=assignee_id,
            dataset_id=dataset_id,
            overdue=overdue,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )

        total: int = self._count_filtered(
            db,
            workspace_id,
            status=status,
            severity=severity,
            assignee_id=assignee_id,
            dataset_id=dataset_id,
            overdue=overdue,
        )
        rows = query.limit(limit).all()

        items = [self._row_to_list_item(row) for row in rows]
        return items, total > limit

    def get_by_id_and_workspace(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
    ) -> IssueDetail | None:
        """
        Fetch a single issue by primary key, scoped to *workspace_id*.

        Returns ``None`` when the issue does not exist or belongs to a
        different workspace (prevents cross-workspace data leakage).
        """
        row = (
            db.query(Issue).filter(Issue.id == issue_id, Issue.workspace_id == workspace_id).first()
        )
        if row is None:
            return None
        return IssueDetail.model_validate(row)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
        updates: dict,
    ) -> IssueDetail | None:
        """
        Apply *updates* to the issue identified by *issue_id* + *workspace_id*.

        Returns the updated ``IssueDetail`` or ``None`` if the issue was not
        found.  The caller must ``commit()``.
        """
        row = (
            db.query(Issue).filter(Issue.id == issue_id, Issue.workspace_id == workspace_id).first()
        )
        if row is None:
            return None
        for field, value in updates.items():
            setattr(row, field, value)
        db.flush()
        return IssueDetail.model_validate(row)

    # ------------------------------------------------------------------
    # F032 — Grouping
    # ------------------------------------------------------------------

    def find_open_for_grouping(
        self,
        db: Session,
        workspace_id: UUID,
        rule_id: UUID,
        dataset_id: UUID,
        policy: str,
        *,
        day_start_utc: datetime | None = None,
        day_end_utc: datetime | None = None,
    ) -> IssueDomain | None:
        """
        Find the most recently opened open/in_progress/reopened issue for
        workspace_id + rule_id + dataset_id.

        For policy 'one_per_day', additionally filters WHERE
        opened_at >= day_start_utc AND opened_at < day_end_utc.

        Uses SELECT FOR UPDATE to acquire a row-level lock.
        Returns IssueDomain or None.
        """
        _OPEN_STATUSES = ("open", "in_progress", "reopened")

        if policy == "one_per_day" and day_start_utc is not None and day_end_utc is not None:
            sql = text(
                "SELECT * FROM public.issues "
                "WHERE workspace_id = :workspace_id "
                "  AND rule_id = :rule_id "
                "  AND dataset_id = :dataset_id "
                "  AND status IN ('open', 'in_progress', 'reopened') "
                "  AND opened_at >= :day_start "
                "  AND opened_at < :day_end "
                "ORDER BY opened_at DESC "
                "LIMIT 1 "
                "FOR UPDATE"
            )
            result = db.execute(
                sql,
                {
                    "workspace_id": str(workspace_id),
                    "rule_id": str(rule_id),
                    "dataset_id": str(dataset_id),
                    "day_start": day_start_utc,
                    "day_end": day_end_utc,
                },
            )
        else:
            sql = text(
                "SELECT * FROM public.issues "
                "WHERE workspace_id = :workspace_id "
                "  AND rule_id = :rule_id "
                "  AND dataset_id = :dataset_id "
                "  AND status IN ('open', 'in_progress', 'reopened') "
                "ORDER BY opened_at DESC "
                "LIMIT 1 "
                "FOR UPDATE"
            )
            result = db.execute(
                sql,
                {
                    "workspace_id": str(workspace_id),
                    "rule_id": str(rule_id),
                    "dataset_id": str(dataset_id),
                },
            )

        row = result.fetchone()
        if row is None:
            return None

        # Map raw row to IssueDomain via ORM query (avoids manual column mapping)
        issue_id = (
            row[0]
            if isinstance(row[0], __import__("uuid").UUID)
            else __import__("uuid").UUID(str(row[0]))
        )
        orm_obj = db.query(Issue).filter(Issue.id == issue_id).first()
        if orm_obj is None:
            return None
        return IssueDomain.model_validate(orm_obj)

    def update_for_grouping(
        self,
        db: Session,
        issue_id: UUID,
        delta_rows_failed: int,
        new_impact_summary: str,
        new_last_seen_at: datetime,
    ) -> IssueDomain:
        """
        Atomically increment failure_count and update grouping metadata.

        UPDATE public.issues
        SET failure_count = failure_count + :delta,
            impact_summary = :impact_summary,
            last_seen_at   = :last_seen_at,
            updated_at     = NOW()
        WHERE id = :issue_id

        Returns the post-update IssueDomain.
        Caller must commit.
        """
        sql = text(
            "UPDATE public.issues "
            "SET failure_count = failure_count + :delta, "
            "    impact_summary = :impact_summary, "
            "    last_seen_at   = :last_seen_at, "
            "    updated_at     = NOW() "
            "WHERE id = :issue_id"
        )
        db.execute(
            sql,
            {
                "delta": delta_rows_failed,
                "impact_summary": new_impact_summary,
                "last_seen_at": new_last_seen_at,
                "issue_id": str(issue_id),
            },
        )
        db.flush()

        # Re-fetch to get updated state
        orm_obj = db.query(Issue).filter(Issue.id == issue_id).first()
        return IssueDomain.model_validate(orm_obj)
