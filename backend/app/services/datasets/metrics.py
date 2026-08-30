"""
F005 — Dataset Prometheus Metrics
===================================

Counters for dataset operations. Labelled by workspace_id and result.
"""

from prometheus_client import Counter

dataset_create_count = Counter(
    "dataset_create_count",
    "Dataset creation attempts",
    ["workspace_id", "dataset_type", "result"],
)

dataset_update_count = Counter(
    "dataset_update_count",
    "Dataset update attempts",
    ["workspace_id", "result"],
)

dataset_activate_count = Counter(
    "dataset_activate_count",
    "Dataset activation attempts",
    ["workspace_id", "result"],
)

dataset_deactivate_count = Counter(
    "dataset_deactivate_count",
    "Dataset deactivation attempts",
    ["workspace_id", "result"],
)

dataset_reactivate_count = Counter(
    "dataset_reactivate_count",
    "Dataset reactivation attempts",
    ["workspace_id", "result"],
)

dataset_archive_count = Counter(
    "dataset_archive_count",
    "Dataset archive attempts",
    ["workspace_id", "result"],
)

dataset_field_add_count = Counter(
    "dataset_field_add_count",
    "Dataset field addition attempts",
    ["workspace_id", "result"],
)

dataset_field_bulk_import_count = Counter(
    "dataset_field_bulk_import_count",
    "Dataset field bulk import attempts",
    ["workspace_id", "mode", "result"],
)
