"""
F004 — Data Source Metrics
===========================

Prometheus counters for all data source lifecycle operations.
Counters are registered in the default prometheus_client registry.

Usage (from service layer):
    from app.services.data_sources import metrics as ds_metrics
    ds_metrics.data_source_create_count.labels(
        workspace_id=str(workspace_id),
        source_type=source_type,
        result="success",
    ).inc()
"""

from prometheus_client import Counter

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

data_source_create_count = Counter(
    "data_source_create_count",
    "Number of data source creation attempts",
    ["workspace_id", "source_type", "result"],
)

data_source_update_count = Counter(
    "data_source_update_count",
    "Number of data source update attempts",
    ["workspace_id", "result"],
)

data_source_archive_count = Counter(
    "data_source_archive_count",
    "Number of data source archive attempts",
    ["workspace_id", "result"],
)

data_source_restore_count = Counter(
    "data_source_restore_count",
    "Number of data source restore attempts",
    ["workspace_id", "result"],
)

data_source_test_connection_count = Counter(
    "data_source_test_connection_count",
    "Number of connection test attempts",
    ["workspace_id", "source_type", "result"],
)
