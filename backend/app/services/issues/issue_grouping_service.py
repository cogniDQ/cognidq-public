"""
IssueGroupingService — F032 Issue Grouping and Deduplication

Determines whether an incoming failure should be folded into an existing open
Issue (instead of creating a new one) based on the workspace's
``issue_grouping_policy`` setting.

Transaction ownership
---------------------
The service receives a caller-provided SQLAlchemy Session.  It does NOT commit.
On DB exception it logs ERROR and returns None (FR-018 lossless fallback).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.services.issues.issue_models import IssueDomain
from app.services.issues.issue_repository import IssueRepository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_GROUPABLE_STATUSES = frozenset({"open", "in_progress", "reopened"})
_POLICY_ONE_PER_EXECUTION = "one_per_execution"
_POLICY_ONE_PER_RULE = "one_per_rule"
_POLICY_ONE_PER_DAY = "one_per_day"


# ---------------------------------------------------------------------------
# Public service class
# ---------------------------------------------------------------------------


class IssueGroupingService:
    """Encapsulates the grouping policy decision and update orchestration."""

    def __init__(self, repository: IssueRepository | None = None) -> None:
        self._repo = repository or IssueRepository()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def find_and_update_candidate(
        self,
        db: Session,
        workspace_id: UUID,
        rule_id: UUID | None,
        dataset_id: UUID | None,
        policy: str,
        workspace_timezone: str,
        new_rows_failed: int,
        new_completed_at: datetime,
    ) -> IssueDomain | None:
        """
        Return the updated IssueDomain of a grouped issue, or None.

        Steps
        -----
        1. policy == one_per_execution → None immediately (no DB call).
        2. rule_id or dataset_id is None → None immediately (FR-015/FR-016).
        3. Compute day window if policy == one_per_day.
        4. Call find_open_for_grouping().
        5. No candidate → None.
        6. Build new impact_summary; call update_for_grouping().
        7. Return updated IssueDomain.
        8. Any DB exception → log ERROR, return None (FR-018).
        """
        # Step 1
        if policy == _POLICY_ONE_PER_EXECUTION:
            logger.debug(
                "F032 grouping skipped: policy=one_per_execution workspace=%s",
                workspace_id,
            )
            return None

        # Step 2
        if rule_id is None or dataset_id is None:
            logger.debug(
                "F032 grouping skipped: null rule_id or dataset_id workspace=%s "
                "rule_id=%s dataset_id=%s",
                workspace_id,
                rule_id,
                dataset_id,
            )
            return None

        try:
            # Step 3
            day_start_utc: datetime | None = None
            day_end_utc: datetime | None = None
            if policy == _POLICY_ONE_PER_DAY:
                day_start_utc, day_end_utc = _compute_day_window(
                    new_completed_at, workspace_timezone
                )

            # Step 4
            candidate = self._repo.find_open_for_grouping(
                db,
                workspace_id=workspace_id,
                rule_id=rule_id,
                dataset_id=dataset_id,
                policy=policy,
                day_start_utc=day_start_utc,
                day_end_utc=day_end_utc,
            )

            # Step 5
            if candidate is None:
                return None

            # Step 6 — compute new cumulative failure_count for summary
            current_failure_count = (candidate.failure_count or 0) + new_rows_failed
            new_impact_summary = _build_grouped_impact_summary(
                current_failure_count, new_completed_at
            )

            # Step 7 — persist update
            updated = self._repo.update_for_grouping(
                db,
                issue_id=candidate.id,
                delta_rows_failed=new_rows_failed,
                new_impact_summary=new_impact_summary,
                new_last_seen_at=new_completed_at,
            )
            return updated

        except Exception as exc:
            # Step 8 — FR-018 lossless fallback
            logger.error(
                "F032 grouping check failed, falling back: "
                "workspace=%s rule=%s dataset=%s policy=%s "
                "exc_type=%s exc=%s",
                workspace_id,
                rule_id,
                dataset_id,
                policy,
                type(exc).__name__,
                exc,
            )
            return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_day_window(
    completed_at: datetime,
    tz_name: str,
) -> tuple[datetime, datetime]:
    """
    Return (day_start_utc, day_end_utc) for the calendar day containing
    ``completed_at`` in workspace timezone ``tz_name``.

    >>> _compute_day_window(datetime(2026,4,1,22,30, tzinfo=timezone.utc), "Europe/Paris")
    (datetime(2026, 3, 31, 22, 0, tzinfo=...), datetime(2026, 4, 1, 22, 0, tzinfo=...))
    """
    tz = ZoneInfo(tz_name)
    local_dt = completed_at.astimezone(tz)
    day_start_local = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_local = day_start_local + timedelta(days=1)
    return (
        day_start_local.astimezone(UTC),
        day_end_local.astimezone(UTC),
    )


def _build_grouped_impact_summary(
    cumulative_failure_count: int,
    last_seen_at: datetime,
) -> str:
    """Build the grouped issue impact summary string.

    >>> _build_grouped_impact_summary(42, datetime(2026, 4, 1, 9, 0, 0))
    '42 failures recorded (last seen: 2026-04-01T09:00:00)'
    """
    return f"{cumulative_failure_count} failures recorded (last seen: {last_seen_at.isoformat()})"
