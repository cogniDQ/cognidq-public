"""
F051 — Report CSV Service
===========================

Generates CSV bytes from report summary models (issue/incident dashboards).
"""

from __future__ import annotations

import csv
import io

from app.services.reporting.report_models import (
    IncidentDashboardSummary,
    IssueDashboardSummary,
)


class ReportCsvService:
    """Formats report summary data as CSV bytes."""

    def issue_summary_csv(self, summary: IssueDashboardSummary) -> bytes:
        """Return UTF-8-BOM-prefixed CSV for issue dashboard summary."""
        buf = io.StringIO()
        writer = csv.writer(buf)

        writer.writerow(["Issue Dashboard Summary"])
        writer.writerow([])

        writer.writerow(["Status Counts"])
        writer.writerow(["status", "count"])
        sc = summary.status_counts
        writer.writerow(["open", sc.open])
        writer.writerow(["resolved", sc.resolved])
        writer.writerow(["closed", sc.closed])
        writer.writerow([])

        writer.writerow(["Severity Counts"])
        writer.writerow(["severity", "count"])
        sv = summary.severity_counts
        writer.writerow(["critical", sv.critical])
        writer.writerow(["major", sv.major])
        writer.writerow(["minor", sv.minor])
        writer.writerow(["info", sv.info])
        writer.writerow([])

        writer.writerow(["Overdue Count", summary.overdue_count])
        writer.writerow([])

        writer.writerow(["Resolution Time Stats"])
        writer.writerow(["metric", "value"])
        rs = summary.resolution_stats
        writer.writerow(["avg_hours", rs.avg_hours])
        writer.writerow(["median_hours", rs.median_hours])
        writer.writerow(["p95_hours", rs.p95_hours])
        writer.writerow(["total_resolved", rs.total_resolved])

        return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")

    def incident_summary_csv(self, summary: IncidentDashboardSummary) -> bytes:
        """Return UTF-8-BOM-prefixed CSV for incident dashboard summary."""
        buf = io.StringIO()
        writer = csv.writer(buf)

        writer.writerow(["Incident Dashboard Summary"])
        writer.writerow([])

        writer.writerow(["Status Counts"])
        writer.writerow(["status", "count"])
        sc = summary.status_counts
        writer.writerow(["open", sc.open])
        writer.writerow(["acknowledged", sc.acknowledged])
        writer.writerow(["resolved", sc.resolved])
        writer.writerow(["closed", sc.closed])
        writer.writerow([])

        writer.writerow(["Severity Counts"])
        writer.writerow(["severity", "count"])
        sv = summary.severity_counts
        writer.writerow(["critical", sv.critical])
        writer.writerow(["major", sv.major])
        writer.writerow(["minor", sv.minor])
        writer.writerow(["info", sv.info])
        writer.writerow([])

        writer.writerow(["Priority Counts"])
        writer.writerow(["priority", "count"])
        pc = summary.priority_counts
        writer.writerow(["p1", pc.p1])
        writer.writerow(["p2", pc.p2])
        writer.writerow(["p3", pc.p3])
        writer.writerow(["p4", pc.p4])
        writer.writerow([])

        writer.writerow(["SLA Breach Count", summary.sla_breach_count])
        writer.writerow([])

        writer.writerow(["Resolution Time Stats"])
        writer.writerow(["metric", "value"])
        rs = summary.resolution_stats
        writer.writerow(["avg_hours", rs.avg_hours])
        writer.writerow(["median_hours", rs.median_hours])
        writer.writerow(["p95_hours", rs.p95_hours])
        writer.writerow(["total_resolved", rs.total_resolved])

        return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
