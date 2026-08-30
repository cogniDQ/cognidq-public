"""
F001 — Outbox event poller (Packet 7)
======================================

Implements the background outbox poller described in TDD §4.4 / §9.

Responsibilities
----------------
* Poll ``control.outbox_events`` for undelivered events
  (``delivered = FALSE AND retry_count < MAX_RETRIES``).
* Deliver each event to the Session Management System (stubbed for MVP).
* On success:  ``UPDATE outbox_events SET delivered = TRUE, delivered_at = NOW()``.
* On failure:  ``UPDATE outbox_events SET retry_count = retry_count + 1, last_error = …``.
* SLA breach:  If an event was created more than 30 seconds ago and is still
  undelivered, emit the ``session_invalidation_sla_breach_count`` alert metric.
* Max retries: When ``retry_count >= MAX_RETRIES``, log a critical alert and
  stop retrying — NEVER silently drop the event.

Usage
-----
Start the poller as a daemon thread from the application startup hook::

    from app.services.tenants.outbox import OutboxPoller
    poller = OutboxPoller()
    poller.start()  # starts a daemon thread

The poller stops when the process exits (daemon thread).  Call
``poller.stop()`` for a clean shutdown before the process exits.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.database import SessionLocal
from app.services.tenants.metrics import emit_session_invalidation_sla_breach

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants (suitable for extraction to settings in production)
# ---------------------------------------------------------------------------

#: Seconds between poll cycles.
POLL_INTERVAL_SECONDS: int = 5

#: Maximum number of events processed per poll cycle.
BATCH_SIZE: int = 50

#: Total attempts before permanent failure escalation (initial + this many retries).
MAX_RETRIES: int = 5

#: Events undelivered past this age (seconds) trigger an SLA breach alert.
SLA_BREACH_SECONDS: int = 30

# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_POLL_SQL = text("""
    SELECT
        event_id::text,
        event_type,
        tenant_id::text,
        payload,
        occurred_at,
        retry_count
    FROM control.outbox_events
    WHERE delivered = FALSE
      AND retry_count < :max_retries
    ORDER BY occurred_at ASC
    LIMIT :batch_size
    FOR UPDATE SKIP LOCKED
""")

_MARK_DELIVERED_SQL = text("""
    UPDATE control.outbox_events
    SET delivered = TRUE, delivered_at = NOW()
    WHERE event_id = CAST(:event_id AS UUID)
""")

_INCREMENT_RETRY_SQL = text("""
    UPDATE control.outbox_events
    SET retry_count = retry_count + 1, last_error = :last_error
    WHERE event_id = CAST(:event_id AS UUID)
""")


# ---------------------------------------------------------------------------
# Session Management System stub (replaced by real client in production)
# ---------------------------------------------------------------------------


class _SessionManagementStub:
    """No-op stub for the Session Management System delivery interface."""

    def deliver_tenant_suspended_event(self, tenant_id: str, payload: dict[str, Any]) -> None:
        """Stub delivery — logs the event.  Replace with real HTTP/gRPC call."""
        logger.info(
            "outbox_poller: stub delivery tenant_suspended tenant_id=%s payload=%s",
            tenant_id,
            payload,
        )


_sms_client = _SessionManagementStub()


# ---------------------------------------------------------------------------
# Metric stubs (fire-and-forget — never raise)
# ---------------------------------------------------------------------------


def _emit_sla_breach(tenant_id: str) -> None:
    """Emit ``session_invalidation_sla_breach_count {tenant_id}`` alert metric.

    Delegates to the canonical metric stub in ``metrics.py`` so all metric
    definitions are consolidated in one module (fire-and-forget).
    """
    emit_session_invalidation_sla_breach(tenant_id)


# ---------------------------------------------------------------------------
# Poller implementation
# ---------------------------------------------------------------------------


class OutboxPoller:
    """Background daemon that polls and delivers outbox events (TDD §4.4, §9).

    Thread safety
    -------------
    Each poll cycle creates its own ``Session`` instance.  The poller shares
    no state with the FastAPI request-handling threads.

    Lifecycle
    ---------
    ``start()``     — creates and starts the daemon thread.
    ``stop()``      — signals the polling loop to exit cleanly.
    ``is_running()`` — returns True while the loop is active.
    """

    def __init__(
        self,
        poll_interval: int = POLL_INTERVAL_SECONDS,
        batch_size: int = BATCH_SIZE,
        max_retries: int = MAX_RETRIES,
        sla_breach_seconds: int = SLA_BREACH_SECONDS,
    ) -> None:
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._sla_breach_delta = timedelta(seconds=sla_breach_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("OutboxPoller.start() called but thread is already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="outbox-poller",
            daemon=True,
        )
        self._thread.start()
        logger.info("OutboxPoller started (poll_interval=%ds)", self._poll_interval)

    def stop(self) -> None:
        """Signal the polling loop to stop and wait for the thread to join."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._poll_interval + 5)
            logger.info("OutboxPoller stopped")

    def is_running(self) -> bool:
        """Return True if the polling thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main loop — polls until ``stop()`` is called."""
        while not self._stop_event.is_set():
            try:
                self._poll_cycle()
            except Exception:
                logger.exception("OutboxPoller: unhandled exception in poll cycle")
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_cycle(self) -> None:
        """One poll iteration: fetch a batch and process each event."""
        db: Session = SessionLocal()
        try:
            rows: list[Any] = list(
                db.execute(
                    _POLL_SQL,
                    {"max_retries": self._max_retries, "batch_size": self._batch_size},
                )
                .mappings()
                .all()
            )

            if not rows:
                db.rollback()
                return

            now = datetime.now(UTC)

            for row in rows:
                event_id: str = str(row["event_id"])
                tenant_id: str = str(row["tenant_id"])
                occurred_at: datetime = row["occurred_at"]
                retry_count: int = int(row["retry_count"])

                # Ensure occurred_at is timezone-aware for comparison
                if occurred_at.tzinfo is None:
                    occurred_at = occurred_at.replace(tzinfo=UTC)

                # ----------------------------------------------------------
                # SLA breach check (TDD §9)
                # ----------------------------------------------------------
                if now - occurred_at > self._sla_breach_delta:
                    _emit_sla_breach(tenant_id)

                # ----------------------------------------------------------
                # Max retries reached — escalate, do NOT mark delivered
                # ----------------------------------------------------------
                if retry_count >= self._max_retries:
                    logger.critical(
                        "outbox_poller: event %s for tenant %s has exhausted "
                        "%d retries — manual operator intervention required",
                        event_id,
                        tenant_id,
                        self._max_retries,
                    )
                    db.rollback()
                    continue

                # ----------------------------------------------------------
                # Attempt delivery
                # ----------------------------------------------------------
                payload_raw = row["payload"]
                if isinstance(payload_raw, str):
                    payload = json.loads(payload_raw)
                else:
                    payload = payload_raw or {}

                try:
                    _sms_client.deliver_tenant_suspended_event(tenant_id, payload)
                    # Success: mark delivered
                    db.execute(_MARK_DELIVERED_SQL, {"event_id": event_id})
                    db.commit()
                    logger.info(
                        "outbox_poller: delivered event %s for tenant %s", event_id, tenant_id
                    )

                except Exception as delivery_exc:
                    db.rollback()
                    error_str = str(delivery_exc)[:1000]
                    try:
                        db.execute(
                            _INCREMENT_RETRY_SQL,
                            {"event_id": event_id, "last_error": error_str},
                        )
                        db.commit()
                    except Exception:
                        db.rollback()
                        logger.exception(
                            "outbox_poller: failed to increment retry_count for event %s",
                            event_id,
                        )
                    logger.warning(
                        "outbox_poller: delivery failed for event %s tenant %s "
                        "(retry_count now %d): %s",
                        event_id,
                        tenant_id,
                        retry_count + 1,
                        error_str,
                    )

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
