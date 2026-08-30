"""
F008 — Permission Audit Metrics
================================

Prometheus counters and histogram for the permission-audit endpoints.

Usage (from endpoint layer):
    from app.services.permission_audit import metrics as pa_metrics

    # on successful list request:
    pa_metrics.list_requests_total.labels(
        workspace_id=str(workspace_id), result="ok"
    ).inc()

    # on successful export request:
    pa_metrics.export_requests_total.labels(
        workspace_id=str(workspace_id), result="ok", truncated="false"
    ).inc()

    # record query duration for either endpoint:
    pa_metrics.query_duration_ms.labels(endpoint="list").observe(duration_ms)
"""

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

list_requests_total = Counter(
    "permission_audit_list_requests_total",
    "Total number of permission audit list endpoint requests",
    ["workspace_id", "result"],
)

export_requests_total = Counter(
    "permission_audit_export_requests_total",
    "Total number of permission audit export endpoint requests",
    ["workspace_id", "result", "truncated"],
)

# ---------------------------------------------------------------------------
# Histograms
# ---------------------------------------------------------------------------

query_duration_ms = Histogram(
    "permission_audit_query_duration_ms",
    "Permission audit query duration in milliseconds",
    ["endpoint"],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000],
)
