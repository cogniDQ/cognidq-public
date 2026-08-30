"""
F050 — Incident Report Service
================================

Aggregation queries over the incidents table for workspace-scoped reporting.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.incident import Incident, IncidentIssue
from app.models.issue import Issue
from app.services.reporting.report_models import (
    IncidentDashboardSummary,
    IncidentPriorityCounts,
    IncidentSeverityCounts,
    IncidentStatusCounts,
    ResolutionTimeStats,
)


class IncidentReportService:
    """Read-only aggregation service for incident reporting."""

    def count_by_status(self, db: Session, workspace_id: UUID) -> IncidentStatusCounts:
        rows: list[tuple[str, int]] = (
            db.query(Incident.status, sa_func.count(Incident.id))
            .filter(Incident.workspace_id == workspace_id)
            .group_by(Incident.status)
            .all()
        )
        counts = {status: count for status, count in rows}
        return IncidentStatusCounts(
            open=counts.get("open", 0),
            acknowledged=counts.get("acknowledged", 0),
            resolved=counts.get("resolved", 0),
            closed=counts.get("closed", 0),
        )

    def count_by_severity(self, db: Session, workspace_id: UUID) -> IncidentSeverityCounts:
        rows: list[tuple[str, int]] = (
            db.query(Incident.severity, sa_func.count(Incident.id))
            .filter(Incident.workspace_id == workspace_id)
            .group_by(Incident.severity)
            .all()
        )
        counts = {sev: count for sev, count in rows}
        return IncidentSeverityCounts(
            critical=counts.get("critical", 0),
            major=counts.get("major", 0),
            minor=counts.get("minor", 0),
            info=counts.get("info", 0),
        )

    def count_by_priority(self, db: Session, workspace_id: UUID) -> IncidentPriorityCounts:
        rows: list[tuple[str, int]] = (
            db.query(Incident.priority, sa_func.count(Incident.id))
            .filter(Incident.workspace_id == workspace_id)
            .group_by(Incident.priority)
            .all()
        )
        counts = {p: count for p, count in rows}
        return IncidentPriorityCounts(
            p1=counts.get("P1", 0),
            p2=counts.get("P2", 0),
            p3=counts.get("P3", 0),
            p4=counts.get("P4", 0),
        )

    def sla_breach_count(self, db: Session, workspace_id: UUID) -> int:
        """Count incidents that have at least one linked overdue open issue."""
        now = datetime.now(UTC)
        result = (
            db.query(sa_func.count(sa_func.distinct(Incident.id)))
            .join(IncidentIssue, IncidentIssue.incident_id == Incident.id)
            .join(Issue, Issue.id == IncidentIssue.issue_id)
            .filter(
                Incident.workspace_id == workspace_id,
                Issue.status == "open",
                Issue.due_at.isnot(None),
                Issue.due_at < now,
            )
            .scalar()
        )
        return result or 0

    def resolution_time_stats(self, db: Session, workspace_id: UUID) -> ResolutionTimeStats:
        """Compute avg/median/p95 resolution times in hours for resolved/closed incidents."""
        rows = (
            db.query(
                sa_func.extract(
                    "epoch",
                    Incident.resolved_at - Incident.opened_at,
                )
                / 3600.0
            )
            .filter(
                Incident.workspace_id == workspace_id,
                Incident.resolved_at.isnot(None),
                Incident.opened_at.isnot(None),
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

    def dashboard_summary(self, db: Session, workspace_id: UUID) -> IncidentDashboardSummary:
        return IncidentDashboardSummary(
            status_counts=self.count_by_status(db, workspace_id),
            severity_counts=self.count_by_severity(db, workspace_id),
            priority_counts=self.count_by_priority(db, workspace_id),
            sla_breach_count=self.sla_breach_count(db, workspace_id),
            resolution_stats=self.resolution_time_stats(db, workspace_id),
        )
