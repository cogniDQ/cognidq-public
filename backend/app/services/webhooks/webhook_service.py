"""
F059 — Webhook and Event Delivery — Service Layer
==================================================

Provides:
  WebhookSubscriptionService  — CRUD for webhook subscriptions
  WebhookDispatchService      — Signs and dispatches webhook payloads with retry logic
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.webhook import WebhookDeliveryLog, WebhookSubscription

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_EVENT_TYPES = frozenset(
    {
        "execution_failed",
        "issue_created",
        "incident_created",
        "incident_updated",
    }
)

MAX_SUBSCRIPTIONS_PER_WORKSPACE = 20
DEFAULT_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = [30, 120, 300]  # 30s, 2min, 5min

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class WebhookNotFoundError(Exception):
    """Raised when a subscription does not exist in the workspace."""


class WebhookValidationError(Exception):
    """Raised when a subscription payload fails validation."""


class WebhookLimitError(Exception):
    """Raised when workspace exceeds the subscription limit."""


# ---------------------------------------------------------------------------
# Subscription service
# ---------------------------------------------------------------------------


class WebhookSubscriptionService:
    """CRUD operations for webhook subscriptions."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_subscription(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        name: str,
        target_url: str,
        event_types: list[str],
        enabled: bool = True,
    ) -> WebhookSubscription:
        name = (name or "").strip()
        if not name or len(name) > 200:
            raise WebhookValidationError("name must be 1–200 characters")
        if not target_url or not target_url.startswith(("http://", "https://")):
            raise WebhookValidationError("target_url must be a valid http/https URL")
        invalid = [e for e in event_types if e not in VALID_EVENT_TYPES]
        if invalid:
            raise WebhookValidationError(
                f"invalid event_types: {invalid}. Valid: {sorted(VALID_EVENT_TYPES)}"
            )
        if not event_types:
            raise WebhookValidationError("event_types must not be empty")

        existing_count = db.execute(
            select(WebhookSubscription).where(WebhookSubscription.workspace_id == workspace_id)
        ).all()
        if len(existing_count) >= MAX_SUBSCRIPTIONS_PER_WORKSPACE:
            raise WebhookLimitError(
                f"workspace exceeds {MAX_SUBSCRIPTIONS_PER_WORKSPACE} webhook subscriptions"
            )

        secret_key = secrets.token_hex(32)  # 256-bit HMAC key

        sub = WebhookSubscription(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            name=name,
            target_url=target_url,
            secret_key=secret_key,
            event_types=event_types,
            enabled=enabled,
            created_by=actor_id,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_subscriptions(self, db: Session, workspace_id: UUID) -> list[WebhookSubscription]:
        result = db.execute(
            select(WebhookSubscription)
            .where(WebhookSubscription.workspace_id == workspace_id)
            .order_by(WebhookSubscription.created_at)
        )
        return list(result.scalars().all())

    def get_subscription(
        self, db: Session, subscription_id: UUID, workspace_id: UUID
    ) -> WebhookSubscription | None:
        result = db.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.id == subscription_id,
                WebhookSubscription.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_subscription(
        self,
        db: Session,
        subscription_id: UUID,
        workspace_id: UUID,
        *,
        name: str | None = None,
        target_url: str | None = None,
        event_types: list[str] | None = None,
        enabled: bool | None = None,
    ) -> WebhookSubscription:
        sub = self.get_subscription(db, subscription_id, workspace_id)
        if sub is None:
            raise WebhookNotFoundError(f"webhook subscription {subscription_id} not found")

        if name is not None:
            name = name.strip()
            if not name or len(name) > 200:
                raise WebhookValidationError("name must be 1–200 characters")
            sub.name = name

        if target_url is not None:
            if not target_url.startswith(("http://", "https://")):
                raise WebhookValidationError("target_url must be a valid http/https URL")
            sub.target_url = target_url

        if event_types is not None:
            invalid = [e for e in event_types if e not in VALID_EVENT_TYPES]
            if invalid:
                raise WebhookValidationError(f"invalid event_types: {invalid}")
            if not event_types:
                raise WebhookValidationError("event_types must not be empty")
            sub.event_types = event_types

        if enabled is not None:
            sub.enabled = enabled

        sub.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(sub)
        return sub

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_subscription(self, db: Session, subscription_id: UUID, workspace_id: UUID) -> bool:
        sub = self.get_subscription(db, subscription_id, workspace_id)
        if sub is None:
            return False
        db.delete(sub)
        db.commit()
        return True


# ---------------------------------------------------------------------------
# Dispatch service
# ---------------------------------------------------------------------------


class WebhookDispatchService:
    """Signs payloads and dispatches webhook HTTP requests.

    Signing: ``X-DQ-Signature: sha256=<hmac_hex>``
    Payload envelope::

        {
            "event_type": "<type>",
            "occurred_at": "<iso8601>",
            "workspace_id": "<uuid>",
            "data": { ... }
        }
    """

    # ------------------------------------------------------------------
    # Public — enqueue event (writes delivery_log rows synchronously,
    #          dispatches immediately; retries can be offloaded to Celery)
    # ------------------------------------------------------------------

    def dispatch_event(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        event_type: str,
        data: dict,
    ) -> list[WebhookDeliveryLog]:
        """Find all active subscriptions for this workspace + event_type and
        attempt delivery. Returns list of delivery log entries created."""

        if event_type not in VALID_EVENT_TYPES:
            logger.warning("Unknown webhook event_type=%s — skipping dispatch", event_type)
            return []

        # Find enabled subscriptions for this event type
        result = db.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.workspace_id == workspace_id,
                WebhookSubscription.enabled.is_(True),
            )
        )
        subscriptions = [s for s in result.scalars().all() if event_type in (s.event_types or [])]

        if not subscriptions:
            return []

        now = datetime.now(UTC)
        payload_body = {
            "event_type": event_type,
            "occurred_at": now.isoformat(),
            "workspace_id": str(workspace_id),
            "data": data,
        }

        logs: list[WebhookDeliveryLog] = []
        for sub in subscriptions:
            log = WebhookDeliveryLog(
                subscription_id=sub.id,
                workspace_id=workspace_id,
                event_type=event_type,
                payload=payload_body,
                status="pending",
                attempt_count=0,
                max_attempts=DEFAULT_MAX_ATTEMPTS,
            )
            db.add(log)
            db.flush()  # get ID

            # Attempt delivery inline
            success, http_code, error = self._send(sub.target_url, sub.secret_key, payload_body)
            log.attempt_count = 1
            log.last_attempt_at = datetime.now(UTC)
            log.http_response_code = http_code

            if success:
                log.status = "delivered"
                log.delivered_at = datetime.now(UTC)
            else:
                log.last_error = error
                if log.attempt_count < log.max_attempts:
                    log.status = "retrying"
                    delay = RETRY_BACKOFF_SECONDS[
                        min(log.attempt_count - 1, len(RETRY_BACKOFF_SECONDS) - 1)
                    ]
                    log.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
                else:
                    log.status = "abandoned"

            logs.append(log)

        db.commit()
        return logs

    # ------------------------------------------------------------------
    # Retry pending/retrying deliveries
    # ------------------------------------------------------------------

    def retry_pending(self, db: Session) -> int:
        """Re-attempt delivery for logs in 'retrying' state where next_attempt_at <= now.

        Returns the number of logs processed.
        """
        now = datetime.now(UTC)
        result = db.execute(
            select(WebhookDeliveryLog).where(
                WebhookDeliveryLog.status == "retrying",
                WebhookDeliveryLog.next_attempt_at <= now,
            )
        )
        logs = list(result.scalars().all())

        for log in logs:
            sub_result = db.execute(
                select(WebhookSubscription).where(WebhookSubscription.id == log.subscription_id)
            )
            sub = sub_result.scalar_one_or_none()
            if sub is None or not sub.enabled:
                log.status = "abandoned"
                log.last_error = "Subscription deleted or disabled"
                continue

            success, http_code, error = self._send(sub.target_url, sub.secret_key, log.payload)
            log.attempt_count += 1
            log.last_attempt_at = now
            log.http_response_code = http_code

            if success:
                log.status = "delivered"
                log.delivered_at = now
                log.last_error = None
            else:
                log.last_error = error
                if log.attempt_count >= log.max_attempts:
                    log.status = "abandoned"
                else:
                    delay = RETRY_BACKOFF_SECONDS[
                        min(log.attempt_count, len(RETRY_BACKOFF_SECONDS) - 1)
                    ]
                    log.next_attempt_at = now + timedelta(seconds=delay)

        db.commit()
        return len(logs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sign_payload(secret_key: str, body: bytes) -> str:
        """Return ``sha256=<hex>`` signature for the given body using HMAC-SHA256."""
        sig = hmac.new(secret_key.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    @staticmethod
    def _send(
        target_url: str, secret_key: str, payload: dict, timeout: float = 10.0
    ) -> tuple[bool, int | None, str | None]:
        """Attempt a single HTTP POST.

        Returns (success, http_status_code, error_message).
        """
        try:
            body = json.dumps(payload, default=str).encode("utf-8")
            signature = WebhookDispatchService._sign_payload(secret_key, body)
            headers = {
                "Content-Type": "application/json",
                "X-DQ-Signature": signature,
                "User-Agent": "DataQuality.AI-Webhook/1.0",
            }
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(target_url, content=body, headers=headers)
            success = 200 <= resp.status_code < 300
            return success, resp.status_code, None if success else f"HTTP {resp.status_code}"
        except Exception as exc:
            logger.warning("Webhook dispatch error url=%s: %s", target_url, exc)
            return False, None, str(exc)
