"""
F044 Alert Channel Service
============================

CRUD operations for alert channels with validation and audit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.alert_channel import AlertChannel
from app.services.alerts.alert_channel_models import AlertChannelResponse
from app.services.alerts.alert_channel_repository import AlertChannelRepository
from app.services.audit.hooks import build_alert_channel_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CHANNEL_TYPES = frozenset({"email", "webhook", "slack"})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AlertChannelValidationError(Exception):
    """Raised when alert channel input fails validation."""


class AlertChannelNotFoundError(Exception):
    """Raised when an alert channel is not found in the workspace."""


class DuplicateAlertChannelNameError(Exception):
    """Raised when the name already exists in the workspace."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AlertChannelService:
    """CRUD for alert channels."""

    def __init__(
        self,
        repo: AlertChannelRepository | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._repo = repo or AlertChannelRepository()
        self._audit = audit_service or AuditService()

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _to_response(ch: AlertChannel) -> AlertChannelResponse:
        return AlertChannelResponse(
            id=ch.id,
            workspace_id=ch.workspace_id,
            name=ch.name,
            channel_type=ch.channel_type,
            configuration=ch.configuration or {},
            enabled=ch.enabled,
            created_by_user_id=ch.created_by_user_id,
            created_at=ch.created_at,
            updated_at=ch.updated_at,
        )

    # -- create ---------------------------------------------------------------

    def create_channel(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        created_by_user_id: UUID,
        name: str,
        channel_type: str,
        configuration: dict,
        enabled: bool = True,
        audit_ctx: AuditContext | None = None,
    ) -> AlertChannelResponse:
        name = (name or "").strip()
        if not name or len(name) > 200:
            raise AlertChannelValidationError("name must be 1–200 characters")
        if channel_type not in VALID_CHANNEL_TYPES:
            raise AlertChannelValidationError(f"invalid channel_type: {channel_type}")

        # Webhook must have url
        if channel_type == "webhook" and not configuration.get("url"):
            raise AlertChannelValidationError("webhook configuration requires 'url'")

        if self._repo.name_exists(db, workspace_id, name):
            raise DuplicateAlertChannelNameError(f"name already exists: {name}")

        channel = AlertChannel(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            name=name,
            channel_type=channel_type,
            configuration=configuration,
            enabled=enabled,
            created_by_user_id=created_by_user_id,
        )
        channel = self._repo.insert(db, channel)

        if audit_ctx is not None:
            entry = build_alert_channel_audit_entry(
                ctx=audit_ctx,
                action="alert_channel_created",
                workspace_id=workspace_id,
                alert_channel_id=channel.id,
                after_state={"name": name, "channel_type": channel_type, "enabled": enabled},
            )
            self._audit.write(db, entry)

        return self._to_response(channel)

    # -- read -----------------------------------------------------------------

    def get_channel(
        self,
        db: Session,
        *,
        channel_id: UUID,
        workspace_id: UUID,
    ) -> AlertChannelResponse:
        ch = self._repo.get_by_id_and_workspace(db, channel_id, workspace_id)
        if ch is None:
            raise AlertChannelNotFoundError(f"alert channel {channel_id} not found")
        return self._to_response(ch)

    def list_channels(
        self,
        db: Session,
        *,
        workspace_id: UUID,
    ) -> list[AlertChannelResponse]:
        channels = self._repo.list_by_workspace(db, workspace_id)
        return [self._to_response(c) for c in channels]

    # -- update ---------------------------------------------------------------

    def update_channel(
        self,
        db: Session,
        *,
        channel_id: UUID,
        workspace_id: UUID,
        audit_ctx: AuditContext | None = None,
        name: str | None = None,
        channel_type: str | None = None,
        configuration: dict | None = None,
        enabled: bool | None = None,
    ) -> AlertChannelResponse:
        ch = self._repo.get_by_id_and_workspace(db, channel_id, workspace_id)
        if ch is None:
            raise AlertChannelNotFoundError(f"alert channel {channel_id} not found")

        if name is not None:
            name = name.strip()
            if not name or len(name) > 200:
                raise AlertChannelValidationError("name must be 1–200 characters")
            if self._repo.name_exists(db, workspace_id, name, exclude_id=channel_id):
                raise DuplicateAlertChannelNameError(f"name already exists: {name}")
            ch.name = name

        if channel_type is not None:
            if channel_type not in VALID_CHANNEL_TYPES:
                raise AlertChannelValidationError(f"invalid channel_type: {channel_type}")
            ch.channel_type = channel_type

        if configuration is not None:
            ch.configuration = configuration

        if enabled is not None:
            ch.enabled = enabled

        ch = self._repo.update(db, ch)

        if audit_ctx is not None:
            entry = build_alert_channel_audit_entry(
                ctx=audit_ctx,
                action="alert_channel_updated",
                workspace_id=workspace_id,
                alert_channel_id=ch.id,
                after_state={
                    "name": ch.name,
                    "channel_type": ch.channel_type,
                    "enabled": ch.enabled,
                },
            )
            self._audit.write(db, entry)

        return self._to_response(ch)

    # -- delete ---------------------------------------------------------------

    def delete_channel(
        self,
        db: Session,
        *,
        channel_id: UUID,
        workspace_id: UUID,
        audit_ctx: AuditContext | None = None,
    ) -> None:
        ch = self._repo.get_by_id_and_workspace(db, channel_id, workspace_id)
        if ch is None:
            raise AlertChannelNotFoundError(f"alert channel {channel_id} not found")

        if audit_ctx is not None:
            entry = build_alert_channel_audit_entry(
                ctx=audit_ctx,
                action="alert_channel_deleted",
                workspace_id=workspace_id,
                alert_channel_id=ch.id,
                after_state={"name": ch.name},
            )
            self._audit.write(db, entry)

        self._repo.delete(db, channel_id, workspace_id)
