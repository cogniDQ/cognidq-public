"""
Unit tests — F003 Packet 2: Settings Models

Verifies all dataclasses, built-in defaults, and WorkspaceSettings.with_defaults()
behaviour from settings_models.py.  No database or I/O dependencies.

Run:
    pytest backend/tests/unit/services/workspaces/test_f003_settings_models.py -v
"""

import uuid
from datetime import UTC, datetime, timezone

import pytest
from app.services.workspaces.settings_models import (
    DEFAULT_NAMING_STANDARDS,
    DEFAULT_SEVERITY_POLICY,
    DEFAULT_SLA_POLICY,
    NamingConstraint,
    NamingStandards,
    SeverityPolicy,
    SLAPolicy,
    WorkspaceSettings,
    WorkspaceSettingsUpdate,
)

_NOW = datetime.now(UTC)
_WID = uuid.uuid4()
_TID = uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# SeverityPolicy
# ─────────────────────────────────────────────────────────────────────────────


class TestSeverityPolicy:
    def test_create_with_all_labels(self):
        p = SeverityPolicy(
            critical_label="P1",
            major_label="P2",
            minor_label="P3",
            informational_label="P4",
        )
        assert p.critical_label == "P1"
        assert p.informational_label == "P4"

    def test_is_frozen(self):
        p = SeverityPolicy("C", "M", "m", "I")
        with pytest.raises(AttributeError):
            p.critical_label = "X"  # type: ignore[misc]

    def test_default_constant_values(self):
        assert DEFAULT_SEVERITY_POLICY.critical_label == "Critical"
        assert DEFAULT_SEVERITY_POLICY.major_label == "Major"
        assert DEFAULT_SEVERITY_POLICY.minor_label == "Minor"
        assert DEFAULT_SEVERITY_POLICY.informational_label == "Informational"


# ─────────────────────────────────────────────────────────────────────────────
# SLAPolicy
# ─────────────────────────────────────────────────────────────────────────────


class TestSLAPolicy:
    def test_create_with_all_hours(self):
        p = SLAPolicy(critical_hours=4, major_hours=24, minor_hours=72, informational_hours=168)
        assert p.critical_hours == 4
        assert p.informational_hours == 168

    def test_informational_hours_can_be_none(self):
        p = SLAPolicy(critical_hours=4, major_hours=24, minor_hours=72, informational_hours=None)
        assert p.informational_hours is None

    def test_is_frozen(self):
        p = SLAPolicy(4, 24, 72, None)
        with pytest.raises(AttributeError):
            p.critical_hours = 99  # type: ignore[misc]

    def test_default_constant_values(self):
        assert DEFAULT_SLA_POLICY.critical_hours == 4
        assert DEFAULT_SLA_POLICY.major_hours == 24
        assert DEFAULT_SLA_POLICY.minor_hours == 72
        assert DEFAULT_SLA_POLICY.informational_hours is None


# ─────────────────────────────────────────────────────────────────────────────
# NamingConstraint
# ─────────────────────────────────────────────────────────────────────────────


class TestNamingConstraint:
    def test_all_optional_fields_can_be_none(self):
        c = NamingConstraint(
            required_prefix=None,
            required_suffix=None,
            pattern=None,
            max_length=None,
            allow_special_characters=None,
        )
        assert c.required_prefix is None
        assert c.max_length is None

    def test_fields_can_be_populated(self):
        c = NamingConstraint(
            required_prefix="raw_",
            required_suffix=None,
            pattern=r"^[a-z_]+$",
            max_length=100,
            allow_special_characters=False,
        )
        assert c.required_prefix == "raw_"
        assert c.max_length == 100
        assert c.allow_special_characters is False

    def test_is_frozen(self):
        c = NamingConstraint(None, None, None, None, None)
        with pytest.raises(AttributeError):
            c.max_length = 50  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# NamingStandards
# ─────────────────────────────────────────────────────────────────────────────


class TestNamingStandards:
    def test_create_with_sub_constraints(self):
        ds = NamingConstraint("raw_", None, None, None, None)
        r = NamingConstraint(None, None, r"^[a-z]+$", None, True)
        ns = NamingStandards(datasets=ds, rules=r)
        assert ns.datasets.required_prefix == "raw_"
        assert ns.rules.allow_special_characters is True

    def test_default_constant_is_all_none(self):
        assert DEFAULT_NAMING_STANDARDS.datasets.required_prefix is None
        assert DEFAULT_NAMING_STANDARDS.datasets.max_length is None
        assert DEFAULT_NAMING_STANDARDS.rules.pattern is None


# ─────────────────────────────────────────────────────────────────────────────
# WorkspaceSettings
# ─────────────────────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> WorkspaceSettings:
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
    )
    defaults.update(overrides)
    return WorkspaceSettings(**defaults)


class TestWorkspaceSettings:
    def test_create_with_all_nulls(self):
        ws = _make_settings()
        assert ws.severity_policy is None
        assert ws.sla_policy is None
        assert ws.naming_standards is None

    def test_is_frozen(self):
        ws = _make_settings()
        with pytest.raises(AttributeError):
            ws.default_timezone = "Europe/Paris"  # type: ignore[misc]

    def test_with_defaults_fills_null_severity(self):
        ws = _make_settings(severity_policy=None)
        result = ws.with_defaults()
        assert result.severity_policy == DEFAULT_SEVERITY_POLICY

    def test_with_defaults_fills_null_sla(self):
        ws = _make_settings(sla_policy=None)
        result = ws.with_defaults()
        assert result.sla_policy == DEFAULT_SLA_POLICY

    def test_with_defaults_fills_null_naming(self):
        ws = _make_settings(naming_standards=None)
        result = ws.with_defaults()
        assert result.naming_standards == DEFAULT_NAMING_STANDARDS

    def test_with_defaults_preserves_existing_severity(self):
        custom = SeverityPolicy("P1", "P2", "P3", "P4")
        ws = _make_settings(severity_policy=custom)
        result = ws.with_defaults()
        assert result.severity_policy is custom

    def test_with_defaults_preserves_existing_sla(self):
        custom = SLAPolicy(1, 8, 48, 96)
        ws = _make_settings(sla_policy=custom)
        result = ws.with_defaults()
        assert result.sla_policy is custom

    def test_with_defaults_preserves_existing_naming_standards(self):
        custom = NamingStandards(
            datasets=NamingConstraint("raw_", None, None, None, None),
            rules=NamingConstraint(None, None, None, None, None),
        )
        ws = _make_settings(naming_standards=custom)
        result = ws.with_defaults()
        assert result.naming_standards is custom

    def test_with_defaults_returns_new_instance(self):
        ws = _make_settings()
        result = ws.with_defaults()
        assert result is not ws

    def test_with_defaults_preserves_non_policy_fields(self):
        actor_id = uuid.uuid4()
        ws = _make_settings(
            default_timezone="America/New_York",
            issue_grouping_policy="one_per_rule",
            updated_by=actor_id,
        )
        result = ws.with_defaults()
        assert result.default_timezone == "America/New_York"
        assert result.issue_grouping_policy == "one_per_rule"
        assert result.updated_by == actor_id
        assert result.workspace_id == _WID
        assert result.tenant_id == _TID


# ─────────────────────────────────────────────────────────────────────────────
# WorkspaceSettingsUpdate
# ─────────────────────────────────────────────────────────────────────────────


class TestWorkspaceSettingsUpdate:
    def test_all_fields_default_to_none(self):
        u = WorkspaceSettingsUpdate()
        assert u.default_timezone is None
        assert u.severity_policy is None
        assert u.sla_policy is None
        assert u.issue_grouping_policy is None
        assert u.naming_standards is None

    def test_is_mutable(self):
        u = WorkspaceSettingsUpdate()
        u.default_timezone = "Europe/London"
        assert u.default_timezone == "Europe/London"

    def test_partial_population(self):
        u = WorkspaceSettingsUpdate(
            default_timezone="Asia/Tokyo",
            issue_grouping_policy="one_per_day",
        )
        assert u.default_timezone == "Asia/Tokyo"
        assert u.issue_grouping_policy == "one_per_day"
        assert u.severity_policy is None
