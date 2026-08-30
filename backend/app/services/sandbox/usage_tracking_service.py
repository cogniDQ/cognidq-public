"""
F134 P10 — UsageTrackingService

Per-request sandbox usage event recording (fire-and-forget — never raises).
Aggregation logic for engagement scoring.

Engagement score rule (per TDD §7):
  high    → ≥5 sessions in last 48h AND ≥10 unique event types
  medium  → ≥2 sessions in last 48h
  low     → default
  unknown → no events recorded yet
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.sandbox.sandbox_environment_repository import (
    SandboxEnvironmentRepository,
)
from app.services.sandbox.sandbox_usage_event_repository import (
    SandboxUsageEventRepository,
)

logger = logging.getLogger(__name__)

# Usage event dropped metric counter (stub — real counter wired in P12)
_usage_event_dropped_total = 0


def _increment_dropped() -> None:
    global _usage_event_dropped_total
    _usage_event_dropped_total += 1


# ── Engagement score computation (pure function) ──────────────────────────────

_SESSIONS_IN_48H_SQL = text("""
    SELECT COUNT(*) AS n
    FROM control.sandbox_usage_events
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
      AND event_type = 'login'
      AND occurred_at >= :since
""")

_UNIQUE_EVENT_TYPES_SQL = text("""
    SELECT COUNT(DISTINCT event_type) AS n
    FROM control.sandbox_usage_events
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
      AND occurred_at >= :since
""")

_TOTAL_EVENTS_SQL = text("""
    SELECT COUNT(*) AS n
    FROM control.sandbox_usage_events
    WHERE sandbox_id = CAST(:sandbox_id AS UUID)
""")


def compute_engagement_score(
    *,
    sessions_in_48h: int,
    unique_event_types_in_48h: int,
    total_events: int,
) -> str:
    """
    Pure function implementing the engagement score rule from TDD §7.

    Returns one of: 'high', 'medium', 'low', 'unknown'.
    """
    if total_events == 0:
        return "unknown"
    if sessions_in_48h >= 5 and unique_event_types_in_48h >= 10:
        return "high"
    if sessions_in_48h >= 2:
        return "medium"
    return "low"


# ── UsageTrackingService ──────────────────────────────────────────────────────


class UsageTrackingService:
    """
    Records sandbox usage events and computes engagement scores.

    ``record_event`` is fire-and-forget — it NEVER propagates exceptions
    to the caller. Errors are logged and the metric counter is incremented.
    """

    def __init__(
        self,
        db: Session,
        *,
        event_repo: SandboxUsageEventRepository | None = None,
        env_repo: SandboxEnvironmentRepository | None = None,
    ) -> None:
        self._db = db
        self._event_repo = event_repo or SandboxUsageEventRepository(db)
        self._env_repo = env_repo or SandboxEnvironmentRepository(db)

    def record_event(
        self,
        *,
        sandbox_id: UUID,
        user_id: UUID | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
        request_id: UUID | None = None,
        source_ip: str | None = None,
    ) -> None:
        """
        Record a single usage event.

        This method NEVER raises — all exceptions are caught, logged, and
        counted via ``usage_event_dropped_total``.
        """
        try:
            self._event_repo.insert(
                sandbox_id=sandbox_id,
                user_id=user_id,
                event_type=event_type,
                event_payload=payload or {},
                request_id=request_id,
                source_ip=source_ip,
                occurred_at=datetime.now(UTC),
            )
        except Exception as exc:
            _increment_dropped()
            logger.warning(
                "UsageTrackingService.record_event failed for sandbox %s event_type=%s: %s",
                sandbox_id,
                event_type,
                exc,
            )

    def aggregate(self, *, sandbox_id: UUID) -> str:
        """
        Compute the engagement score for a sandbox and update the DB.

        Returns the computed score string.
        """
        now = datetime.now(UTC)
        since_48h = now - timedelta(hours=48)

        row_sessions = self._db.execute(
            _SESSIONS_IN_48H_SQL, {"sandbox_id": str(sandbox_id), "since": since_48h}
        ).fetchone()
        sessions = int(row_sessions._mapping["n"]) if row_sessions else 0

        row_types = self._db.execute(
            _UNIQUE_EVENT_TYPES_SQL, {"sandbox_id": str(sandbox_id), "since": since_48h}
        ).fetchone()
        unique_types = int(row_types._mapping["n"]) if row_types else 0

        row_total = self._db.execute(_TOTAL_EVENTS_SQL, {"sandbox_id": str(sandbox_id)}).fetchone()
        total = int(row_total._mapping["n"]) if row_total else 0

        score = compute_engagement_score(
            sessions_in_48h=sessions,
            unique_event_types_in_48h=unique_types,
            total_events=total,
        )

        # Update sandbox engagement score
        self._db.execute(
            text("""
                UPDATE control.sandbox_environments
                SET engagement_score = :score, updated_at = NOW()
                WHERE id = CAST(:id AS UUID)
            """),
            {"id": str(sandbox_id), "score": score},
        )

        return score

    def get_usage_summary(self, *, sandbox_id: UUID) -> dict[str, Any]:
        """
        Return a usage summary for the admin usage endpoint.

        Shape:
          { summary: {...}, events_by_type: [...], timeline: [...] }
        """
        # Total events
        row_total = self._db.execute(_TOTAL_EVENTS_SQL, {"sandbox_id": str(sandbox_id)}).fetchone()
        total = int(row_total._mapping["n"]) if row_total else 0

        # Events by type
        events_by_type_rows = self._db.execute(
            text("""
                SELECT event_type, COUNT(*) AS count, MAX(occurred_at) AS last_seen_at
                FROM control.sandbox_usage_events
                WHERE sandbox_id = CAST(:sandbox_id AS UUID)
                GROUP BY event_type
                ORDER BY count DESC
            """),
            {"sandbox_id": str(sandbox_id)},
        ).fetchall()

        events_by_type = [
            {
                "event_type": r._mapping["event_type"],
                "count": int(r._mapping["count"]),
                "last_seen_at": r._mapping["last_seen_at"].isoformat()
                if r._mapping["last_seen_at"]
                else None,
            }
            for r in events_by_type_rows
        ]

        # Daily timeline (last 14 days)
        since_14d = datetime.now(UTC) - timedelta(days=14)
        timeline_rows = self._db.execute(
            text("""
                SELECT
                    DATE(occurred_at AT TIME ZONE 'UTC') AS day,
                    COUNT(*) AS count
                FROM control.sandbox_usage_events
                WHERE sandbox_id = CAST(:sandbox_id AS UUID)
                  AND occurred_at >= :since
                GROUP BY day
                ORDER BY day
            """),
            {"sandbox_id": str(sandbox_id), "since": since_14d},
        ).fetchall()

        timeline = [
            {"day": str(r._mapping["day"]), "count": int(r._mapping["count"])}
            for r in timeline_rows
        ]

        # Load sandbox for engagement score
        env = self._env_repo.find_by_id(sandbox_id)
        engagement_score = (env or {}).get("engagement_score", "unknown")

        return {
            "summary": {
                "total_events": total,
                "engagement_score": engagement_score,
            },
            "events_by_type": events_by_type,
            "timeline": timeline,
        }
