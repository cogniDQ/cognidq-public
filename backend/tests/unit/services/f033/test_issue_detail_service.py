"""
F033 P01 — Unit tests for IssueDetailService

Tests all enrichment paths: full context, missing entities, null FK fields.
Uses MagicMock for DB session and repository — no live database needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from app.services.issues.issue_detail_service import IssueDetailService
from app.services.issues.issue_models import IssueDetail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT = uuid.uuid4()
_WORKSPACE = uuid.uuid4()
_ISSUE_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()
_DATASET_ID = uuid.uuid4()
_ASSIGNEE_ID = uuid.uuid4()
_EXECUTION_ID = uuid.uuid4()
_NODE_RESULT_ID = uuid.uuid4()
_FLOW_ID = uuid.uuid4()
_NOW = datetime(2026, 3, 30, 12, 0, 0, tzinfo=UTC)


def _make_detail(**overrides) -> IssueDetail:
    """Build an IssueDetail with sensible defaults; override any field."""
    defaults = dict(
        id=_ISSUE_ID,
        tenant_id=_TENANT,
        workspace_id=_WORKSPACE,
        flow_execution_id=_EXECUTION_ID,
        flow_node_result_id=_NODE_RESULT_ID,
        rule_id=_RULE_ID,
        dataset_id=_DATASET_ID,
        assignee_id=_ASSIGNEE_ID,
        issue_type="dq_check_failure",
        severity="major",
        status="open",
        title="Test issue",
        impact_summary="50 rows failed",
        failure_count=50,
        rows_scanned=100,
        pass_rate=Decimal("50.00"),
        due_at=_NOW,
        opened_at=_NOW,
        resolved_at=None,
        closed_at=None,
        updated_at=_NOW,
        created_at=_NOW,
    )
    defaults.update(overrides)
    return IssueDetail(**defaults)


def _make_rule_orm():
    rule = MagicMock()
    rule.id = _RULE_ID
    rule.name = "Completeness check"
    rule.category = "completeness"
    rule.severity = "major"
    rule.status = "active"
    rule.target_table = "orders"
    rule.target_columns = ["email", "phone"]
    return rule


def _make_user_orm():
    user = MagicMock()
    user.id = _ASSIGNEE_ID
    user.full_name = "Jane Doe"
    user.email = "jane@example.com"
    return user


def _make_execution_orm():
    ex = MagicMock()
    ex.id = _EXECUTION_ID
    ex.flow_id = _FLOW_ID
    ex.status = "completed"
    ex.started_at = _NOW
    ex.completed_at = _NOW
    ex.nodes_executed = 5
    ex.nodes_passed = 4
    ex.nodes_failed = 1
    return ex


def _make_flow_orm():
    flow = MagicMock()
    flow.id = _FLOW_ID
    flow.name = "Daily DQ Flow"
    return flow


def _make_node_result_orm():
    nr = MagicMock()
    nr.id = _NODE_RESULT_ID
    nr.node_id = "check_email"
    nr.node_type = "check"
    nr.status = "failed"
    nr.result_data = {
        "rows_scanned": 100,
        "rows_passed": 50,
        "rows_failed": 50,
        "pass_rate": 50.0,
    }
    return nr


def _dataset_row():
    """Simulate a raw SQL row tuple from control.datasets."""
    return (_DATASET_ID, "orders_dataset", "finance", "high", "active")


def _setup_db_query(
    db: MagicMock,
    *,
    rule=None,
    user=None,
    execution=None,
    flow=None,
    node_result=None,
):
    """
    Configure db.query(...).filter(...).first() to return the right ORM
    object based on which model class is queried.
    """
    from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
    from app.models.rule import DQRule
    from app.models.user import User

    lookup = {
        DQRule: rule,
        User: user,
        FlowExecution: execution,
        DQFlow: flow,
        FlowNodeResult: node_result,
    }

    def query_side_effect(model_cls):
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.first.return_value = lookup.get(model_cls)
        return chain

    db.query.side_effect = query_side_effect


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnrichedDetailAllEntities:
    """When all FK entities exist, all 5 context objects should be populated."""

    def test_enriched_detail_all_entities(self):
        repo = MagicMock()
        detail = _make_detail()
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        _setup_db_query(
            db,
            rule=_make_rule_orm(),
            user=_make_user_orm(),
            execution=_make_execution_orm(),
            flow=_make_flow_orm(),
            node_result=_make_node_result_orm(),
        )
        # Dataset raw SQL
        ds_result = MagicMock()
        ds_result.fetchone.return_value = _dataset_row()
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        assert enriched.id == _ISSUE_ID
        assert enriched.rule is not None
        assert enriched.rule.name == "Completeness check"
        assert enriched.dataset is not None
        assert enriched.dataset.dataset_name == "orders_dataset"
        assert enriched.assignee is not None
        assert enriched.assignee.display_name == "Jane Doe"
        assert enriched.flow_execution is not None
        assert enriched.flow_execution.flow_name == "Daily DQ Flow"
        assert enriched.node_result is not None
        assert enriched.node_result.node_id == "check_email"


class TestEnrichedDetailRuleDeleted:
    """When rule_id references a deleted rule, rule context should be None."""

    def test_enriched_detail_rule_deleted(self):
        repo = MagicMock()
        detail = _make_detail()
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        _setup_db_query(
            db,
            rule=None,  # rule deleted
            user=_make_user_orm(),
            execution=_make_execution_orm(),
            flow=_make_flow_orm(),
            node_result=_make_node_result_orm(),
        )
        ds_result = MagicMock()
        ds_result.fetchone.return_value = _dataset_row()
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        assert enriched.rule is None
        assert enriched.rule_id == _RULE_ID  # flat ID preserved


class TestEnrichedDetailDatasetDeleted:
    """When dataset row is missing from control.datasets, dataset context is None."""

    def test_enriched_detail_dataset_deleted(self):
        repo = MagicMock()
        detail = _make_detail()
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        _setup_db_query(
            db,
            rule=_make_rule_orm(),
            user=_make_user_orm(),
            execution=_make_execution_orm(),
            flow=_make_flow_orm(),
            node_result=_make_node_result_orm(),
        )
        ds_result = MagicMock()
        ds_result.fetchone.return_value = None  # dataset deleted
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        assert enriched.dataset is None
        assert enriched.dataset_id == _DATASET_ID  # flat ID preserved


class TestEnrichedDetailNoAssignee:
    """When assignee_id is NULL, assignee context should be None."""

    def test_enriched_detail_no_assignee(self):
        repo = MagicMock()
        detail = _make_detail(assignee_id=None)
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        _setup_db_query(
            db,
            rule=_make_rule_orm(),
            execution=_make_execution_orm(),
            flow=_make_flow_orm(),
            node_result=_make_node_result_orm(),
        )
        ds_result = MagicMock()
        ds_result.fetchone.return_value = _dataset_row()
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        assert enriched.assignee is None
        assert enriched.assignee_id is None


class TestEnrichedDetailNoNodeResult:
    """When flow_node_result_id is NULL, node_result context should be None."""

    def test_enriched_detail_no_node_result(self):
        repo = MagicMock()
        detail = _make_detail(flow_node_result_id=None)
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        _setup_db_query(
            db,
            rule=_make_rule_orm(),
            user=_make_user_orm(),
            execution=_make_execution_orm(),
            flow=_make_flow_orm(),
        )
        ds_result = MagicMock()
        ds_result.fetchone.return_value = _dataset_row()
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        assert enriched.node_result is None
        assert enriched.flow_node_result_id is None


class TestEnrichedDetailIssueNotFound:
    """When issue doesn't exist, service should return None."""

    def test_enriched_detail_issue_not_found(self):
        repo = MagicMock()
        repo.get_by_id_and_workspace.return_value = None

        db = MagicMock()
        svc = IssueDetailService(repository=repo)
        result = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert result is None


class TestEnrichedDetailFlatIdsPreserved:
    """All flat FK fields from IssueDetail must be present in EnrichedIssueDetail."""

    def test_enriched_detail_flat_ids_preserved(self):
        repo = MagicMock()
        detail = _make_detail()
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        _setup_db_query(
            db,
            rule=_make_rule_orm(),
            user=_make_user_orm(),
            execution=_make_execution_orm(),
            flow=_make_flow_orm(),
            node_result=_make_node_result_orm(),
        )
        ds_result = MagicMock()
        ds_result.fetchone.return_value = _dataset_row()
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        # All flat FK IDs are preserved
        assert enriched.flow_execution_id == _EXECUTION_ID
        assert enriched.flow_node_result_id == _NODE_RESULT_ID
        assert enriched.rule_id == _RULE_ID
        assert enriched.dataset_id == _DATASET_ID
        assert enriched.assignee_id == _ASSIGNEE_ID
        # All scalar fields preserved
        assert enriched.title == "Test issue"
        assert enriched.severity == "major"
        assert enriched.status == "open"
        assert enriched.failure_count == 50
        assert enriched.rows_scanned == 100
        assert enriched.pass_rate == Decimal("50.00")


class TestEnrichedDetailExecutionNodes:
    """Verify nodes_total maps from FlowExecution.nodes_executed."""

    def test_enriched_detail_execution_nodes(self):
        repo = MagicMock()
        detail = _make_detail()
        repo.get_by_id_and_workspace.return_value = detail

        db = MagicMock()
        execution = _make_execution_orm()
        execution.nodes_executed = 10
        execution.nodes_passed = 8
        execution.nodes_failed = 2
        _setup_db_query(
            db,
            rule=_make_rule_orm(),
            user=_make_user_orm(),
            execution=execution,
            flow=_make_flow_orm(),
            node_result=_make_node_result_orm(),
        )
        ds_result = MagicMock()
        ds_result.fetchone.return_value = _dataset_row()
        db.execute.return_value = ds_result

        svc = IssueDetailService(repository=repo)
        enriched = svc.get_enriched_detail(db, _ISSUE_ID, _WORKSPACE)

        assert enriched is not None
        assert enriched.flow_execution is not None
        assert enriched.flow_execution.nodes_total == 10
        assert enriched.flow_execution.nodes_passed == 8
        assert enriched.flow_execution.nodes_failed == 2
