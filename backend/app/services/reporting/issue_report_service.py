"""
F050 — Issue Report Service
=============================

Aggregation queries over the issues table for workspace-scoped reporting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.services.reporting.report_models import (
    IssueDashboardSummary,
    IssueSeverityCounts,
    IssueStatusCounts,
    ResolutionTimeStats,
)


class IssueReportService:
    """Read-only aggregation service for issue reporting."""

    def count_by_status(self, db: Session, workspace_id: UUID) -> IssueStatusCounts:
        rows: list[tuple[str, int]] = (
            db.query(Issue.status, sa_func.count(Issue.id))
            .filter(Issue.workspace_id == workspace_id)
            .group_by(Issue.status)
            .all()
        )
        counts = {status: count for status, count in rows}
        return IssueStatusCounts(
            open=counts.get("open", 0),
            resolved=counts.get("resolved", 0),
            closed=counts.get("closed", 0),
        )

    def count_by_severity(self, db: Session, workspace_id: UUID) -> IssueSeverityCounts:
        rows: list[tuple[str, int]] = (
            db.query(Issue.severity, sa_func.count(Issue.id))
            .filter(
                Issue.workspace_id == workspace_id,
                Issue.status.in_(["open", "resolved", "closed"]),
            )
            .group_by(Issue.severity)
            .all()
        )
        counts = {sev: count for sev, count in rows}
        return IssueSeverityCounts(
            critical=counts.get("critical", 0),
            major=counts.get("major", 0),
            minor=counts.get("minor", 0),
            info=counts.get("info", 0),
        )

    def count_overdue(self, db: Session, workspace_id: UUID) -> int:
        now = datetime.now(UTC)
        return (
            db.query(sa_func.count(Issue.id))
            .filter(
                Issue.workspace_id == workspace_id,
                Issue.status == "open",
                Issue.due_at.isnot(None),
                Issue.due_at < now,
            )
            .scalar()
        ) or 0

    def resolution_time_stats(self, db: Session, workspace_id: UUID) -> ResolutionTimeStats:
        """Compute avg/median/p95 resolution times in hours for resolved/closed issues."""
        rows = (
            db.query(
                sa_func.extract(
                    "epoch",
                    Issue.resolved_at - Issue.opened_at,
                )
                / 3600.0
            )
            .filter(
                Issue.workspace_id == workspace_id,
                Issue.resolved_at.isnot(None),
                Issue.opened_at.isnot(None),
            )
            .all()
        )
        hours_list = sorted([r[0] for r in rows if r[0] is not None and r[0] >= 0])
        if not hours_list:
            return ResolutionTimeStats()

        total = len(hours_list)
        avg_h = sum(hours_list) / total
        median_h = (
            hours_list[total // 2]
            if total % 2 == 1
            else (hours_list[total // 2 - 1] + hours_list[total // 2]) / 2.0
        )
        p95_idx = min(int(total * 0.95), total - 1)
        p95_h = hours_list[p95_idx]

        return ResolutionTimeStats(
            avg_hours=round(avg_h, 2),
            median_hours=round(median_h, 2),
            p95_hours=round(p95_h, 2),
            total_resolved=total,
        )

    def dashboard_summary(self, db: Session, workspace_id: UUID) -> IssueDashboardSummary:
        return IssueDashboardSummary(
            status_counts=self.count_by_status(db, workspace_id),
            severity_counts=self.count_by_severity(db, workspace_id),
            overdue_count=self.count_overdue(db, workspace_id),
            resolution_stats=self.resolution_time_stats(db, workspace_id),
        )
