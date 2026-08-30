"""
F038 P03 — API Endpoint Tests (15 tests)
==========================================

Covers:
  - POST /workspaces/{ws}/incidents endpoint behaviour
  - Request validation, error handling, response fields
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.incidents.incident_models import IncidentResponse
from app.services.incidents.incident_service import (
    IncidentValidationError,
    IssueNotFoundError,
)
from fastapi import HTTPException

INCIDENTS_EP = "app.api.v1.endpoints.incidents"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_ISSUE_1 = uuid4()
_ISSUE_2 = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.actor_id = _USER
    actor.actor_role = "admin"
    return actor


def _mock_response(**overrides):
    defaults = dict(
        id=uuid4(),
        workspace_id=_WS,
        title="DQ Pipeline Outage",
        severity="critical",
        priority="P1",
        status="open",
        impact_summary="Multiple pipelines affected",
        owner_id=uuid4(),
        owner_name="Alice",
        created_by_user_id=_USER,
        created_by_name="Bob",
        issue_count=2,
        opened_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return IncidentResponse(**defaults)


def _mock_body(**overrides):
    body = MagicMock()
    body.title = overrides.get("title", "DQ Pipeline Outage")
    body.severity = overrides.get("severity", "critical")
    body.priority = overrides.get("priority", "P1")
    body.impact_summary = overrides.get("impact_summary", "Impact desc")
    body.owner_id = overrides.get("owner_id", uuid4())
    body.issue_ids = overrides.get("issue_ids", [_ISSUE_1, _ISSUE_2])
    return body


async def _call_endpoint(svc_mock, body=None, resp=None, side_effect=None):
    """Import and call the create_incident endpoint with mocked service."""
    from app.api.v1.endpoints.incidents import create_incident

    if side_effect:
        svc_mock.create_incident.side_effect = side_effect
    elif resp:
        svc_mock.create_incident.return_value = resp
    else:
        svc_mock.create_incident.return_value = _mock_response()

    return await create_incident(
        workspace_id=_WS,
        body=body or _mock_body(),
        actor=_mock_actor(),
        db=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Success Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateIncidentSuccess:
    """Tests 1-6: Successful creation response fields."""

    @pytest.mark.asyncio
    async def test_create_incident_returns_201(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_create_incident_response_has_id(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert "id" in data
        assert len(data["id"]) == 36  # UUID string

    @pytest.mark.asyncio
    async def test_create_incident_response_has_title(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert data["title"] == "DQ Pipeline Outage"

    @pytest.mark.asyncio
    async def test_create_incident_response_has_status_open(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert data["status"] == "open"

    @pytest.mark.asyncio
    async def test_create_incident_response_has_issue_count(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert data["issue_count"] == 2

    @pytest.mark.asyncio
    async def test_create_incident_response_has_owner_name(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert data["owner_name"] == "Alice"


# ═══════════════════════════════════════════════════════════════════════════════
# Validation / Error Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateIncidentErrors:
    """Tests 7-11: Error handling."""

    @pytest.mark.asyncio
    async def test_create_incident_empty_title_422(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            with pytest.raises(HTTPException) as exc_info:
                await _call_endpoint(
                    mock_svc,
                    side_effect=IncidentValidationError("title must be 1–500 characters"),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_incident_invalid_severity_422(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            with pytest.raises(HTTPException) as exc_info:
                await _call_endpoint(
                    mock_svc,
                    side_effect=IncidentValidationError("invalid severity"),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_incident_invalid_priority_422(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            with pytest.raises(HTTPException) as exc_info:
                await _call_endpoint(
                    mock_svc,
                    side_effect=IncidentValidationError("invalid priority"),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_incident_empty_issues_422(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            with pytest.raises(HTTPException) as exc_info:
                await _call_endpoint(
                    mock_svc,
                    side_effect=IncidentValidationError(
                        "issue_ids must contain at least one issue"
                    ),
                )
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_create_incident_issue_not_found_404(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            with pytest.raises(HTTPException) as exc_info:
                await _call_endpoint(
                    mock_svc,
                    side_effect=IssueNotFoundError("Issues not found"),
                )
            assert exc_info.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateIncidentIntegration:
    """Tests 12-15: Service delegation and extra response fields."""

    @pytest.mark.asyncio
    async def test_create_incident_calls_service(self):
        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            mock_svc.create_incident.return_value = _mock_response()
            await _call_endpoint(mock_svc)
        mock_svc.create_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_incident_response_has_severity(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert data["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_create_incident_response_has_priority(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert data["priority"] == "P1"

    @pytest.mark.asyncio
    async def test_create_incident_response_has_opened_at(self):
        import json

        with patch(f"{INCIDENTS_EP}._svc") as mock_svc:
            result = await _call_endpoint(mock_svc)
        data = json.loads(result.body)
        assert "opened_at" in data
        assert len(data["opened_at"]) > 10  # ISO format
