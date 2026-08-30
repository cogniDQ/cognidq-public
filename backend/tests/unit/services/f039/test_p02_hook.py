"""
F039 P02 — IssueCreationService Hook Tests
=============================================

Verifies that step 13b in IssueCreationService.create_from_node_result
calls AutoIncidentService.evaluate_and_create after a successful issue
persist, with the correct arguments, and that failures are non-blocking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from app.services.issues.issue_creation_service import IssueCreationService
from app.services.issues.issue_models import IssueDomain
from app.services.workspaces.settings_models import SLAPolicy, WorkspaceSettings

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.uuid4()
_WORKSPACE_ID = uuid.uuid4()
_EXEC_ID = uuid.uuid4()
_FLOW_ID = uuid.uuid4()
_NR_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()
_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

_DEFAULT_SLA = SLAPolicy(
    critical_hours=4,
    major_hours=24,
    minor_hours=72,
    informational_hours=None,
)


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------


def _make_node_result(
    id_=_NR_ID,
    status="failed",
    node_id="node_check_001",
    completed_at=None,
    result_data=None,
):
    nr = MagicMock()
    nr.id = id_
    nr.status = status
    nr.node_id = node_id
    nr.completed_at = completed_at or _NOW
    nr.result_data = result_data or {
        "rows_scanned": 1000,
        "rows_failed": 150,
        "pass_rate": 85.0,
    }
    return nr


def _make_execution():
    exc = MagicMock()
    exc.id = _EXEC_ID
    exc.flow_id = _FLOW_ID
    exc.status = "completed"
    return exc


def _make_flow():
    flow = MagicMock()
    flow.id = _FLOW_ID
    flow.workspace_id = _WORKSPACE_ID
    flow.flow_definition = {
        "nodes": [
            {
                "id": "node_check_001",
                "type": "check",
                "config": {"rule_id": str(_RULE_ID)},
            }
        ],
        "connections": [],
    }
    return flow


def _make_rule(severity="critical"):
    rule = MagicMock()
    rule.id = _RULE_ID
    rule.severity = severity
    rule.canonical_rule = {"severity": severity, "dimension": "completeness"}
    return rule


def _make_workspace():
    ws = MagicMock()
    ws.tenant_id = _TENANT_ID
    ws.workspace_id = _WORKSPACE_ID
    return ws


def _make_ws_settings():
    settings = MagicMock(spec=WorkspaceSettings)
    settings.sla_policy = _DEFAULT_SLA
    settings.with_defaults.return_value = settings
    return settings


def _make_persisted_domain(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        workspace_id=_WORKSPACE_ID,
        flow_execution_id=_EXEC_ID,
        flow_node_result_id=_NR_ID,
        rule_id=_RULE_ID,
        issue_type="threshold_breach",
        severity="critical",
        status="open",
        title="[CRITICAL] Check failed: node node_check_001",
        failure_count=150,
        rows_scanned=1000,
        pass_rate=85.0,
        opened_at=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )
    defaults.update(overrides)
    return IssueDomain(**defaults)


def _make_db(node_result, execution, flow, rule=None):
    """Return a Session mock whose .query() chain returns supplied objects."""
    from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
    from app.models.rule import DQRule

    def _query_side_effect(model):
        chain = MagicMock()
        chain.filter.return_value = chain
        if model is FlowNodeResult:
            chain.first.return_value = node_result
        elif model is FlowExecution:
            chain.first.return_value = execution
        elif model is DQFlow:
            chain.first.return_value = flow
        elif model is DQRule:
            chain.first.return_value = rule
        else:
            chain.first.return_value = None
        return chain

    db = MagicMock()
    db.query.side_effect = _query_side_effect
    return db


def _build_service(persisted=None, auto_inc_svc=None):
    mock_repo = MagicMock()
    mock_repo.insert.return_value = persisted or _make_persisted_domain()
    mock_sample = MagicMock()
    mock_grouping = MagicMock()
    mock_grouping.find_and_update_candidate.return_value = None
    mock_auto = auto_inc_svc or MagicMock()

    svc = IssueCreationService(
        repository=mock_repo,
        grouping_service=mock_grouping,
        sample_service=mock_sample,
        auto_incident_service=mock_auto,
    )
    return svc, mock_repo, mock_auto


# ---------------------------------------------------------------------------
# Patch context manager
# ---------------------------------------------------------------------------


def _ws_patches(ws=None, settings=None):
    """Return stacked patches for workspace and settings repos."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=settings or _make_ws_settings(),
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws or _make_workspace(),
            ),
        ):
            yield

    return _ctx()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoIncidentHookCalled:
    """Step 13b invokes AutoIncidentService with correct args."""

    def test_evaluate_and_create_called_on_success(self):
        persisted = _make_persisted_domain()
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        mock_auto.evaluate_and_create.assert_called_once()

    def test_passes_correct_workspace_id(self):
        persisted = _make_persisted_domain()
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        kwargs = mock_auto.evaluate_and_create.call_args
        assert kwargs.kwargs["workspace_id"] == _WORKSPACE_ID

    def test_passes_correct_tenant_id(self):
        persisted = _make_persisted_domain()
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        kwargs = mock_auto.evaluate_and_create.call_args
        assert kwargs.kwargs["tenant_id"] == _TENANT_ID

    def test_passes_correct_issue_id(self):
        persisted = _make_persisted_domain()
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        kwargs = mock_auto.evaluate_and_create.call_args
        assert kwargs.kwargs["issue_id"] == persisted.id

    def test_passes_correct_severity(self):
        persisted = _make_persisted_domain(severity="major")
        svc, _, mock_auto = _build_service(persisted=persisted)
        rule = _make_rule("major")
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), rule)

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        kwargs = mock_auto.evaluate_and_create.call_args
        assert kwargs.kwargs["issue_severity"] == "major"

    def test_passes_failure_count(self):
        persisted = _make_persisted_domain(failure_count=42)
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        kwargs = mock_auto.evaluate_and_create.call_args
        assert kwargs.kwargs["issue_failure_count"] == 42

    def test_passes_issue_title(self):
        persisted = _make_persisted_domain(title="Test title")
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        kwargs = mock_auto.evaluate_and_create.call_args
        assert kwargs.kwargs["issue_title"] == "Test title"


class TestAutoIncidentHookNonBlocking:
    """Step 13b failures must not prevent issue return."""

    def test_exception_does_not_prevent_return(self):
        persisted = _make_persisted_domain()
        mock_auto = MagicMock()
        mock_auto.evaluate_and_create.side_effect = RuntimeError("boom")
        svc, _, _ = _build_service(persisted=persisted, auto_inc_svc=mock_auto)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is not None
        assert result.id == persisted.id

    def test_exception_is_logged(self, caplog):
        persisted = _make_persisted_domain()
        mock_auto = MagicMock()
        mock_auto.evaluate_and_create.side_effect = RuntimeError("boom")
        svc, _, _ = _build_service(persisted=persisted, auto_inc_svc=mock_auto)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches(), caplog.at_level("WARNING"):
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert any("F039 auto-incident creation failed" in rec.message for rec in caplog.records)


class TestAutoIncidentNotCalledOnFailure:
    """Step 13b should NOT be called when issue creation fails."""

    def test_not_called_when_node_result_passes(self):
        svc, _, mock_auto = _build_service()
        nr = _make_node_result(status="completed")
        db = _make_db(nr, _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is None
        mock_auto.evaluate_and_create.assert_not_called()

    def test_not_called_when_db_insert_raises(self):
        svc, mock_repo, mock_auto = _build_service()
        mock_repo.insert.side_effect = RuntimeError("db error")
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        with _ws_patches():
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is None
        mock_auto.evaluate_and_create.assert_not_called()

    def test_not_called_when_execution_missing(self):
        svc, _, mock_auto = _build_service()
        db = MagicMock()

        def _q(model):
            chain = MagicMock()
            chain.filter.return_value = chain
            from app.models.flow import FlowNodeResult

            if model is FlowNodeResult:
                chain.first.return_value = _make_node_result()
            else:
                chain.first.return_value = None
            return chain

        db.query.side_effect = _q

        with _ws_patches():
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is None
        mock_auto.evaluate_and_create.assert_not_called()
