"""
F044 Alert Channel Repository
===============================

Data-access layer for AlertChannel ORM objects.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.alert_channel import AlertChannel


class AlertChannelRepository:
    """CRUD operations for the alert_channels table."""

    # -- write ----------------------------------------------------------------

    def insert(self, db: Session, channel: AlertChannel) -> AlertChannel:
        db.add(channel)
        db.flush()
        return channel

    def update(self, db: Session, channel: AlertChannel) -> AlertChannel:
        db.flush()
        db.refresh(channel)
        return channel

    def delete(self, db: Session, channel_id: UUID, workspace_id: UUID) -> bool:
        channel = self.get_by_id_and_workspace(db, channel_id, workspace_id)
        if channel is None:
            return False
        db.delete(channel)
        db.flush()
        return True

    # -- read -----------------------------------------------------------------

    def get_by_id_and_workspace(
        self,
        db: Session,
        channel_id: UUID,
        workspace_id: UUID,
    ) -> AlertChannel | None:
        return (
            db.query(AlertChannel)
            .filter(AlertChannel.id == channel_id, AlertChannel.workspace_id == workspace_id)
            .first()
        )

    def list_by_workspace(
        self,
        db: Session,
        workspace_id: UUID,
    ) -> list[AlertChannel]:
        return (
            db.query(AlertChannel)
            .filter(AlertChannel.workspace_id == workspace_id)
            .order_by(AlertChannel.created_at.desc())
            .all()
        )

    def name_exists(
        self,
        db: Session,
        workspace_id: UUID,
        name: str,
        *,
        exclude_id: UUID | None = None,
    ) -> bool:
        q = db.query(AlertChannel.id).filter(
            AlertChannel.workspace_id == workspace_id,
            AlertChannel.name == name,
        )
        if exclude_id is not None:
            q = q.filter(AlertChannel.id != exclude_id)
        return q.first() is not None
