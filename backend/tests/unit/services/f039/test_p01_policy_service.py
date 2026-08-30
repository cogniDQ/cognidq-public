"""
F039 P01 — Policy Models + Auto-Incident Service Tests
=========================================================

Tests for IncidentPolicy (models) and AutoIncidentService (evaluate_and_create).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from app.services.incidents.auto_incident_models import (
    DEFAULT_INCIDENT_POLICY,
    IncidentPolicy,
)
from app.services.incidents.auto_incident_service import AutoIncidentService

# ---------------------------------------------------------------------------
# IncidentPolicy model tests
# ---------------------------------------------------------------------------


class TestIncidentPolicyDefaults:
    def test_default_is_disabled(self):
        assert DEFAULT_INCIDENT_POLICY.enabled is False

    def test_default_min_severity(self):
        assert DEFAULT_INCIDENT_POLICY.min_severity == "critical"

    def test_default_recurrence_threshold(self):
        assert DEFAULT_INCIDENT_POLICY.recurrence_threshold == 1

    def test_default_auto_priority_none(self):
        assert DEFAULT_INCIDENT_POLICY.auto_priority is None

    def test_default_auto_owner_none(self):
        assert DEFAULT_INCIDENT_POLICY.auto_owner_user_id is None


class TestSeverityMet:
    def test_critical_meets_critical(self):
        p = IncidentPolicy(enabled=True, min_severity="critical")
        assert p.severity_met("critical") is True

    def test_major_does_not_meet_critical(self):
        p = IncidentPolicy(enabled=True, min_severity="critical")
        assert p.severity_met("major") is False

    def test_critical_meets_major_threshold(self):
        p = IncidentPolicy(enabled=True, min_severity="major")
        assert p.severity_met("critical") is True

    def test_major_meets_major(self):
        p = IncidentPolicy(enabled=True, min_severity="major")
        assert p.severity_met("major") is True

    def test_minor_does_not_meet_major(self):
        p = IncidentPolicy(enabled=True, min_severity="major")
        assert p.severity_met("minor") is False

    def test_informational_meets_informational(self):
        p = IncidentPolicy(enabled=True, min_severity="informational")
        assert p.severity_met("informational") is True

    def test_unknown_severity_does_not_meet(self):
        p = IncidentPolicy(enabled=True, min_severity="critical")
        assert p.severity_met("unknown") is False


class TestRecurrenceMet:
    def test_at_threshold(self):
        p = IncidentPolicy(enabled=True, recurrence_threshold=3)
        assert p.recurrence_met(3) is True

    def test_above_threshold(self):
        p = IncidentPolicy(enabled=True, recurrence_threshold=3)
        assert p.recurrence_met(5) is True

    def test_below_threshold(self):
        p = IncidentPolicy(enabled=True, recurrence_threshold=3)
        assert p.recurrence_met(2) is False

    def test_default_threshold_one(self):
        p = IncidentPolicy(enabled=True)
        assert p.recurrence_met(1) is True


class TestDerivePriority:
    def test_explicit_priority(self):
        p = IncidentPolicy(enabled=True, auto_priority="P2")
        assert p.derive_priority("critical") == "P2"

    def test_critical_maps_to_p1(self):
        p = IncidentPolicy(enabled=True)
        assert p.derive_priority("critical") == "P1"

    def test_major_maps_to_p2(self):
        p = IncidentPolicy(enabled=True)
        assert p.derive_priority("major") == "P2"

    def test_minor_maps_to_p3(self):
        p = IncidentPolicy(enabled=True)
        assert p.derive_priority("minor") == "P3"

    def test_informational_maps_to_p4(self):
        p = IncidentPolicy(enabled=True)
        assert p.derive_priority("informational") == "P4"

    def test_unknown_defaults_to_p3(self):
        p = IncidentPolicy(enabled=True)
        assert p.derive_priority("unknown") == "P3"


# ---------------------------------------------------------------------------
# AutoIncidentService tests
# ---------------------------------------------------------------------------


def _make_repo():
    repo = MagicMock()
    incident_mock = MagicMock()
    incident_mock.id = uuid.uuid4()
    repo.insert.return_value = incident_mock
    repo.bulk_insert_links.return_value = None
    return repo, incident_mock


def _base_kwargs():
    return dict(
        workspace_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        issue_id=uuid.uuid4(),
        issue_severity="critical",
        issue_failure_count=1,
        issue_title="Null values in column X",
    )


class TestAutoIncidentServiceDisabled:
    def test_returns_none_when_disabled(self):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        result = svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=False),
        )
        assert result is None
        repo.insert.assert_not_called()

    def test_returns_none_with_default_policy(self):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        result = svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=None,
        )
        assert result is None


class TestAutoIncidentServiceSeverity:
    def test_skip_when_severity_below_threshold(self):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        kwargs = _base_kwargs()
        kwargs["issue_severity"] = "minor"
        result = svc.evaluate_and_create(
            MagicMock(),
            **kwargs,
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        assert result is None

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_creates_when_severity_met(self, _mock):
        repo, inc = _make_repo()
        svc = AutoIncidentService(repo=repo)
        result = svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        assert result == inc.id
        repo.insert.assert_called_once()


class TestAutoIncidentServiceRecurrence:
    def test_skip_when_recurrence_below(self):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        kwargs = _base_kwargs()
        kwargs["issue_failure_count"] = 2
        result = svc.evaluate_and_create(
            MagicMock(),
            **kwargs,
            policy=IncidentPolicy(enabled=True, min_severity="critical", recurrence_threshold=5),
        )
        assert result is None

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_creates_when_recurrence_met(self, _mock):
        repo, inc = _make_repo()
        svc = AutoIncidentService(repo=repo)
        kwargs = _base_kwargs()
        kwargs["issue_failure_count"] = 5
        result = svc.evaluate_and_create(
            MagicMock(),
            **kwargs,
            policy=IncidentPolicy(enabled=True, min_severity="critical", recurrence_threshold=5),
        )
        assert result == inc.id


class TestAutoIncidentServiceDuplicate:
    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=True)
    def test_skip_when_already_linked(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        result = svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        assert result is None
        repo.insert.assert_not_called()


class TestAutoIncidentServiceCreation:
    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_incident_title_has_auto_prefix(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        call_args = repo.insert.call_args
        incident = call_args[0][1]  # positional: (db, incident)
        assert incident.title.startswith("[Auto]")

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_incident_uses_derived_priority(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        call_args = repo.insert.call_args
        incident = call_args[0][1]
        assert incident.priority == "P1"

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_incident_uses_explicit_priority(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical", auto_priority="P3"),
        )
        call_args = repo.insert.call_args
        incident = call_args[0][1]
        assert incident.priority == "P3"

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_incident_sets_auto_owner(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        owner = uuid.uuid4()
        svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical", auto_owner_user_id=owner),
        )
        call_args = repo.insert.call_args
        incident = call_args[0][1]
        assert incident.owner_id == owner

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_creates_issue_link(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        kwargs = _base_kwargs()
        svc.evaluate_and_create(
            MagicMock(),
            **kwargs,
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        repo.bulk_insert_links.assert_called_once()
        links = repo.bulk_insert_links.call_args[0][1]
        assert len(links) == 1
        assert links[0].issue_id == kwargs["issue_id"]

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_incident_status_is_open(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        svc.evaluate_and_create(
            MagicMock(),
            **_base_kwargs(),
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        call_args = repo.insert.call_args
        incident = call_args[0][1]
        assert incident.status == "open"

    @patch.object(AutoIncidentService, "_issue_has_open_incident", return_value=False)
    def test_long_title_truncated(self, _mock):
        repo, _ = _make_repo()
        svc = AutoIncidentService(repo=repo)
        kwargs = _base_kwargs()
        kwargs["issue_title"] = "X" * 500
        svc.evaluate_and_create(
            MagicMock(),
            **kwargs,
            policy=IncidentPolicy(enabled=True, min_severity="critical"),
        )
        call_args = repo.insert.call_args
        incident = call_args[0][1]
        assert len(incident.title) <= 500
        assert incident.title.endswith("...")
