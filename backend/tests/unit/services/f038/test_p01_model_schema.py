"""
F038 P01 — Incident Model + Schema Tests (15 tests)
====================================================

Covers:
  - Incident ORM model (columns, defaults, relationships)
  - IncidentIssue ORM model (composite PK, relationship)
  - CreateIncidentRequest schema validation
  - IncidentResponse schema fields
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from uuid import uuid4

import pytest
from app.models.incident import Incident, IncidentIssue
from app.services.incidents.incident_models import (
    CreateIncidentRequest,
    IncidentResponse,
)
from pydantic import ValidationError

# ═══════════════════════════════════════════════════════════════════════════════
# Incident ORM Model
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentModel:
    """Tests 1-6: Incident ORM model structure."""

    def test_incident_table_name(self):
        assert Incident.__tablename__ == "incidents"

    def test_incident_columns(self):
        cols = {c.name for c in Incident.__table__.columns}
        expected = {
            "id",
            "tenant_id",
            "workspace_id",
            "title",
            "severity",
            "priority",
            "status",
            "impact_summary",
            "owner_id",
            "created_by_user_id",
            "opened_at",
            "updated_at",
            "created_at",
        }
        assert expected.issubset(cols)

    def test_incident_default_id(self):
        col = Incident.__table__.c.id
        assert col.default is not None
        assert callable(col.default.arg)

    def test_incident_default_status(self):
        col = Incident.__table__.c.status
        assert col.default is not None
        assert col.default.arg == "open"

    def test_incident_owner_relationship(self):
        rel = Incident.__mapper__.relationships.get("owner")
        assert rel is not None
        assert rel.mapper.class_.__name__ == "User"

    def test_incident_creator_relationship(self):
        rel = Incident.__mapper__.relationships.get("creator")
        assert rel is not None
        assert rel.mapper.class_.__name__ == "User"


# ═══════════════════════════════════════════════════════════════════════════════
# IncidentIssue ORM Model
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentIssueModel:
    """Tests 7-9: IncidentIssue junction model structure."""

    def test_incident_issue_table_name(self):
        assert IncidentIssue.__tablename__ == "incident_issues"

    def test_incident_issue_composite_pk(self):
        pk_cols = {c.name for c in IncidentIssue.__table__.primary_key.columns}
        assert pk_cols == {"incident_id", "issue_id"}

    def test_incident_issue_incident_relationship(self):
        rel = IncidentIssue.__mapper__.relationships.get("incident")
        assert rel is not None
        assert rel.mapper.class_.__name__ == "Incident"


# ═══════════════════════════════════════════════════════════════════════════════
# CreateIncidentRequest Schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateIncidentRequest:
    """Tests 10-14: Pydantic request schema validation."""

    def test_create_request_valid(self):
        req = CreateIncidentRequest(
            title="Network outage affecting DQ scores",
            severity="critical",
            priority="P1",
            issue_ids=[uuid4(), uuid4()],
        )
        assert req.title == "Network outage affecting DQ scores"
        assert req.severity == "critical"
        assert req.priority == "P1"
        assert len(req.issue_ids) == 2

    def test_create_request_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            CreateIncidentRequest(
                title="   ",
                severity="major",
                priority="P2",
                issue_ids=[uuid4()],
            )

    def test_create_request_invalid_severity_rejected(self):
        with pytest.raises(ValidationError):
            CreateIncidentRequest(
                title="Test incident",
                severity="extreme",
                priority="P1",
                issue_ids=[uuid4()],
            )

    def test_create_request_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            CreateIncidentRequest(
                title="Test incident",
                severity="major",
                priority="P5",
                issue_ids=[uuid4()],
            )

    def test_create_request_empty_issue_ids_rejected(self):
        with pytest.raises(ValidationError):
            CreateIncidentRequest(
                title="Test incident",
                severity="major",
                priority="P2",
                issue_ids=[],
            )


# ═══════════════════════════════════════════════════════════════════════════════
# IncidentResponse Schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestIncidentResponse:
    """Test 15: Response schema has all expected fields."""

    def test_incident_response_fields(self):
        now = datetime.now(UTC)
        resp = IncidentResponse(
            id=uuid4(),
            workspace_id=uuid4(),
            title="Test",
            severity="major",
            priority="P2",
            status="open",
            impact_summary="Impact desc",
            owner_id=uuid4(),
            owner_name="Alice",
            created_by_user_id=uuid4(),
            created_by_name="Bob",
            issue_count=3,
            opened_at=now,
        )
        assert resp.status == "open"
        assert resp.issue_count == 3
        assert resp.owner_name == "Alice"
        assert resp.created_by_name == "Bob"
