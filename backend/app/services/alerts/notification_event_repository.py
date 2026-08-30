"""
F045 Notification Event Repository
====================================

Data-access layer for NotificationEvent ORM objects.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.notification_event import NotificationEvent


class NotificationEventRepository:
    """CRUD operations for the notification_events table."""

    # -- write ----------------------------------------------------------------

    def insert(self, db: Session, event: NotificationEvent) -> NotificationEvent:
        db.add(event)
        db.flush()
        return event

    def update_status(
        self,
        db: Session,
        event_id: UUID,
        workspace_id: UUID,
        **kwargs,
    ) -> NotificationEvent | None:
        event = self.get_by_id_and_workspace(db, event_id, workspace_id)
        if event is None:
            return None
        for key, value in kwargs.items():
            if hasattr(event, key):
                setattr(event, key, value)
        db.flush()
        db.refresh(event)
        return event

    # -- read -----------------------------------------------------------------

    def get_by_id_and_workspace(
        self,
        db: Session,
        event_id: UUID,
        workspace_id: UUID,
    ) -> NotificationEvent | None:
        return (
            db.query(NotificationEvent)
            .filter(
                NotificationEvent.id == event_id,
                NotificationEvent.workspace_id == workspace_id,
            )
            .first()
        )

    def list_by_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        *,
        status_filter: str | None = None,
        rule_filter: UUID | None = None,
        channel_filter: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[NotificationEvent]:
        q = db.query(NotificationEvent).filter(
            NotificationEvent.workspace_id == workspace_id,
        )
        if status_filter is not None:
            q = q.filter(NotificationEvent.status == status_filter)
        if rule_filter is not None:
            q = q.filter(NotificationEvent.alert_rule_id == rule_filter)
        if channel_filter is not None:
            q = q.filter(NotificationEvent.alert_channel_id == channel_filter)
        return q.order_by(NotificationEvent.created_at.desc()).limit(limit).offset(offset).all()

    def count_by_workspace_and_status(
        self,
        db: Session,
        workspace_id: UUID,
    ) -> dict[str, int]:
        rows = (
            db.query(
                NotificationEvent.status,
                sa_func.count(NotificationEvent.id),
            )
            .filter(NotificationEvent.workspace_id == workspace_id)
            .group_by(NotificationEvent.status)
            .all()
        )
        return {status: count for status, count in rows}
