"""
F036 Timeline Service
======================

Merges issue comments and audit-log events into a single, time-ordered
activity stream for a given issue.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.issues.comment_models import TimelineEntry, TimelinePage
from app.services.issues.comment_repository import IssueCommentRepository

logger = logging.getLogger(__name__)


class TimelineService:
    """Builds a unified issue timeline from comments + audit events."""

    def __init__(
        self,
        *,
        comment_repo: IssueCommentRepository | None = None,
    ):
        self._comment_repo = comment_repo or IssueCommentRepository()

    def get_timeline(
        self,
        db: Session,
        issue_id: UUID,
        workspace_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
    ) -> TimelinePage:
        """
        Return a paginated, time-ordered timeline for an issue.

        Steps:
        1. Fetch all comments for the issue
        2. Fetch all audit events for the issue
        3. Merge into a single list sorted by timestamp desc
        4. Apply pagination
        5. Resolve actor names
        """
        # --- 1. Comments ---
        comments, _comment_total = self._comment_repo.list_by_issue(
            db,
            issue_id,
            offset=0,
            limit=10_000,  # fetch all, paginate after merge
        )
        comment_entries = [
            TimelineEntry(
                entry_type="comment",
                id=c.id,
                timestamp=c.created_at,
                actor_id=c.author_id,
                actor_name=None,
                content={"body": c.body},
            )
            for c in comments
        ]

        # --- 2. Audit events ---
        audit_rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.target_entity_type == "issue",
                AuditLog.target_entity_id == issue_id,
            )
            .order_by(AuditLog.occurred_at.desc())
            .all()
        )
        event_entries = [
            TimelineEntry(
                entry_type="event",
                id=a.log_id,
                timestamp=a.occurred_at,
                actor_id=a.actor_id,
                actor_name=None,
                content={
                    "action": a.action_type,
                    "before": a.previous_data,
                    "after": a.new_data,
                },
            )
            for a in audit_rows
        ]

        # --- 3. Merge + sort (newest first) ---
        merged = sorted(
            comment_entries + event_entries,
            key=lambda e: e.timestamp,
            reverse=True,
        )
        total = len(merged)

        # --- 4. Paginate ---
        offset = (page - 1) * page_size
        page_items = merged[offset : offset + page_size]
        has_next = (offset + page_size) < total

        # --- 5. Resolve actor names ---
        actor_ids = {e.actor_id for e in page_items if e.actor_id}
        if actor_ids:
            users = (
                db.query(User.id, User.full_name, User.email).filter(User.id.in_(actor_ids)).all()
            )
            name_map: dict[UUID, str] = {}
            for u in users:
                name_map[u.id] = u.full_name or u.email or str(u.id)
            for entry in page_items:
                if entry.actor_id and entry.actor_id in name_map:
                    entry.actor_name = name_map[entry.actor_id]

        return TimelinePage(
            items=page_items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=has_next,
        )
