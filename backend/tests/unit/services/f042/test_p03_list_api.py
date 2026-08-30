"""
F042 P03 — GET List API Endpoint Tests (15 tests)
====================================================

Covers:
  - GET /workspaces/{ws}/incidents — pagination, filters, response fields
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.incidents.incident_models import (
    IncidentListItem,
    IncidentPage,
)

INCIDENTS_EP = "app.api.v1.endpoints.incidents"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_INC = uuid4()
_NOW = datetime.now(UTC)


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.actor_id = _USER
    actor.actor_role = "admin"
    return actor


def _mock_list_item(**overrides):
    defaults = dict(
        id=_INC,
        title="Pipeline Failure",
        severity="critical",
        priority="P1",
        status="open",
        impact_summary="Multiple pipelines down",
        owner_id=uuid4(),
        owner_name="Alice",
        created_by_name="Bob",
        issue_count=5,
        has_sla_breach=True,
        earliest_due_at=_NOW,
        opened_at=_NOW,
        acknowledged_at=None,
        resolved_at=None,
        closed_at=None,
    )
    defaults.update(overrides)
    return IncidentListItem(**defaults)


def _mock_page(items=None, total=None, has_next=False):
    items = items if items is not None else [_mock_list_item()]
    return IncidentPage(
        items=items,
        total=total if total is not None else len(items),
        page=1,
        page_size=50,
        has_next=has_next,
    )


async def _call_list(
    list_svc_mock,
    page=1,
    page_size=50,
    status_filter=None,
    severity=None,
    priority=None,
    owner_id=None,
    resp=None,
):
    from app.api.v1.endpoints.incidents import list_incidents

    list_svc_mock.list_incidents.return_value = resp or _mock_page()

    return await list_incidents(
        workspace_id=_WS,
        actor=_mock_actor(),
        db=MagicMock(),
        page=page,
        page_size=page_size,
        status_filter=status_filter,
        severity=severity,
        priority=priority,
        owner_id=owner_id,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Success + Response Structure
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetList:
    """Tests 1-10: Response fields."""

    @pytest.mark.asyncio
    async def test_get_returns_200(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_get_response_has_items(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert "items" in data
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_get_response_has_total(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_get_response_has_page(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_get_response_has_page_size(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["page_size"] == 50

    @pytest.mark.asyncio
    async def test_get_response_has_next(self):
        resp = _mock_page(has_next=True, total=100)
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock, resp=resp)
        data = json.loads(result.body)
        assert data["has_next"] is True

    @pytest.mark.asyncio
    async def test_get_item_has_title(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["items"][0]["title"] == "Pipeline Failure"

    @pytest.mark.asyncio
    async def test_get_item_has_status(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["items"][0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_get_item_has_sla_breach(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["items"][0]["has_sla_breach"] is True

    @pytest.mark.asyncio
    async def test_get_item_has_issue_count(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert data["items"][0]["issue_count"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Service Delegation + Filtering + Edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetDelegation:
    """Tests 11-15: Service delegation, defaults, filters, empty, timestamp."""

    @pytest.mark.asyncio
    async def test_get_calls_service(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            mock.list_incidents.return_value = _mock_page()
            await _call_list(mock)
        mock.list_incidents.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_default_pagination(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            mock.list_incidents.return_value = _mock_page()
            await _call_list(mock)
        kwargs = mock.list_incidents.call_args.kwargs
        assert kwargs["page"] == 1
        assert kwargs["page_size"] == 50

    @pytest.mark.asyncio
    async def test_get_passes_filters(self):
        owner = uuid4()
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            mock.list_incidents.return_value = _mock_page()
            await _call_list(
                mock, status_filter="open", severity="critical", priority="P1", owner_id=owner
            )
        kwargs = mock.list_incidents.call_args.kwargs
        assert kwargs["status"] == "open"
        assert kwargs["severity"] == "critical"
        assert kwargs["priority"] == "P1"
        assert kwargs["owner_id"] == owner

    @pytest.mark.asyncio
    async def test_get_empty_list(self):
        resp = _mock_page(items=[], total=0)
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock, resp=resp)
        data = json.loads(result.body)
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_item_has_opened_at(self):
        with patch(f"{INCIDENTS_EP}._list_svc") as mock:
            result = await _call_list(mock)
        data = json.loads(result.body)
        assert "opened_at" in data["items"][0]
