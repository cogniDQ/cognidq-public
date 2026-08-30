"""
F038 P02 — Repository + Service + Audit Tests (15 tests)
=========================================================

Covers:
  - IncidentRepository (insert, bulk_insert_links)
  - IncidentService.create_incident() (happy path, validation, audit)
  - Audit constants for incident entity
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.models.incident import Incident, IncidentIssue
from app.services.audit.constants import VALID_ACTION_TYPES, VALID_ENTITY_TYPES
from app.services.audit.models import AuditContext
from app.services.incidents.incident_repository import IncidentRepository
from app.services.incidents.incident_service import (
    IncidentService,
    IncidentValidationError,
    IssueNotFoundError,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_ISSUE_1 = uuid4()
_ISSUE_2 = uuid4()


def _insert_side_effect(db, incident):
    """Simulate flush populating server defaults."""
    incident.id = uuid4()
    incident.opened_at = datetime.now(UTC)
    incident.updated_at = datetime.now(UTC)
    incident.created_at = datetime.now(UTC)
    incident.status = incident.status or "open"
    incident.owner = None
    incident.creator = None
    return incident


def _audit_ctx() -> AuditContext:
    return AuditContext(
        tenant_id=_TENANT,
        actor_id=_USER,
        actor_type="user",
        actor_role="admin",
        request_id=uuid4(),
        source_ip="127.0.0.1",
    )


def _make_service(issues_found=None):
    """Build an IncidentService with mocked repo + audit."""
    repo = MagicMock(spec=IncidentRepository)
    repo.insert.side_effect = _insert_side_effect
    repo.bulk_insert_links.return_value = None
    repo.get_issues_in_workspace.return_value = (
        issues_found if issues_found is not None else [_ISSUE_1, _ISSUE_2]
    )

    audit = MagicMock()
    audit.write.return_value = None

    svc = IncidentService(repo=repo, audit_service=audit)
    return svc, repo, audit


def _call_create(svc, **overrides):
    """Shorthand for a valid create_incident call."""
    defaults = dict(
        workspace_id=_WS,
        tenant_id=_TENANT,
        created_by_user_id=_USER,
        title="DQ Pipeline Outage",
        severity="critical",
        priority="P1",
        issue_ids=[_ISSUE_1, _ISSUE_2],
        audit_ctx=_audit_ctx(),
    )
    defaults.update(overrides)
    db = MagicMock()
    return svc.create_incident(db, **defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Repository
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentRepository:
    """Tests 1-3: IncidentRepository data access."""

    def test_repo_insert_calls_flush(self):
        repo = IncidentRepository()
        db = MagicMock()
        incident = Incident(
            tenant_id=_TENANT, workspace_id=_WS, title="T", severity="major", priority="P2"
        )
        repo.insert(db, incident)
        db.add.assert_called_once_with(incident)
        db.flush.assert_called_once()

    def test_repo_insert_returns_orm(self):
        repo = IncidentRepository()
        db = MagicMock()
        incident = Incident(
            tenant_id=_TENANT, workspace_id=_WS, title="T", severity="major", priority="P2"
        )
        result = repo.insert(db, incident)
        assert result is incident

    def test_repo_bulk_insert_links(self):
        repo = IncidentRepository()
        db = MagicMock()
        links = [IncidentIssue(incident_id=uuid4(), issue_id=uuid4()) for _ in range(3)]
        repo.bulk_insert_links(db, links)
        db.add_all.assert_called_once_with(links)
        db.flush.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentService:
    """Tests 4-13: IncidentService.create_incident()."""

    def test_create_incident_happy_path(self):
        svc, _, _ = _make_service()
        resp = _call_create(svc)
        assert resp is not None

    def test_create_incident_returns_response(self):
        svc, _, _ = _make_service()
        resp = _call_create(svc)
        assert resp.title == "DQ Pipeline Outage"
        assert resp.severity == "critical"
        assert resp.priority == "P1"
        assert resp.status == "open"

    def test_create_incident_issue_not_found(self):
        svc, _, _ = _make_service(issues_found=[_ISSUE_1])  # missing _ISSUE_2
        with pytest.raises(IssueNotFoundError):
            _call_create(svc)

    def test_create_incident_invalid_title(self):
        svc, _, _ = _make_service()
        with pytest.raises(IncidentValidationError):
            _call_create(svc, title="   ")

    def test_create_incident_invalid_severity(self):
        svc, _, _ = _make_service()
        with pytest.raises(IncidentValidationError):
            _call_create(svc, severity="extreme")

    def test_create_incident_invalid_priority(self):
        svc, _, _ = _make_service()
        with pytest.raises(IncidentValidationError):
            _call_create(svc, priority="P5")

    def test_create_incident_empty_issue_ids(self):
        svc, _, _ = _make_service()
        with pytest.raises(IncidentValidationError):
            _call_create(svc, issue_ids=[])

    def test_create_incident_writes_audit(self):
        svc, _, audit = _make_service()
        _call_create(svc)
        audit.write.assert_called_once()

    def test_create_incident_audit_action_type(self):
        svc, _, audit = _make_service()
        _call_create(svc)
        entry = audit.write.call_args[0][1]
        assert entry.action_type == "incident_created"

    def test_create_incident_inserts_links(self):
        svc, repo, _ = _make_service()
        _call_create(svc)
        repo.bulk_insert_links.assert_called_once()
        links = repo.bulk_insert_links.call_args[0][1]
        assert len(links) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Constants
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuditConstants:
    """Tests 14-15: Audit constants include incident entries."""

    def test_audit_constants_include_incident(self):
        assert "incident" in VALID_ENTITY_TYPES

    def test_audit_constants_include_incident_created(self):
        assert "incident_created" in VALID_ACTION_TYPES
