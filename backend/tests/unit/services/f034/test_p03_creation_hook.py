"""
F034 P03 — Unit tests: IssueCreationService sample capture hook

AC-P03-01: capture_for_issue called after issue creation
AC-P03-02: sample_service raises → issue still returned (non-blocking)
AC-P03-03: capture called with correct issue_id, workspace_id, dataset_id
AC-P03-04: grouping early-return (F032) does not trigger sample capture
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.services.issues.issue_creation_service import IssueCreationService
from app.services.issues.issue_models import IssueDomain

_WS = uuid.uuid4()
_TENANT = uuid.uuid4()
_EXEC = uuid.uuid4()
_NR_ID = uuid.uuid4()
_FLOW_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()
_DS_ID = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_NOW = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)


def _make_domain(**kwargs) -> IssueDomain:
    base = dict(
        id=_ISSUE_ID,
        tenant_id=_TENANT,
        workspace_id=_WS,
        flow_execution_id=_EXEC,
        issue_type="threshold_breach",
        severity="major",
        status="open",
        title="[MAJOR] Check failed",
        failure_count=5,
    )
    base.update(kwargs)
    return IssueDomain(**base)


def _patch_settings(settings_row):
    return patch(
        "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
        return_value=settings_row,
    )


def _patch_workspace_repo(workspace):
    return patch(
        "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
        return_value=workspace,
    )


def _build_query_chain(
    db,
    *,
    rule_id=_RULE_ID,
    dataset_id=_DS_ID,
    policy="one_per_execution",
):
    """Set up mock db.query chain for all steps of create_from_node_result."""
    node_result = MagicMock()
    node_result.status = "failed"
    node_result.node_id = "node_1"
    node_result.completed_at = _NOW
    node_result.result_data = {
        "rows_scanned": 100,
        "rows_failed": 5,
        "pass_rate": 95.0,
        "violations": [{"customer_id": 1, "email": "a@b.com"}],
    }

    execution = MagicMock()
    execution.flow_id = _FLOW_ID

    flow = MagicMock()
    flow.workspace_id = _WS
    flow.flow_definition = {
        "nodes": [
            {
                "id": "node_1",
                "config": {
                    "rule_id": str(rule_id),
                    "dataset_id": str(dataset_id),
                },
            }
        ]
    }

    workspace = MagicMock()
    workspace.tenant_id = _TENANT

    settings = MagicMock()
    settings.issue_grouping_policy = policy
    settings.default_timezone = "UTC"
    settings.sla_policy = None
    settings_row = MagicMock()
    settings_row.with_defaults.return_value = settings

    call_n = [0]

    def q(model):
        m = MagicMock()
        n = call_n[0]
        call_n[0] += 1
        if n == 0:
            m.filter.return_value.first.return_value = node_result
        elif n == 1:
            m.filter.return_value.first.return_value = execution
        elif n == 2:
            m.filter.return_value.first.return_value = flow
        else:
            m.filter.return_value.first.return_value = MagicMock(severity="major")
        return m

    db.query.side_effect = q
    # Prevent UUID validation errors from db.execute().fetchone() returning MagicMock
    db.execute.return_value.fetchone.return_value = None
    return settings_row, workspace, node_result


# ---------------------------------------------------------------------------
# AC-P03-01: capture_for_issue called after issue creation
# ---------------------------------------------------------------------------
class TestSampleCaptureCalledAfterInsert:
    def test_capture_called(self):
        mock_repo = MagicMock()
        created = _make_domain()
        mock_repo.insert.return_value = created

        mock_sample_svc = MagicMock()
        mock_grouping_svc = MagicMock()

        svc = IssueCreationService(
            repository=mock_repo,
            grouping_service=mock_grouping_svc,
            sample_service=mock_sample_svc,
        )

        db = MagicMock()
        settings_row, workspace, _ = _build_query_chain(db)

        with _patch_settings(settings_row), _patch_workspace_repo(workspace):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC)

        mock_sample_svc.capture_for_issue.assert_called_once()
        assert result is created


# ---------------------------------------------------------------------------
# AC-P03-02: sample_service raises → issue still returned
# ---------------------------------------------------------------------------
class TestSampleExceptionNonBlocking:
    def test_issue_returned_despite_exception(self):
        mock_repo = MagicMock()
        created = _make_domain()
        mock_repo.insert.return_value = created

        mock_sample_svc = MagicMock()
        mock_sample_svc.capture_for_issue.side_effect = RuntimeError("disk full")
        mock_grouping_svc = MagicMock()

        svc = IssueCreationService(
            repository=mock_repo,
            grouping_service=mock_grouping_svc,
            sample_service=mock_sample_svc,
        )

        db = MagicMock()
        settings_row, workspace, _ = _build_query_chain(db)

        with _patch_settings(settings_row), _patch_workspace_repo(workspace):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC)

        assert result is created


# ---------------------------------------------------------------------------
# AC-P03-03: correct args passed to capture_for_issue
# ---------------------------------------------------------------------------
class TestCaptureArgs:
    def test_args_correct(self):
        mock_repo = MagicMock()
        created = _make_domain()
        mock_repo.insert.return_value = created

        mock_sample_svc = MagicMock()
        mock_grouping_svc = MagicMock()

        svc = IssueCreationService(
            repository=mock_repo,
            grouping_service=mock_grouping_svc,
            sample_service=mock_sample_svc,
        )

        db = MagicMock()
        settings_row, workspace, _ = _build_query_chain(db)

        with _patch_settings(settings_row), _patch_workspace_repo(workspace):
            svc.create_from_node_result(db, _NR_ID, _EXEC)

        call_kwargs = mock_sample_svc.capture_for_issue.call_args.kwargs
        assert call_kwargs["issue_id"] == created.id
        assert call_kwargs["workspace_id"] == _WS
        assert call_kwargs["dataset_id"] == _DS_ID


# ---------------------------------------------------------------------------
# AC-P03-04: grouping early-return does not trigger sample capture
# ---------------------------------------------------------------------------
class TestGroupingSkipsSampleCapture:
    def test_sample_not_called_on_grouping_path(self):
        mock_repo = MagicMock()
        mock_grouping_svc = MagicMock()
        grouped = _make_domain(failure_count=10)
        mock_grouping_svc.find_and_update_candidate.return_value = grouped

        mock_sample_svc = MagicMock()

        svc = IssueCreationService(
            repository=mock_repo,
            grouping_service=mock_grouping_svc,
            sample_service=mock_sample_svc,
        )

        db = MagicMock()
        settings_row, workspace, _ = _build_query_chain(db, policy="one_per_rule")

        with _patch_settings(settings_row):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC)

        assert result is grouped
        mock_sample_svc.capture_for_issue.assert_not_called()
