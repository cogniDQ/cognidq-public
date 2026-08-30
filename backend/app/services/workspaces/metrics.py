"""
F002 — Workspace Metrics (TDD §8.1, §12.1)
==========================================

Fire-and-forget metric counters for workspace operations.
A metric failure MUST NEVER propagate to the caller.

In production, these stubs are replaced with real Prometheus/StatsD implementations.
The fire-and-forget contract remains identical.

Metrics defined per TDD §8.1, §12.1:
| Metric name                                    | Labels |
|------------------------------------------------|--------|
| workspace_create_success_count                 | tenant_id |
| workspace_create_failure_count                 | failure_reason (duplicate_name, duplicate_slug, invalid_input, tenant_not_active, unauthorized, internal_error) |
| workspace_metadata_update_count                | updated_fields (comma-separated, sorted) |
| workspace_status_change_count                  | from_status, to_status |
| workspace_status_change_failure_count          | failure_reason |
| workspace_list_request_count                   | None   |
| workspace_detail_request_count                 | None   |
| workspace_detail_count_query_failure_count     | count_type (dataset_count, member_count) |
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def emit_workspace_create_success(tenant_id: str) -> None:
    """
    Increment workspace_create_success_count (fire-and-forget).

    Args:
        tenant_id: The tenant that owns the created workspace (per TDD §12.1 label).

    Emitted after successful workspace creation (3-write transaction committed).
    """
    try:
        logger.info(
            "metric: workspace_create_success_count tenant_id=%s",
            tenant_id,
        )
    except Exception:  # pragma: no cover
        pass


def emit_workspace_create_failure(failure_reason: str) -> None:
    """
    Increment workspace_create_failure_count (fire-and-forget).

    Args:
        failure_reason: One of: duplicate_name, duplicate_slug, invalid_input,
                        tenant_not_active, unauthorized, internal_error (TDD §12.1).

    Emitted on any workspace creation failure (validation, business rule, or internal error).
    """
    try:
        logger.info(
            "metric: workspace_create_failure_count failure_reason=%s",
            failure_reason,
        )
    except Exception:  # pragma: no cover
        pass


def emit_workspace_update_success(updated_fields: str) -> None:
    """
    Increment workspace_metadata_update_count (fire-and-forget).

    Args:
        updated_fields: Comma-separated field names, alphabetically sorted
                       (e.g., "description,workspace_name")

    Per TDD §12.1: Label format is alphabetically sorted field list.
    Emitted after successful workspace metadata update (transaction committed).
    """
    try:
        logger.info("metric: workspace_metadata_update_count updated_fields=%s", updated_fields)
    except Exception:  # pragma: no cover
        pass


def emit_workspace_update_failure(error_code: str) -> None:
    """
    Increment workspace_update_failure_count (fire-and-forget).

    Args:
        error_code: Error code from WorkspaceAPIError

    Emitted on any workspace update failure (validation, business rule, or internal error).
    """
    try:
        logger.info("metric: workspace_update_failure_count error_code=%s", error_code)
    except Exception:  # pragma: no cover
        pass


def emit_workspace_status_change_success(from_status: str, to_status: str) -> None:
    """
    Increment workspace_status_change_count (fire-and-forget).

    Args:
        from_status: Previous workspace status (e.g., "active")
        to_status:   New workspace status (e.g., "archived")

    Per TDD §12.1: Emitted after a successful archive or restore transaction commit.
    """
    try:
        logger.info(
            "metric: workspace_status_change_count from_status=%s to_status=%s",
            from_status,
            to_status,
        )
    except Exception:  # pragma: no cover
        pass


def emit_workspace_status_change_failure(failure_reason: str) -> None:
    """
    Increment workspace_status_change_failure_count (fire-and-forget).

    Args:
        failure_reason: One of: forbidden_transition, missing_reason,
                        tenant_not_active, unauthorized, no_op,
                        last_active_workspace, internal_error
                        (per TDD §12.1)

    Emitted on any archive/restore rejection or failure.
    """
    try:
        logger.info(
            "metric: workspace_status_change_failure_count failure_reason=%s",
            failure_reason,
        )
    except Exception:  # pragma: no cover
        pass


def emit_workspace_list_request_count() -> None:
    """
    Increment workspace_list_request_count (fire-and-forget).

    Emitted unconditionally at the start of every GET /api/v1/workspaces
    request, including ones that ultimately return 4xx (TDD §12.1 task 9).
    """
    try:
        logger.info("metric: workspace_list_request_count +1")
    except Exception:  # pragma: no cover
        pass


def emit_workspace_detail_request_count() -> None:
    """
    Increment workspace_detail_request_count (fire-and-forget).

    Emitted unconditionally at the start of every
    GET /api/v1/workspaces/{workspace_id} request (TDD §12.1 task 9).
    """
    try:
        logger.info("metric: workspace_detail_request_count +1")
    except Exception:  # pragma: no cover
        pass


def emit_workspace_detail_count_query_failure(count_type: str) -> None:
    """
    Increment workspace_detail_count_query_failure_count (fire-and-forget).

    Args:
        count_type: Either ``"dataset_count"`` or ``"member_count"``
                    (per TDD §12.1 label values).

    Emitted when a secondary count query (dataset or member registry)
    fails or times out during a workspace detail request.
    """
    try:
        logger.info(
            "metric: workspace_detail_count_query_failure_count count_type=%s",
            count_type,
        )
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# F003 — Workspace Settings Metrics (TDD §12.1)
# ---------------------------------------------------------------------------


def emit_workspace_settings_read_success() -> None:
    """Increment workspace_settings_read_count (fire-and-forget).

    Emitted after a successful GET /workspaces/{id}/settings response.
    No labels per TDD §12.1.
    """
    try:
        logger.info("metric: workspace_settings_read_count +1")
    except Exception:  # pragma: no cover
        pass


def emit_workspace_settings_update_success(changed_fields: str) -> None:
    """Increment workspace_settings_update_count (fire-and-forget).

    Args:
        changed_fields: Sorted comma-separated list of changed policy domains
                        (e.g., ``"default_timezone,sla_policy"``).

    Emitted after a successful PATCH /workspaces/{id}/settings that caused
    at least one field change (i.e., not a no-op).  Emitted post-commit.
    """
    try:
        logger.info(
            "metric: workspace_settings_update_count changed_fields=%s",
            changed_fields,
        )
    except Exception:  # pragma: no cover
        pass


def emit_workspace_settings_noop() -> None:
    """Increment workspace_settings_noop_count (fire-and-forget).

    Emitted after a PATCH /workspaces/{id}/settings where no values
    actually changed (no-op detected by the service layer).
    """
    try:
        logger.info("metric: workspace_settings_noop_count +1")
    except Exception:  # pragma: no cover
        pass


def emit_workspace_settings_update_failure(failure_reason: str) -> None:
    """Increment workspace_settings_update_failure_count (fire-and-forget).

    Args:
        failure_reason: One of: ``validation_error``, ``workspace_not_found``,
                        ``workspace_not_active``, ``forbidden``,
                        ``missing_required_field``, ``internal_error``
                        (per TDD §12.1 label values).

    Emitted on any failed PATCH /workspaces/{id}/settings attempt.
    """
    try:
        logger.info(
            "metric: workspace_settings_update_failure_count failure_reason=%s",
            failure_reason,
        )
    except Exception:  # pragma: no cover
        pass
