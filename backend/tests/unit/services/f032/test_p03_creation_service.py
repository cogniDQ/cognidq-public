"""
F032 P03 — Unit tests for IssueCreationService grouping integration
====================================================================

Covers the 5 unit-level acceptance criteria:

AC-P03-01  one_per_rule + existing issue → returns updated domain, no new insert
AC-P03-02  one_per_execution → always creates new issue
AC-P03-03  one_per_rule + no candidate → creates new issue as F031
AC-P03-04  grouping_service raises → falls back to insert, no re-raise
AC-P03-05  three consecutive failures one_per_rule → one issue, accumulated count
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest
from app.services.issues.issue_creation_service import IssueCreationService
from app.services.issues.issue_models import IssueDomain

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_WS = uuid.uuid4()
_TENANT = uuid.uuid4()
_EXEC = uuid.uuid4()
_NODE_RESULT_ID = uuid.uuid4()
_FLOW_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()
_DS_ID = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_NOW = datetime(2026, 4, 1, 9, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_domain(failure_count: int = 5) -> IssueDomain:
    return IssueDomain(
        id=_ISSUE_ID,
        tenant_id=_TENANT,
        workspace_id=_WS,
        flow_execution_id=_EXEC,
        issue_type="threshold_breach",
        severity="major",
        status="open",
        title="[MAJOR] Check failed",
        failure_count=failure_count,
    )


def _build_db_mocks(
    *,
    policy: str = "one_per_execution",
    timezone_: str = "UTC",
    rows_failed: int = 5,
    rule_id: uuid.UUID | None = _RULE_ID,
    dataset_id: uuid.UUID | None = _DS_ID,
) -> MagicMock:
    """
    Build a fully mocked db session that satisfies all steps of
    IssueCreationService.create_from_node_result().
    """
    db = MagicMock()

    # node_result
    node_result = MagicMock()
    node_result.id = _NODE_RESULT_ID
    node_result.status = "failed"
    node_result.node_id = "node_1"
    node_result.completed_at = _NOW
    node_result.result_data = {
        "rows_scanned": 100,
        "rows_failed": rows_failed,
        "pass_rate": 90.0,
    }

    # flow_execution
    execution = MagicMock()
    execution.id = _EXEC
    execution.flow_id = _FLOW_ID

    # flow
    flow = MagicMock()
    flow.id = _FLOW_ID
    flow.workspace_id = _WS
    flow.flow_definition = {
        "nodes": [
            {
                "id": "node_1",
                "config": {
                    "rule_id": str(rule_id) if rule_id else None,
                    "dataset_id": str(dataset_id) if dataset_id else None,
                },
            }
        ]
    }

    # workspace
    workspace = MagicMock()
    workspace.tenant_id = _TENANT

    # settings
    settings = MagicMock()
    settings.issue_grouping_policy = policy
    settings.default_timezone = timezone_
    settings.sla_policy = None

    settings_row = MagicMock()
    settings_row.with_defaults.return_value = settings

    # Sequence db.query().filter().first() calls
    call_count = [0]

    def query_side_effect(model):
        mock_q = MagicMock()
        n = call_count[0]

        if n == 0:
            # Step 1: query(FlowNodeResult)
            mock_q.filter.return_value.first.return_value = node_result
        elif n == 1:
            # Step 2: query(FlowExecution)
            mock_q.filter.return_value.first.return_value = execution
        elif n == 2:
            # Step 3: query(DQFlow)
            mock_q.filter.return_value.first.return_value = flow
        elif n == 3:
            # Step 5: query(DQRule)
            rule = MagicMock()
            rule.severity = "major"
            mock_q.filter.return_value.first.return_value = rule
        elif n == 4:
            # Step 10: workspace lookup via WorkspaceRepository
            mock_q.filter.return_value.first.return_value = workspace
        else:
            mock_q.filter.return_value.first.return_value = None

        call_count[0] += 1
        return mock_q

    db.query.side_effect = query_side_effect

    # Prevent UUID validation errors from db.execute().fetchone() returning MagicMock
    db.execute.return_value.fetchone.return_value = None

    # settings repository
    db._settings_row = settings_row  # stored for patching

    return db, settings_row, workspace


# ---------------------------------------------------------------------------
# Patch helpers
# ---------------------------------------------------------------------------


def _patch_settings(settings_row):
    """Return patch context for settings_repository.find_by_workspace_id."""
    return patch(
        "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
        return_value=settings_row,
    )


def _patch_workspace_repo(workspace):
    """Return patch context for WorkspaceRepository.find_by_id_any_tenant."""
    return patch(
        "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
        return_value=workspace,
    )


# ===========================================================================
# AC-P03-01: one_per_rule + existing issue → grouped domain returned, no insert
# ===========================================================================
class TestGroupingReturnsExistingIssue:
    def test_grouped_result_returned_instead_of_insert(self):
        mock_repo = MagicMock()
        mock_grouping_svc = MagicMock()
        grouped_domain = _make_domain(failure_count=10)
        mock_grouping_svc.find_and_update_candidate.return_value = grouped_domain

        svc = IssueCreationService(
            repository=mock_repo,
            grouping_service=mock_grouping_svc,
        )

        db = MagicMock()
        # Build minimal mocks for the db query chain
        node_result = MagicMock()
        node_result.status = "failed"
        node_result.node_id = "node_1"
        node_result.completed_at = _NOW
        node_result.result_data = {"rows_scanned": 100, "rows_failed": 5, "pass_rate": 90.0}

        execution = MagicMock()
        execution.flow_id = _FLOW_ID

        flow = MagicMock()
        flow.workspace_id = _WS
        flow.flow_definition = {
            "nodes": [
                {"id": "node_1", "config": {"rule_id": str(_RULE_ID), "dataset_id": str(_DS_ID)}}
            ]
        }

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

        settings = MagicMock()
        settings.issue_grouping_policy = "one_per_rule"
        settings.default_timezone = "UTC"
        settings.sla_policy = None
        settings_row = MagicMock()
        settings_row.with_defaults.return_value = settings

        with _patch_settings(settings_row):
            result = svc.create_from_node_result(db, _NODE_RESULT_ID, _EXEC)

        assert result is grouped_domain
        mock_repo.insert.assert_not_called()
        mock_grouping_svc.find_and_update_candidate.assert_called_once()
