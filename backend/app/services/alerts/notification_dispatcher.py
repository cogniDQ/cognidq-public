"""
F116 Notification Dispatcher
==============================

Actually delivers pending notification events via their configured channels
(email via SMTP, webhook via HTTP POST). Includes retry logic.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.models.alert_channel import AlertChannel
from app.models.notification_event import NotificationEvent

logger = logging.getLogger(__name__)


class NotificationDispatchError(Exception):
    """Raised when a notification delivery fails."""


class NotificationDispatcher:
    """Delivers pending NotificationEvent records via their AlertChannel."""

    def dispatch_event(self, db: Session, event_id: UUID) -> bool:
        """
        Attempt to deliver a single notification event.
        Returns True on success, False on failure (updates DB status).
        """
        event = (
            db.query(NotificationEvent)
            .filter(
                NotificationEvent.id == event_id,
            )
            .first()
        )
        if not event:
            logger.warning("dispatch: event %s not found", event_id)
            return False

        if event.status not in ("pending", "retrying"):
            logger.debug("dispatch: event %s status=%s, skipping", event_id, event.status)
            return False

        channel = (
            db.query(AlertChannel)
            .filter(
                AlertChannel.id == event.alert_channel_id,
            )
            .first()
        )
        if not channel:
            self._mark_failed(db, event, "Alert channel not found")
            return False

        if not channel.enabled:
            self._mark_failed(db, event, "Alert channel is disabled")
            return False

        try:
            if channel.channel_type == "email":
                self._deliver_email(
                    channel.configuration, event, db=db, tenant_id=channel.tenant_id
                )
            elif channel.channel_type == "webhook":
                self._deliver_webhook(channel.configuration, event)
            elif channel.channel_type == "slack":
                self._deliver_slack(channel.configuration, event)
            else:
                raise NotificationDispatchError(f"Unsupported channel type: {channel.channel_type}")

            event.status = "sent"
            event.sent_at = datetime.now(UTC)
            event.delivered_at = datetime.now(UTC)
            event.last_error = None
            db.commit()
            logger.info("dispatch: event %s sent via %s", event_id, channel.channel_type)
            return True

        except Exception as exc:
            event.retry_count = (event.retry_count or 0) + 1
            event.last_error = str(exc)[:2000]
            if event.retry_count >= (event.max_retries or 3):
                event.status = "failed"
                logger.warning("dispatch: event %s failed permanently: %s", event_id, exc)
            else:
                event.status = "retrying"
                logger.info(
                    "dispatch: event %s retry %d/%d: %s",
                    event_id,
                    event.retry_count,
                    event.max_retries,
                    exc,
                )
            db.commit()
            return False

    def dispatch_pending(
        self, db: Session, workspace_id: UUID | None = None, batch_size: int = 50
    ) -> dict[str, int]:
        """
        Process a batch of pending/retrying events.
        Returns counts: {sent, failed, skipped}.
        """
        query = db.query(NotificationEvent).filter(
            NotificationEvent.status.in_(["pending", "retrying"]),
        )
        if workspace_id:
            query = query.filter(NotificationEvent.workspace_id == workspace_id)

        events = query.order_by(NotificationEvent.created_at).limit(batch_size).all()

        counts = {"sent": 0, "failed": 0, "skipped": 0}
        for event in events:
            ok = self.dispatch_event(db, event.id)
            if ok:
                counts["sent"] += 1
            else:
                if event.status == "failed":
                    counts["failed"] += 1
                else:
                    counts["skipped"] += 1

        return counts

    def send_test(self, db: Session, channel_id: UUID, workspace_id: UUID) -> dict:
        """Send a test notification to verify channel configuration."""
        channel = (
            db.query(AlertChannel)
            .filter(
                AlertChannel.id == channel_id,
                AlertChannel.workspace_id == workspace_id,
            )
            .first()
        )
        if not channel:
            raise NotificationDispatchError("Channel not found")

        # Build a transient event object (not persisted) to reuse delivery methods
        test_event = NotificationEvent()
        test_event.workspace_id = workspace_id
        test_event.recipient = (
            channel.configuration.get("from_address", "test@example.com")
            if channel.channel_type == "email"
            else channel.configuration.get("url", "test")
        )
        test_event.payload = {
            "subject": "Test Notification",
            "body": "This is a test notification from DQ Hub.",
        }

        try:
            if channel.channel_type == "email":
                self._deliver_email(
                    channel.configuration, test_event, db=db, tenant_id=channel.tenant_id
                )
            elif channel.channel_type == "webhook":
                self._deliver_webhook(channel.configuration, test_event)
            elif channel.channel_type == "slack":
                self._deliver_slack(channel.configuration, test_event)
            else:
                raise NotificationDispatchError(f"Unsupported channel type: {channel.channel_type}")
            return {
                "success": True,
                "message": f"Test {channel.channel_type} notification sent successfully",
            }
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    # ------------------------------------------------------------------
    # Private delivery methods
    # ------------------------------------------------------------------

    def _deliver_email(
        self, config: dict, event: NotificationEvent, *, db=None, tenant_id=None
    ) -> None:
        """Send email via SMTP using channel configuration with tenant fallback.

        Resolution order for SMTP credentials:
          1. AlertChannel ``configuration`` if it contains an ``smtp_host``.
          2. Tenant-scoped SMTP settings (control.tenant_settings) when
             ``smtp_enabled`` is true and ``db`` + ``tenant_id`` are provided.
          3. None / failure — raises NotificationDispatchError.
        """
        host = config.get("smtp_host")
        port = int(config.get("smtp_port", 587))
        username = config.get("smtp_username", "")
        password = config.get("smtp_password", "")
        use_tls = config.get("smtp_tls", True)
        from_addr = config.get("from_address", username)

        if not host and db is not None and tenant_id is not None:
            try:
                from app.services.tenant.settings_service import TenantSettingsService

                tenant_cfg = TenantSettingsService().get_smtp_config_for_dispatch(db, tenant_id)
                if tenant_cfg is not None:
                    host = tenant_cfg.host
                    port = int(tenant_cfg.port or 587)
                    username = tenant_cfg.username or ""
                    password = tenant_cfg.password or ""
                    use_tls = bool(tenant_cfg.use_tls)
                    from_addr = tenant_cfg.from_address or username
            except Exception as exc:  # noqa: BLE001
                logger.warning("tenant SMTP fallback failed: %s", exc)

        if not host:
            raise NotificationDispatchError(
                "No SMTP host configured (channel config and tenant settings both missing)"
            )

        payload = event.payload or {}
        subject = payload.get("subject", "DQ Hub Notification")
        body = payload.get("body", "")

        msg = MIMEMultipart("alternative")
        msg["From"] = from_addr
        msg["To"] = event.recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        if payload.get("html_body"):
            msg.attach(MIMEText(payload["html_body"], "html"))

        try:
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP(host, port, timeout=30)
            if username and password:
                server.login(username, password)
            server.sendmail(from_addr, [event.recipient], msg.as_string())
            server.quit()
        except smtplib.SMTPException as exc:
            raise NotificationDispatchError(f"SMTP error: {exc}") from exc

    def _deliver_webhook(self, config: dict, event: NotificationEvent) -> None:
        """POST event payload to webhook URL."""
        url = config.get("url")
        if not url:
            raise NotificationDispatchError("Webhook URL not configured")

        headers = {"Content-Type": "application/json"}
        if config.get("secret"):
            headers["X-Webhook-Secret"] = config["secret"]
        extra_headers = config.get("headers")
        if isinstance(extra_headers, dict):
            headers.update(extra_headers)

        payload = event.payload or {}
        body = {
            "event_id": str(event.id) if event.id else None,
            "alert_rule_id": str(event.alert_rule_id) if event.alert_rule_id else None,
            "workspace_id": str(event.workspace_id) if event.workspace_id else None,
            "recipient": event.recipient,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                raise NotificationDispatchError(
                    f"Webhook returned {resp.status_code}: {resp.text[:500]}"
                )

    def _deliver_slack(self, config: dict, event: NotificationEvent) -> None:
        """POST a Slack-formatted message to an incoming webhook URL.

        Channel config:
          - webhook_url (required) — Slack incoming webhook URL (https://hooks.slack.com/services/...)
          - channel (optional) — override channel, e.g. "#dq-alerts"
          - username (optional) — bot username override
          - icon_emoji (optional) — e.g. ":warning:"
        """
        webhook_url = config.get("webhook_url") or config.get("url")
        if not webhook_url:
            raise NotificationDispatchError("Slack webhook URL not configured")

        payload = event.payload or {}
        subject = payload.get("subject", "DQ Hub Notification")
        body = payload.get("body", "")
        trigger_type = payload.get("trigger_type", "")
        severity = (payload.get("severity") or "").lower()

        color_map = {
            "blocker": "#B91C1C",
            "critical": "#B91C1C",
            "major": "#C2410C",
            "high": "#C2410C",
            "minor": "#A16207",
            "medium": "#A16207",
            "info": "#1D4ED8",
            "low": "#1D4ED8",
        }
        color = color_map.get(severity, "#1E40AF")

        message = {
            "text": f"*{subject}*",
            "attachments": [
                {
                    "color": color,
                    "text": body,
                    "footer": f"CogniDQ \u2022 {trigger_type}" if trigger_type else "CogniDQ",
                    "ts": int(datetime.now(UTC).timestamp()),
                }
            ],
        }
        for opt_key in ("channel", "username", "icon_emoji"):
            if config.get(opt_key):
                message[opt_key] = config[opt_key]

        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(webhook_url, json=message)
                if resp.status_code >= 400:
                    raise NotificationDispatchError(
                        f"Slack webhook returned {resp.status_code}: {resp.text[:500]}"
                    )
        except httpx.HTTPError as exc:
            raise NotificationDispatchError(f"Slack delivery error: {exc}") from exc

    @staticmethod
    def _mark_failed(db: Session, event: NotificationEvent, error: str) -> None:
        event.status = "failed"
        event.last_error = error
        db.commit()
