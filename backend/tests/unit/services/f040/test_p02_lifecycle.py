"""
F040 P02 — IncidentLifecycleService Tests (15 tests)
=====================================================

Covers:
  - Status transition validation (allowed and disallowed)
  - Resolution summary enforcement
  - Timestamp side-effects
  - Owner changes
  - Audit integration
  - Constants
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.models.incident import Incident
from app.services.audit.constants import VALID_ACTION_TYPES
from app.services.audit.models import AuditContext
from app.services.incidents.incident_lifecycle_service import (
    EmptyUpdateError,
    IncidentLifecycleService,
    IncidentNotFoundError,
    InvalidStatusTransitionError,
    ResolutionSummaryRequiredError,
)
from app.services.incidents.incident_repository import IncidentRepository

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_INC_ID = uuid4()


def _audit_ctx() -> AuditContext:
    return AuditContext(
        tenant_id=_TENANT,
        actor_id=_USER,
        actor_type="user",
        actor_role="admin",
        request_id=uuid4(),
        source_ip="127.0.0.1",
    )


def _make_incident(status="open", resolution_summary=None):
    inc = Incident(
        id=_INC_ID,
        tenant_id=_TENANT,
        workspace_id=_WS,
        title="Test Incident",
        severity="critical",
        priority="P1",
        status=status,
        resolution_summary=resolution_summary,
        opened_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    inc.owner = None
    inc.creator = None
    return inc


def _make_service(incident=None):
    repo = MagicMock(spec=IncidentRepository)
    repo.get_by_id_and_workspace.return_value = incident
    repo.update.side_effect = lambda db, iid, ws, updates: _apply_updates(incident, updates)
    repo.count_linked_issues.return_value = 2

    audit = MagicMock()
    audit.write.return_value = None

    svc = IncidentLifecycleService(repo=repo, audit_service=audit)
    return svc, repo, audit


def _apply_updates(inc, updates):
    if inc is None:
        return inc
    for k, v in updates.items():
        setattr(inc, k, v)
    return inc


def _call_update(svc, *, status=None, owner_id=None, resolution_summary=None):
    fields = set()
    if status is not None:
        fields.add("status")
    if owner_id is not None:
        fields.add("owner_id")
    if resolution_summary is not None:
        fields.add("resolution_summary")
    if not fields:
        fields = set()

    db = MagicMock()
    db.refresh = lambda obj: None  # no-op
    return svc.update_incident(
        db,
        _INC_ID,
        _WS,
        fields_provided=fields,
        status=status,
        owner_id=owner_id,
        resolution_summary=resolution_summary,
        audit_ctx=_audit_ctx(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Status Transitions
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatusTransitions:
    """Tests 1-5: Valid and invalid transitions."""

    def test_open_to_acknowledged(self):
        inc = _make_incident(status="open")
        svc, _, _ = _make_service(inc)
        resp = _call_update(svc, status="acknowledged")
        assert resp.status == "acknowledged"

    def test_acknowledged_to_resolved(self):
        inc = _make_incident(status="acknowledged")
        svc, _, _ = _make_service(inc)
        resp = _call_update(svc, status="resolved", resolution_summary="Fixed root cause")
        assert resp.status == "resolved"

    def test_open_to_resolved_rejected(self):
        inc = _make_incident(status="open")
        svc, _, _ = _make_service(inc)
        with pytest.raises(InvalidStatusTransitionError):
            _call_update(svc, status="resolved", resolution_summary="Fixed")

    def test_closed_to_reopened(self):
        inc = _make_incident(status="closed", resolution_summary="Done")
        svc, _, _ = _make_service(inc)
        resp = _call_update(svc, status="reopened")
        assert resp.status == "reopened"

    def test_reopened_to_acknowledged(self):
        inc = _make_incident(status="reopened")
        svc, _, _ = _make_service(inc)
        resp = _call_update(svc, status="acknowledged")
        assert resp.status == "acknowledged"


# ═══════════════════════════════════════════════════════════════════════════════
# Resolution Summary
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolutionSummary:
    """Tests 6-7: Resolution summary required for resolve/close."""

    def test_resolved_requires_summary(self):
        inc = _make_incident(status="acknowledged")
        svc, _, _ = _make_service(inc)
        with pytest.raises(ResolutionSummaryRequiredError):
            _call_update(svc, status="resolved")

    def test_closed_requires_summary(self):
        inc = _make_incident(status="acknowledged")
        svc, _, _ = _make_service(inc)
        with pytest.raises(ResolutionSummaryRequiredError):
            _call_update(svc, status="closed")


# ═══════════════════════════════════════════════════════════════════════════════
# Timestamp Side-Effects
# ═══════════════════════════════════════════════════════════════════════════════


class TestTimestampEffects:
    """Tests 8-10: Lifecycle timestamps set on transitions."""

    def test_acknowledged_sets_timestamp(self):
        inc = _make_incident(status="open")
        svc, _, _ = _make_service(inc)
        _call_update(svc, status="acknowledged")
        assert inc.acknowledged_at is not None

    def test_resolved_sets_timestamp(self):
        inc = _make_incident(status="acknowledged")
        svc, _, _ = _make_service(inc)
        _call_update(svc, status="resolved", resolution_summary="Fixed")
        assert inc.resolved_at is not None

    def test_closed_sets_timestamp(self):
        inc = _make_incident(status="acknowledged")
        svc, _, _ = _make_service(inc)
        _call_update(svc, status="closed", resolution_summary="Closed out")
        assert inc.closed_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Owner & Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestOwnerAndValidation:
    """Tests 11-13: Owner change, empty update, not found."""

    def test_owner_change(self):
        new_owner = uuid4()
        inc = _make_incident(status="open")
        svc, _, _ = _make_service(inc)
        resp = _call_update(svc, owner_id=new_owner)
        assert resp.owner_id == new_owner

    def test_empty_update_rejected(self):
        inc = _make_incident(status="open")
        svc, _, _ = _make_service(inc)
        db = MagicMock()
        with pytest.raises(EmptyUpdateError):
            svc.update_incident(
                db,
                _INC_ID,
                _WS,
                fields_provided=set(),
                audit_ctx=_audit_ctx(),
            )

    def test_incident_not_found(self):
        svc, _, _ = _make_service(incident=None)
        with pytest.raises(IncidentNotFoundError):
            _call_update(svc, status="acknowledged")


# ═══════════════════════════════════════════════════════════════════════════════
# Audit
# ═══════════════════════════════════════════════════════════════════════════════


class TestAudit:
    """Tests 14-15: Audit integration and constants."""

    def test_audit_written_on_status_change(self):
        inc = _make_incident(status="open")
        svc, _, audit = _make_service(inc)
        _call_update(svc, status="acknowledged")
        audit.write.assert_called_once()
        entry = audit.write.call_args[0][1]
        assert entry.action_type == "incident_status_changed"

    def test_audit_constants_include_new_actions(self):
        for action in ("incident_status_changed", "incident_owner_changed", "incident_updated"):
            assert action in VALID_ACTION_TYPES, f"{action} not in VALID_ACTION_TYPES"
