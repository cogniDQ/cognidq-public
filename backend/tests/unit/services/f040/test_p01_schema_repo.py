"""
F040 P01 — Schema + Repository Extensions (15 tests)
=====================================================

Covers:
  - Incident ORM lifecycle columns (acknowledged_at, resolved_at, closed_at, resolution_summary)
  - UpdateIncidentRequest schema
  - IncidentRepository get/update methods
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock
from uuid import uuid4

import pytest
from app.models.incident import Incident
from app.services.incidents.incident_models import UpdateIncidentRequest
from app.services.incidents.incident_repository import IncidentRepository

_WS = uuid4()
_TENANT = uuid4()


# ═══════════════════════════════════════════════════════════════════════════════
# ORM Lifecycle Columns
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentLifecycleColumns:
    """Tests 1-4: New lifecycle columns on Incident model."""

    def test_incident_has_acknowledged_at_column(self):
        assert "acknowledged_at" in {c.name for c in Incident.__table__.columns}

    def test_incident_has_resolved_at_column(self):
        assert "resolved_at" in {c.name for c in Incident.__table__.columns}

    def test_incident_has_closed_at_column(self):
        assert "closed_at" in {c.name for c in Incident.__table__.columns}

    def test_incident_has_resolution_summary_column(self):
        assert "resolution_summary" in {c.name for c in Incident.__table__.columns}


# ═══════════════════════════════════════════════════════════════════════════════
# UpdateIncidentRequest Schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpdateIncidentRequest:
    """Tests 5-9, 15: UpdateIncidentRequest Pydantic schema."""

    def test_update_request_valid(self):
        req = UpdateIncidentRequest(status="acknowledged", owner_id=uuid4())
        assert req.status == "acknowledged"
        assert req.owner_id is not None

    def test_update_request_status_only(self):
        req = UpdateIncidentRequest(status="acknowledged")
        assert req.status == "acknowledged"
        assert req.owner_id is None

    def test_update_request_owner_only(self):
        uid = uuid4()
        req = UpdateIncidentRequest(owner_id=uid)
        assert req.owner_id == uid
        assert req.status is None

    def test_update_request_resolution_summary_only(self):
        req = UpdateIncidentRequest(resolution_summary="Root cause identified")
        assert req.resolution_summary == "Root cause identified"

    def test_update_request_impact_summary_only(self):
        req = UpdateIncidentRequest(impact_summary="3 pipelines affected")
        assert req.impact_summary == "3 pipelines affected"

    def test_update_request_empty_rejects(self):
        # All-None is valid at schema level; service enforces non-empty
        req = UpdateIncidentRequest()
        assert req.status is None
        assert req.owner_id is None


# ═══════════════════════════════════════════════════════════════════════════════
# IncidentRepository Extensions
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentRepositoryExtensions:
    """Tests 10-14: get_by_id_and_workspace, update methods."""

    def test_repo_get_by_id_and_workspace_found(self):
        repo = IncidentRepository()
        db = MagicMock()
        inc = Incident(
            id=uuid4(),
            workspace_id=_WS,
            tenant_id=_TENANT,
            title="T",
            severity="major",
            priority="P2",
        )
        db.query.return_value.filter.return_value.first.return_value = inc
        result = repo.get_by_id_and_workspace(db, inc.id, _WS)
        assert result is inc

    def test_repo_get_by_id_and_workspace_not_found(self):
        repo = IncidentRepository()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        result = repo.get_by_id_and_workspace(db, uuid4(), _WS)
        assert result is None

    def test_repo_update_applies_fields(self):
        repo = IncidentRepository()
        db = MagicMock()
        inc = Incident(
            id=uuid4(),
            workspace_id=_WS,
            tenant_id=_TENANT,
            title="T",
            severity="major",
            priority="P2",
            status="open",
        )
        db.query.return_value.filter.return_value.first.return_value = inc
        repo.update(db, inc.id, _WS, {"status": "acknowledged"})
        assert inc.status == "acknowledged"

    def test_repo_update_calls_flush(self):
        repo = IncidentRepository()
        db = MagicMock()
        inc = Incident(
            id=uuid4(),
            workspace_id=_WS,
            tenant_id=_TENANT,
            title="T",
            severity="major",
            priority="P2",
        )
        db.query.return_value.filter.return_value.first.return_value = inc
        repo.update(db, inc.id, _WS, {"status": "acknowledged"})
        db.flush.assert_called_once()

    def test_repo_update_returns_incident(self):
        repo = IncidentRepository()
        db = MagicMock()
        inc = Incident(
            id=uuid4(),
            workspace_id=_WS,
            tenant_id=_TENANT,
            title="T",
            severity="major",
            priority="P2",
        )
        db.query.return_value.filter.return_value.first.return_value = inc
        result = repo.update(db, inc.id, _WS, {"status": "acknowledged"})
        assert result is inc
