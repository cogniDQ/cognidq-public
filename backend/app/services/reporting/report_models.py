"""
F050 — Issue and Incident Report Pydantic Models
==================================================

Response schemas for aggregated issue/incident reporting.
"""

from __future__ import annotations

from pydantic import BaseModel

# ── Issue Report Models ──────────────────────────────────────────────────────


class IssueStatusCounts(BaseModel):
    open: int = 0
    resolved: int = 0
    closed: int = 0


class IssueSeverityCounts(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0
    info: int = 0


class ResolutionTimeStats(BaseModel):
    avg_hours: float = 0.0
    median_hours: float = 0.0
    p95_hours: float = 0.0
    total_resolved: int = 0


class IssueDashboardSummary(BaseModel):
    status_counts: IssueStatusCounts
    severity_counts: IssueSeverityCounts
    overdue_count: int = 0
    resolution_stats: ResolutionTimeStats


# ── Incident Report Models ───────────────────────────────────────────────────


class IncidentStatusCounts(BaseModel):
    open: int = 0
    acknowledged: int = 0
    resolved: int = 0
    closed: int = 0


class IncidentSeverityCounts(BaseModel):
    critical: int = 0
    major: int = 0
    minor: int = 0
    info: int = 0


class IncidentPriorityCounts(BaseModel):
    p1: int = 0
    p2: int = 0
    p3: int = 0
    p4: int = 0


class IncidentDashboardSummary(BaseModel):
    status_counts: IncidentStatusCounts
    severity_counts: IncidentSeverityCounts
    priority_counts: IncidentPriorityCounts
    sla_breach_count: int = 0
    resolution_stats: ResolutionTimeStats
