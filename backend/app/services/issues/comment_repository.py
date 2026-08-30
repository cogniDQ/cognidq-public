"""
F036 Issue Comment Repository
==============================

Data-access layer for the ``issue_comments`` table.
All methods accept an open SQLAlchemy Session; callers own commit/rollback.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.issue_comment import IssueComment


class IssueCommentRepository:
    """CRUD operations for issue comments (insert + read only — immutable)."""

    def insert(self, db: Session, comment: IssueComment) -> IssueComment:
        """Persist a new comment. Flushes to populate server defaults."""
        db.add(comment)
        db.flush()
        return comment

    def list_by_issue(
        self,
        db: Session,
        issue_id: UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[IssueComment], int]:
        """Return (comments, total_count) for a given issue, newest first."""
        base = db.query(IssueComment).filter(IssueComment.issue_id == issue_id)
        total = base.count()
        items = base.order_by(IssueComment.created_at.desc()).offset(offset).limit(limit).all()
        return items, total
