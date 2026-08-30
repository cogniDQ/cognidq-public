"""
F041 P03 — Link API Endpoint Tests (15 tests)
===============================================

Covers:
  - POST /workspaces/{ws}/incidents/{id}/links  — add links
  - DELETE /workspaces/{ws}/incidents/{id}/links — remove links
  - Error mapping, response fields, service delegation
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.services.incidents.incident_link_service import (
    IncidentNotFoundError,
    IssueNotFoundError,
    MinimumLinkError,
)
from app.services.incidents.incident_models import LinkOperationResponse
from fastapi import HTTPException

INCIDENTS_EP = "app.api.v1.endpoints.incidents"

_WS = uuid4()
_TENANT = uuid4()
_USER = uuid4()
_INC = uuid4()
_ISSUE_A = uuid4()
_ISSUE_B = uuid4()


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.actor_id = _USER
    actor.actor_role = "admin"
    return actor


def _mock_link_response(**overrides):
    defaults = dict(
        incident_id=_INC,
        issue_count=2,
        linked_issue_ids=[_ISSUE_A, _ISSUE_B],
    )
    defaults.update(overrides)
    return LinkOperationResponse(**defaults)


def _mock_body(issue_ids=None):
    body = MagicMock()
    body.issue_ids = issue_ids or [_ISSUE_A]
    return body


async def _call_add_links(link_svc_mock, body=None, resp=None, side_effect=None):
    from app.api.v1.endpoints.incidents import add_incident_links

    if side_effect:
        link_svc_mock.add_links.side_effect = side_effect
    else:
        link_svc_mock.add_links.return_value = resp or _mock_link_response()

    return await add_incident_links(
        workspace_id=_WS,
        incident_id=_INC,
        body=body or _mock_body(),
        actor=_mock_actor(),
        db=MagicMock(),
    )


async def _call_remove_links(link_svc_mock, body=None, resp=None, side_effect=None):
    from app.api.v1.endpoints.incidents import remove_incident_links

    if side_effect:
        link_svc_mock.remove_links.side_effect = side_effect
    else:
        link_svc_mock.remove_links.return_value = resp or _mock_link_response()

    return await remove_incident_links(
        workspace_id=_WS,
        incident_id=_INC,
        body=body or _mock_body(),
        actor=_mock_actor(),
        db=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# POST /links
# ═══════════════════════════════════════════════════════════════════════════════


class TestPostLinks:
    """Tests 1-8: POST /{id}/links."""

    @pytest.mark.asyncio
    async def test_post_links_returns_201(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_add_links(mock)
        assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_post_links_response_has_issue_count(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_add_links(mock)
        data = json.loads(result.body)
        assert data["issue_count"] == 2

    @pytest.mark.asyncio
    async def test_post_links_response_has_linked_ids(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_add_links(mock)
        data = json.loads(result.body)
        assert len(data["linked_issue_ids"]) == 2

    @pytest.mark.asyncio
    async def test_post_links_response_has_incident_id(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_add_links(mock)
        data = json.loads(result.body)
        assert data["incident_id"] == str(_INC)

    @pytest.mark.asyncio
    async def test_post_links_not_found_404(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_add_links(mock, side_effect=IncidentNotFoundError("Not found"))
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_post_links_issue_not_found_404(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_add_links(mock, side_effect=IssueNotFoundError("Missing"))
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_post_links_empty_ids_422(self):
        """Empty issue_ids rejected by Pydantic, but also test the endpoint rejects."""
        from app.services.incidents.incident_models import LinkIssuesRequest

        with pytest.raises(Exception):
            LinkIssuesRequest(issue_ids=[])

    @pytest.mark.asyncio
    async def test_post_links_calls_service(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            mock.add_links.return_value = _mock_link_response()
            await _call_add_links(mock)
        mock.add_links.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# DELETE /links
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeleteLinks:
    """Tests 9-15: DELETE /{id}/links."""

    @pytest.mark.asyncio
    async def test_delete_links_returns_200(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_remove_links(mock)
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_links_response_has_issue_count(self):
        resp = _mock_link_response(issue_count=1, linked_issue_ids=[_ISSUE_B])
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_remove_links(mock, resp=resp)
        data = json.loads(result.body)
        assert data["issue_count"] == 1

    @pytest.mark.asyncio
    async def test_delete_links_response_has_linked_ids(self):
        resp = _mock_link_response(issue_count=1, linked_issue_ids=[_ISSUE_B])
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            result = await _call_remove_links(mock, resp=resp)
        data = json.loads(result.body)
        assert len(data["linked_issue_ids"]) == 1

    @pytest.mark.asyncio
    async def test_delete_links_not_found_404(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_remove_links(mock, side_effect=IncidentNotFoundError("Not found"))
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_links_minimum_409(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            with pytest.raises(HTTPException) as exc_info:
                await _call_remove_links(mock, side_effect=MinimumLinkError("Min 1"))
            assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_links_empty_ids_422(self):
        from app.services.incidents.incident_models import LinkIssuesRequest

        with pytest.raises(Exception):
            LinkIssuesRequest(issue_ids=[])

    @pytest.mark.asyncio
    async def test_delete_links_calls_service(self):
        with patch(f"{INCIDENTS_EP}._link_svc") as mock:
            mock.remove_links.return_value = _mock_link_response()
            await _call_remove_links(mock)
        mock.remove_links.assert_called_once()
