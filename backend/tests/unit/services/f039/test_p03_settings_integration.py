"""
F039 P03 — Settings Integration + Serialization Tests
========================================================

Tests that:
1. WorkspaceSettings carries incident_policy correctly
2. with_defaults() fills None → DEFAULT_INCIDENT_POLICY
3. Serialization includes incident_policy when present
4. IssueCreationService passes incident_policy from settings to the hook
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from app.services.incidents.auto_incident_models import (
    DEFAULT_INCIDENT_POLICY,
    SHIPPING_DEFAULT_INCIDENT_POLICY,
    IncidentPolicy,
)
from app.services.issues.issue_creation_service import IssueCreationService
from app.services.issues.issue_models import IssueDomain
from app.services.workspaces.settings_models import (
    DEFAULT_NAMING_STANDARDS,
    DEFAULT_SEVERITY_POLICY,
    DEFAULT_SLA_POLICY,
    WorkspaceSettings,
    WorkspaceSettingsUpdate,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_WID = uuid.uuid4()
_TID = uuid.uuid4()
_NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)

_EXEC_ID = uuid.uuid4()
_FLOW_ID = uuid.uuid4()
_NR_ID = uuid.uuid4()
_RULE_ID = uuid.uuid4()


def _make_settings(**overrides):
    defaults = dict(
        workspace_id=_WID,
        tenant_id=_TID,
        default_timezone="UTC",
        issue_grouping_policy="one_per_execution",
        updated_at=_NOW,
        updated_by=None,
        severity_policy=None,
        sla_policy=None,
        naming_standards=None,
        incident_policy=None,
    )
    defaults.update(overrides)
    return WorkspaceSettings(**defaults)


# ---------------------------------------------------------------------------
# WorkspaceSettings model tests
# ---------------------------------------------------------------------------


class TestWorkspaceSettingsIncidentPolicy:
    def test_default_incident_policy_is_none(self):
        ws = _make_settings()
        assert ws.incident_policy is None

    def test_explicit_incident_policy_stored(self):
        pol = IncidentPolicy(enabled=True, min_severity="major")
        ws = _make_settings(incident_policy=pol)
        assert ws.incident_policy is pol
        assert ws.incident_policy.enabled is True
        assert ws.incident_policy.min_severity == "major"

    def test_with_defaults_fills_none_to_default(self):
        ws = _make_settings(incident_policy=None)
        result = ws.with_defaults()
        assert result.incident_policy == SHIPPING_DEFAULT_INCIDENT_POLICY
        assert result.incident_policy.enabled is True

    def test_with_defaults_preserves_existing_policy(self):
        pol = IncidentPolicy(enabled=True, min_severity="minor", recurrence_threshold=3)
        ws = _make_settings(incident_policy=pol)
        result = ws.with_defaults()
        assert result.incident_policy is pol
        assert result.incident_policy.enabled is True

    def test_frozen_cannot_mutate_incident_policy(self):
        ws = _make_settings()
        with pytest.raises(AttributeError):
            ws.incident_policy = IncidentPolicy()  # type: ignore[misc]


class TestWorkspaceSettingsUpdateIncidentPolicy:
    def test_default_is_none(self):
        update = WorkspaceSettingsUpdate()
        assert update.incident_policy is None

    def test_can_set_incident_policy(self):
        pol = IncidentPolicy(enabled=True, min_severity="critical")
        update = WorkspaceSettingsUpdate(incident_policy=pol)
        assert update.incident_policy is pol


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestSerializeIncidentPolicy:
    def test_serialize_none_policy(self):
        from app.api.v1.endpoints.workspaces import _serialize_workspace_settings

        _make_settings().with_defaults()
        # Override incident_policy to None for this specific test
        ws_none = _make_settings(
            severity_policy=DEFAULT_SEVERITY_POLICY,
            sla_policy=DEFAULT_SLA_POLICY,
            naming_standards=DEFAULT_NAMING_STANDARDS,
            incident_policy=None,
        )
        data = _serialize_workspace_settings(ws_none)
        assert data["incident_policy"] is None

    def test_serialize_enabled_policy(self):
        from app.api.v1.endpoints.workspaces import _serialize_workspace_settings

        pol = IncidentPolicy(enabled=True, min_severity="major", recurrence_threshold=5)
        ws = _make_settings(
            severity_policy=DEFAULT_SEVERITY_POLICY,
            sla_policy=DEFAULT_SLA_POLICY,
            naming_standards=DEFAULT_NAMING_STANDARDS,
            incident_policy=pol,
        )
        data = _serialize_workspace_settings(ws)
        assert data["incident_policy"]["enabled"] is True
        assert data["incident_policy"]["min_severity"] == "major"
        assert data["incident_policy"]["recurrence_threshold"] == 5
        assert data["incident_policy"]["auto_priority"] is None
        assert data["incident_policy"]["auto_owner_user_id"] is None

    def test_serialize_policy_with_owner(self):
        from app.api.v1.endpoints.workspaces import _serialize_workspace_settings

        owner = uuid.uuid4()
        pol = IncidentPolicy(
            enabled=True,
            min_severity="critical",
            auto_priority="P1",
            auto_owner_user_id=owner,
        )
        ws = _make_settings(
            severity_policy=DEFAULT_SEVERITY_POLICY,
            sla_policy=DEFAULT_SLA_POLICY,
            naming_standards=DEFAULT_NAMING_STANDARDS,
            incident_policy=pol,
        )
        data = _serialize_workspace_settings(ws)
        assert data["incident_policy"]["auto_priority"] == "P1"
        assert data["incident_policy"]["auto_owner_user_id"] == str(owner)


# ---------------------------------------------------------------------------
# Hook passes policy from settings
# ---------------------------------------------------------------------------


def _make_node_result():
    nr = MagicMock()
    nr.id = _NR_ID
    nr.status = "failed"
    nr.node_id = "node_check_001"
    nr.completed_at = _NOW
    nr.result_data = {"rows_scanned": 1000, "rows_failed": 150, "pass_rate": 85.0}
    return nr


def _make_execution():
    exc = MagicMock()
    exc.id = _EXEC_ID
    exc.flow_id = _FLOW_ID
    return exc


def _make_flow():
    flow = MagicMock()
    flow.id = _FLOW_ID
    flow.workspace_id = _WID
    flow.flow_definition = {
        "nodes": [{"id": "node_check_001", "type": "check", "config": {"rule_id": str(_RULE_ID)}}],
        "connections": [],
    }
    return flow


def _make_rule():
    rule = MagicMock()
    rule.id = _RULE_ID
    rule.severity = "critical"
    return rule


def _make_workspace():
    ws = MagicMock()
    ws.tenant_id = _TID
    return ws


def _make_persisted_domain(**overrides):
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=_TID,
        workspace_id=_WID,
        flow_execution_id=_EXEC_ID,
        flow_node_result_id=_NR_ID,
        rule_id=_RULE_ID,
        issue_type="threshold_breach",
        severity="critical",
        status="open",
        title="[CRITICAL] Check failed",
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
    from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
    from app.models.rule import DQRule

    def _q(model):
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
    db.query.side_effect = _q
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


class TestHookPassesPolicy:
    """Verify step 13b forwards the incident_policy from workspace_settings."""

    def _run(self, incident_policy):
        """Run create_from_node_result with a workspace_settings that has given policy."""
        persisted = _make_persisted_domain()
        svc, _, mock_auto = _build_service(persisted=persisted)
        db = _make_db(_make_node_result(), _make_execution(), _make_flow(), _make_rule())

        ws_settings = MagicMock(spec=WorkspaceSettings)
        ws_settings.sla_policy = DEFAULT_SLA_POLICY
        ws_settings.with_defaults.return_value = ws_settings
        ws_settings.incident_policy = incident_policy

        with (
            patch(
                "app.services.issues.issue_creation_service._settings_repo.find_by_workspace_id",
                return_value=ws_settings,
            ),
            patch(
                "app.services.issues.issue_creation_service._workspace_repo.find_by_id_any_tenant",
                return_value=_make_workspace(),
            ),
        ):
            svc.create_from_node_result(db, _NR_ID, _EXEC_ID)

        return mock_auto

    def test_none_policy_passed_as_none(self):
        mock_auto = self._run(incident_policy=None)
        kwargs = mock_auto.evaluate_and_create.call_args.kwargs
        assert kwargs["policy"] is None

    def test_enabled_policy_passed_through(self):
        pol = IncidentPolicy(enabled=True, min_severity="major")
        mock_auto = self._run(incident_policy=pol)
        kwargs = mock_auto.evaluate_and_create.call_args.kwargs
        assert kwargs["policy"] is pol
        assert kwargs["policy"].enabled is True

    def test_disabled_policy_passed_through(self):
        pol = IncidentPolicy(enabled=False)
        mock_auto = self._run(incident_policy=pol)
        kwargs = mock_auto.evaluate_and_create.call_args.kwargs
        assert kwargs["policy"] is pol
        assert kwargs["policy"].enabled is False
