"""
F134 — Demo Sandbox Provisioning
SandboxUsageEventRepository: bulk insert + aggregation for control.sandbox_usage_events.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_BULK_INSERT_SQL = text("""
    INSERT INTO control.sandbox_usage_events
        (sandbox_id, user_id, event_type, event_payload, request_id, source_ip, occurred_at)
    VALUES
        (CAST(:sandbox_id AS UUID), CAST(:user_id AS UUID), :event_type,
         CAST(:event_payload AS JSONB), CAST(:request_id AS UUID), CAST(:source_ip AS INET),
         :occurred_at)
""")

_SUMMARISE_SQL = text("""
    SELECT
        event_type,
        COUNT(*) AS total_count,
        MAX(occurred_at) AS last_seen_at
    FROM control.sandbox_usage_events
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
      AND occurred_at >= :since
    GROUP BY event_type
    ORDER BY total_count DESC
""")

_TOTAL_EVENTS_SQL = text("""
    SELECT COUNT(*) AS total
    FROM control.sandbox_usage_events
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
""")


class SandboxUsageEventRepository:
    """Data access for control.sandbox_usage_events (append-only)."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def insert(
        self,
        *,
        sandbox_id: UUID,
        user_id: UUID | None,
        event_type: str,
        event_payload: dict[str, Any] | None = None,
        request_id: UUID | None = None,
        source_ip: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        import json as _json

        self._db.execute(
            _BULK_INSERT_SQL,
            {
                "sandbox_id": str(sandbox_id),
                "user_id": str(user_id) if user_id else None,
                "event_type": event_type,
                "event_payload": _json.dumps(event_payload or {}),
                "request_id": str(request_id) if request_id else None,
                "source_ip": source_ip,
                "occurred_at": occurred_at,
            },
        )

    def bulk_insert(self, events: list[dict[str, Any]]) -> None:
        """Insert multiple events in a single statement batch."""
        import json as _json

        for evt in events:
            self._db.execute(
                _BULK_INSERT_SQL,
                {
                    "sandbox_id": str(evt["sandbox_id"]),
                    "user_id": str(evt["user_id"]) if evt.get("user_id") else None,
                    "event_type": evt["event_type"],
                    "event_payload": _json.dumps(evt.get("event_payload") or {}),
                    "request_id": str(evt["request_id"]) if evt.get("request_id") else None,
                    "source_ip": evt.get("source_ip"),
                    "occurred_at": evt.get("occurred_at"),
                },
            )

    def summarise_by_sandbox(self, *, sandbox_id: UUID, since: datetime) -> list[dict[str, Any]]:
        rows = self._db.execute(
            _SUMMARISE_SQL, {"sandbox_id": str(sandbox_id), "since": since}
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def total_events(self, *, sandbox_id: UUID) -> int:
        row = self._db.execute(_TOTAL_EVENTS_SQL, {"sandbox_id": str(sandbox_id)}).fetchone()
        return int(row._mapping["total"]) if row else 0
