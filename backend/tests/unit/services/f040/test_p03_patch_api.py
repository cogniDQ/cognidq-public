"""
F040 P03 — PATCH API Endpoint Tests (15 tests)
================================================

Covers:
  - PATCH /workspaces/{ws}/incidents/{id} endpoint behaviour
  - Error mapping, response fields
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.incidents.incident_lifecycle_service import (
    EmptyUpdateError,
    IncidentNotFoundError,
    InvalidStatusTransitionError,
    ResolutionSummaryRequiredError,
)
from app.services.incidents.incident_models import IncidentResponse
from fastapi import HTTPException

INCIDENTS_EP = "app.api.v1.endpoints.incidents"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_INC_ID = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.actor_id = _USER
    actor.actor_role = "admin"
    return actor


def _mock_response(**overrides):
    defaults = dict(
        id=_INC_ID,
        workspace_id=_WS,
        title="DQ Pipeline Outage",
        severity="critical",
        priority="P1",
        status="acknowledged",
        impact_summary="Multiple pipelines affected",
        resolution_summary=None,
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
    body.status = overrides.get("status", "acknowledged")
    body.owner_id = overrides.get("owner_id", None)
    body.impact_summary = overrides.get("impact_summary", None)
    body.resolution_summary = overrides.get("resolution_summary", None)
    body.model_fields_set = overrides.get("model_fields_set", {"status"})
    return body


async def _call_patch(lifecycle_mock, body=None, resp=None, side_effect=None):
    from app.api.v1.endpoints.incidents import update_incident

    if side_effect:
        lifecycle_mock.update_incident.side_effect = side_effect
    elif resp:
        lifecycle_mock.update_incident.return_value = resp
    else:
        lifecycle_mock.update_incident.return_value = _mock_response()

    return await update_incident(
        workspace_id=_WS,
        incident_id=_INC_ID,
        body=body or _mock_body(),
        actor=_mock_actor(),
        db=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Success Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatchSuccess:
    """Tests 1-5: Successful PATCH response fields."""

    @pytest.mark.asyncio
    async def test_patch_returns_200(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_patch_response_has_status(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_patch_response_has_title(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["title"] == "DQ Pipeline Outage"

    @pytest.mark.asyncio
    async def test_patch_response_has_severity(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_patch_response_has_owner_name(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["owner_name"] == "Alice"


# ═══════════════════════════════════════════════════════════════════════════════
# Error Cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatchErrors:
    """Tests 6-9: Error mapping to HTTP codes."""

    @pytest.mark.asyncio
    async def test_patch_not_found_404(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_patch(mock, side_effect=IncidentNotFoundError("Not found"))
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_invalid_transition_409(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_patch(mock, side_effect=InvalidStatusTransitionError("Bad transition"))
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_patch_missing_summary_422(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_patch(mock, side_effect=ResolutionSummaryRequiredError("Required"))
            assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_empty_update_422(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_patch(mock, side_effect=EmptyUpdateError("No fields"))
            assert exc_info.value.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════════
# Integration & Extra Fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestPatchIntegration:
    """Tests 10-15: Service delegation and extra response fields."""

    @pytest.mark.asyncio
    async def test_patch_calls_lifecycle_service(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            mock.update_incident.return_value = _mock_response()
            await _call_patch(mock)
        mock.update_incident.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_response_has_priority(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["priority"] == "P1"

    @pytest.mark.asyncio
    async def test_patch_response_has_impact_summary(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["impact_summary"] == "Multiple pipelines affected"

    @pytest.mark.asyncio
    async def test_patch_response_has_opened_at(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert "opened_at" in data

    @pytest.mark.asyncio
    async def test_patch_response_has_issue_count(self):
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock)
        data = json.loads(result.body)
        assert data["issue_count"] == 2

    @pytest.mark.asyncio
    async def test_patch_response_has_resolution_summary(self):
        resp = _mock_response(resolution_summary="Root cause found")
        with patch(f"{INCIDENTS_EP}._lifecycle_svc") as mock:
            result = await _call_patch(mock, resp=resp)
        data = json.loads(result.body)
        assert data["resolution_summary"] == "Root cause found"
