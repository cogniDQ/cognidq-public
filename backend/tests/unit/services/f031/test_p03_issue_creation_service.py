"""
F031 P03 — Unit tests for IssueCreationService
===============================================

All SQLAlchemy Sessions and collaborator objects are replaced by ``MagicMock``
instances.  No running database is required.

ACs covered
-----------
P03-AC-001  rows_failed=150, rows_scanned=1000, pass_rate=85.0 →
            failure_count=150, impact_summary="150 of 1000 rows failed (85.0% pass rate)"
P03-AC-002  severity='critical', sla_policy.critical_hours=4 →
            due_at = opened_at + 4 hours
P03-AC-003  workspace has no sla_policy (None) → due_at=None
P03-AC-004  severity='informational', informational_hours=None → due_at=None
P03-AC-005  passing check node (status='completed') → returns None, no insert
P03-AC-006  skipped node (status='skipped') → returns None, no insert
P03-AC-007  DB INSERT exception → catches, logs ERROR, returns None
P03-AC-008  two failing nodes → IssueCreationService produces two distinct instances
P03-AC-009  opened_at on created Issue equals node_result.completed_at
P03-AC-010  workspace_id resolved from DQFlow.workspace_id
P03-AC-011  DB failure during issue creation does NOT change FlowExecution.status
P03-AC-012  successful creation produces structured INFO log entry
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest
from app.services.issues.issue_creation_service import (
    IssueCreationService,
    _build_impact_summary,
    _compute_due_at,
    _normalise_severity,
)
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
_NOW = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)

_DEFAULT_SLA = SLAPolicy(
    critical_hours=4,
    major_hours=24,
    minor_hours=72,
    informational_hours=None,
)


def _make_node_result(
    id_: uuid.UUID = _NR_ID,
    status: str = "failed",
    node_id: str = "node_check_001",
    completed_at: datetime | None = None,
    result_data: dict | None = None,
) -> MagicMock:
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


def _make_execution(flow_id: uuid.UUID = _FLOW_ID) -> MagicMock:
    exc = MagicMock()
    exc.id = _EXEC_ID
    exc.flow_id = flow_id
    exc.status = "completed"
    return exc


def _make_flow(
    workspace_id: uuid.UUID = _WORKSPACE_ID,
    node_rule_id: str | None = None,
) -> MagicMock:
    flow = MagicMock()
    flow.id = _FLOW_ID
    flow.workspace_id = workspace_id
    flow.flow_definition = {
        "nodes": [
            {
                "id": "node_check_001",
                "type": "check",
                "config": {
                    "rule_id": str(node_rule_id or _RULE_ID),
                },
            }
        ],
        "connections": [],
    }
    return flow


def _make_rule(severity: str = "critical") -> MagicMock:
    rule = MagicMock()
    rule.id = _RULE_ID
    rule.severity = severity
    rule.canonical_rule = {"severity": severity, "dimension": "completeness"}
    return rule


def _make_workspace(tenant_id: uuid.UUID = _TENANT_ID) -> MagicMock:
    ws = MagicMock()
    ws.tenant_id = tenant_id
    ws.workspace_id = _WORKSPACE_ID
    return ws


def _make_workspace_settings(sla: SLAPolicy | None = _DEFAULT_SLA) -> MagicMock:
    settings = MagicMock(spec=WorkspaceSettings)
    settings.sla_policy = sla
    # with_defaults() should return the same mock (SLA already applied)
    settings.with_defaults.return_value = settings
    return settings


def _make_db(
    node_result: MagicMock,
    execution: MagicMock,
    flow: MagicMock,
    rule: MagicMock | None = None,
) -> MagicMock:
    """Return a Session mock whose .query() chain returns the supplied objects."""

    def _query_side_effect(model):
        chain = MagicMock()
        chain.filter.return_value = chain

        from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
        from app.models.rule import DQRule

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
    db.add = MagicMock()
    db.flush = MagicMock()
    db.rollback = MagicMock()
    return db


def _make_persisted_domain(id_: uuid.UUID | None = None, **kwargs) -> IssueDomain:
    """Build a minimal persisted IssueDomain for repo.insert() return value."""
    return IssueDomain(
        id=id_ or uuid.uuid4(),
        tenant_id=kwargs.get("tenant_id", _TENANT_ID),
        workspace_id=kwargs.get("workspace_id", _WORKSPACE_ID),
        flow_execution_id=kwargs.get("flow_execution_id", _EXEC_ID),
        flow_node_result_id=kwargs.get("flow_node_result_id", _NR_ID),
        rule_id=kwargs.get("rule_id", _RULE_ID),
        issue_type="threshold_breach",
        severity=kwargs.get("severity", "critical"),
        status="open",
        title=kwargs.get("title", "[CRITICAL] Check failed: node node_check_001"),
        failure_count=kwargs.get("failure_count", 150),
        rows_scanned=kwargs.get("rows_scanned", 1000),
        pass_rate=kwargs.get("pass_rate", 85.0),
        opened_at=kwargs.get("opened_at", _NOW),
        created_at=_NOW,
        updated_at=_NOW,
    )


# ---------------------------------------------------------------------------
# Helper: build a service with a mocked repository
# ---------------------------------------------------------------------------


def _service_with_mock_repo(persisted: IssueDomain | None = None):
    mock_repo = MagicMock()
    mock_repo.insert.return_value = persisted or _make_persisted_domain()
    return IssueCreationService(repository=mock_repo), mock_repo


# ---------------------------------------------------------------------------
# AC-001: impact_summary and failure_count
# ---------------------------------------------------------------------------


class TestImpactSummaryAndFailureCount:
    def test_impact_summary_and_failure_count_set_correctly(self):
        """P03-AC-001: failure_count=150, impact_summary matches spec format."""
        nr = _make_node_result(
            result_data={"rows_scanned": 1000, "rows_failed": 150, "pass_rate": 85.0}
        )
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("critical")
        db = _make_db(nr, exc, flow, rule)

        svc, mock_repo = _service_with_mock_repo(_make_persisted_domain(failure_count=150))
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is not None
        call_kwargs = mock_repo.insert.call_args[0][1]  # second positional arg = IssueDomain
        assert call_kwargs.failure_count == 150
        assert call_kwargs.impact_summary == "150 of 1000 rows failed (85.0% pass rate)"


# ---------------------------------------------------------------------------
# AC-002: SLA due_at for critical severity
# ---------------------------------------------------------------------------


class TestSLADueAt:
    def test_critical_severity_due_at_is_opened_at_plus_critical_hours(self):
        """P03-AC-002: critical rule + sla.critical_hours=4 → due_at = opened_at + 4h."""
        nr = _make_node_result(completed_at=_NOW)
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("critical")
        db = _make_db(nr, exc, flow, rule)

        persisted = _make_persisted_domain(due_at=_NOW + timedelta(hours=4), severity="critical")
        svc, mock_repo = _service_with_mock_repo(persisted)
        ws = _make_workspace()
        ws_settings = _make_workspace_settings(
            sla=SLAPolicy(
                critical_hours=4, major_hours=24, minor_hours=72, informational_hours=None
            )
        )

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is not None
        domain_arg = mock_repo.insert.call_args[0][1]
        assert domain_arg.due_at == _NOW + timedelta(hours=4)

    def test_null_sla_policy_sets_due_at_none(self):
        """P03-AC-003: workspace with NULL sla_policy → due_at=None."""
        nr = _make_node_result()
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("critical")
        db = _make_db(nr, exc, flow, rule)

        svc, mock_repo = _service_with_mock_repo()
        ws = _make_workspace()
        # settings row exists but sla_policy is None; with_defaults() returns sla_policy=None
        ws_settings = _make_workspace_settings(sla=None)
        ws_settings.sla_policy = None

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        domain_arg = mock_repo.insert.call_args[0][1]
        assert domain_arg.due_at is None

    def test_informational_hours_none_sets_due_at_none(self):
        """P03-AC-004: informational severity + informational_hours=None → due_at=None."""
        nr = _make_node_result()
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("info")  # normalised → 'informational'
        db = _make_db(nr, exc, flow, rule)

        svc, mock_repo = _service_with_mock_repo()
        ws = _make_workspace()
        ws_settings = _make_workspace_settings(
            sla=SLAPolicy(
                critical_hours=4,
                major_hours=24,
                minor_hours=72,
                informational_hours=None,
            )
        )

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        domain_arg = mock_repo.insert.call_args[0][1]
        assert domain_arg.due_at is None


# ---------------------------------------------------------------------------
# AC-005 / AC-006: non-failed nodes return None without inserting
# ---------------------------------------------------------------------------


class TestNonFailedNodeReturnsNone:
    @pytest.mark.parametrize("status", ["completed", "skipped"])
    def test_non_failed_status_returns_none(self, status):
        """P03-AC-005 / P03-AC-006: passing or skipped node → None, no insert."""
        nr = _make_node_result(status=status)
        exc = _make_execution()
        flow = _make_flow()
        db = _make_db(nr, exc, flow)

        svc, mock_repo = _service_with_mock_repo()

        result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is None
        mock_repo.insert.assert_not_called()


# ---------------------------------------------------------------------------
# AC-007: DB INSERT exception → caught, ERROR logged, returns None
# ---------------------------------------------------------------------------


class TestDBExceptionHandling:
    def test_db_exception_is_caught_and_returns_none(self, caplog):
        """P03-AC-007: repository raises → service catches, logs ERROR, returns None."""
        nr = _make_node_result()
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("critical")
        db = _make_db(nr, exc, flow, rule)

        mock_repo = MagicMock()
        mock_repo.insert.side_effect = Exception("DB connection lost")
        svc = IssueCreationService(repository=mock_repo)
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
            caplog.at_level(logging.ERROR, logger="app.services.issues.issue_creation_service"),
        ):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is None
        assert any("F031 issue creation failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# AC-008: two failing nodes → two distinct issues
# ---------------------------------------------------------------------------


class TestTwoFailingNodes:
    def test_two_failing_nodes_produce_two_distinct_issues(self):
        """P03-AC-008: called twice with distinct node_result_ids → two inserts."""
        nr_id_1 = uuid.uuid4()
        nr_id_2 = uuid.uuid4()

        def _make_nr(id_: uuid.UUID) -> MagicMock:
            return _make_node_result(id_=id_, node_id=f"node_{id_}")

        nr1 = _make_nr(nr_id_1)
        nr2 = _make_nr(nr_id_2)
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("major")

        def _query_side(model):
            chain = MagicMock()
            chain.filter.return_value = chain

            from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
            from app.models.rule import DQRule

            if model is FlowNodeResult:
                # Return nr1 first call, nr2 second call
                chain.first.side_effect = [nr1, nr2]
            elif model is FlowExecution:
                chain.first.return_value = exc
            elif model is DQFlow:
                chain.first.return_value = flow
            elif model is DQRule:
                chain.first.return_value = rule
            else:
                chain.first.return_value = None
            return chain

        db = MagicMock()
        db.query.side_effect = _query_side
        db.add = MagicMock()
        db.flush = MagicMock()
        db.rollback = MagicMock()

        mock_repo = MagicMock()
        mock_repo.insert.side_effect = [
            _make_persisted_domain(id_=uuid.uuid4(), flow_node_result_id=nr_id_1),
            _make_persisted_domain(id_=uuid.uuid4(), flow_node_result_id=nr_id_2),
        ]
        svc = IssueCreationService(repository=mock_repo)
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            r1 = svc.create_from_node_result(db, nr_id_1, _EXEC_ID)
            r2 = svc.create_from_node_result(db, nr_id_2, _EXEC_ID)

        assert r1 is not None and r2 is not None
        assert mock_repo.insert.call_count == 2
        insert_args = [mock_repo.insert.call_args_list[i][0][1] for i in range(2)]
        flow_nr_ids = {a.flow_node_result_id for a in insert_args}
        assert len(flow_nr_ids) == 2, "Each insert must have a distinct flow_node_result_id"


# ---------------------------------------------------------------------------
# AC-009: opened_at = node_result.completed_at
# ---------------------------------------------------------------------------


class TestOpenedAt:
    def test_opened_at_equals_node_result_completed_at(self):
        """P03-AC-009: created Issue.opened_at equals node_result.completed_at."""
        completed = datetime(2025, 3, 1, 8, 30, 0, tzinfo=UTC)
        nr = _make_node_result(completed_at=completed)
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("minor")
        db = _make_db(nr, exc, flow, rule)

        svc, mock_repo = _service_with_mock_repo()
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        domain_arg = mock_repo.insert.call_args[0][1]
        assert domain_arg.opened_at == completed


# ---------------------------------------------------------------------------
# AC-010: workspace_id resolved from DQFlow.workspace_id
# ---------------------------------------------------------------------------


class TestWorkspaceIdResolution:
    def test_workspace_id_equals_flow_workspace_id(self):
        """P03-AC-010: Issue.workspace_id = DQFlow.workspace_id."""
        custom_ws_id = uuid.uuid4()
        nr = _make_node_result()
        exc = _make_execution()
        flow = _make_flow(workspace_id=custom_ws_id)
        rule = _make_rule("minor")
        db = _make_db(nr, exc, flow, rule)

        svc, mock_repo = _service_with_mock_repo()
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ) as mock_workspace_lookup,
        ):
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        domain_arg = mock_repo.insert.call_args[0][1]
        mock_workspace_lookup.assert_called_once_with(db, custom_ws_id)
        assert domain_arg.workspace_id == custom_ws_id


# ---------------------------------------------------------------------------
# AC-011: DB failure does NOT change FlowExecution.status
# ---------------------------------------------------------------------------


class TestExecutionStatusUnaffected:
    def test_db_failure_does_not_change_execution_status(self):
        """P03-AC-011: IssueCreationService does not touch FlowExecution.status."""
        nr = _make_node_result()
        execution = _make_execution()
        original_status = execution.status
        flow = _make_flow()
        rule = _make_rule("critical")
        db = _make_db(nr, execution, flow, rule)

        mock_repo = MagicMock()
        mock_repo.insert.side_effect = Exception("DB error")
        svc = IssueCreationService(repository=mock_repo)
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
        ):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is None
        # FlowExecution status must NOT have been modified
        assert execution.status == original_status, (
            "IssueCreationService must not mutate FlowExecution.status"
        )


# ---------------------------------------------------------------------------
# AC-012: success → structured INFO log entry
# ---------------------------------------------------------------------------


class TestSuccessLogging:
    def test_success_produces_info_log(self, caplog):
        """P03-AC-012: successful creation logs INFO with required structured fields."""
        nr = _make_node_result()
        exc = _make_execution()
        flow = _make_flow()
        rule = _make_rule("critical")
        db = _make_db(nr, exc, flow, rule)

        persisted = _make_persisted_domain()
        svc, _ = _service_with_mock_repo(persisted)
        ws = _make_workspace()
        ws_settings = _make_workspace_settings()

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=ws,
            ),
            caplog.at_level(logging.INFO, logger="app.services.issues.issue_creation_service"),
        ):
            result = svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        assert result is not None
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert info_records, "Expected at least one INFO log record on successful creation"
        log = info_records[-1]
        for field in ("issue_id", "workspace_id", "severity", "flow_execution_id", "rule_id"):
            assert hasattr(log, field) or field in getattr(log, "extra", {}), (
                f"Expected structured log field '{field}' to be present"
            )


# ---------------------------------------------------------------------------
# Pure-function helpers — no DB required
# ---------------------------------------------------------------------------


class TestBuildImpactSummary:
    def test_with_pass_rate(self):
        assert _build_impact_summary(150, 1000, 85.0) == (
            "150 of 1000 rows failed (85.0% pass rate)"
        )

    def test_without_pass_rate(self):
        assert _build_impact_summary(5, 200, None) == "5 of 200 rows failed"


class TestComputeDueAt:
    def test_returns_none_when_sla_policy_is_none(self):
        assert _compute_due_at(_NOW, "critical", None) is None

    def test_returns_none_when_opened_at_is_none(self):
        sla = SLAPolicy(critical_hours=4, major_hours=24, minor_hours=72, informational_hours=None)
        assert _compute_due_at(None, "critical", sla) is None

    def test_returns_none_for_informational_hours_none(self):
        sla = SLAPolicy(critical_hours=4, major_hours=24, minor_hours=72, informational_hours=None)
        assert _compute_due_at(_NOW, "informational", sla) is None

    def test_correct_timedelta_for_major(self):
        sla = SLAPolicy(critical_hours=4, major_hours=24, minor_hours=72, informational_hours=None)
        assert _compute_due_at(_NOW, "major", sla) == _NOW + timedelta(hours=24)


class TestNormaliseSeverity:
    @pytest.mark.parametrize(
        "rule_sev,expected",
        [
            ("critical", "critical"),
            ("blocker", "critical"),
            ("major", "major"),
            ("minor", "minor"),
            ("info", "informational"),
            ("informational", "informational"),
            ("CRITICAL", "critical"),  # case-insensitive
            ("unknown_value", "minor"),  # safe default
        ],
    )
    def test_normalise(self, rule_sev, expected):
        assert _normalise_severity(rule_sev) == expected
