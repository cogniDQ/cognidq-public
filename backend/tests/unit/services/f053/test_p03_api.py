"""
F053 P03 — API Endpoint Tests (15 tests)
==========================================

Covers: list_audit_logs and export_audit_logs endpoints via direct async calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.services.audit.search_models import AuditLogEntry, AuditLogPage
from app.services.audit.search_service import AuditLogSearchService

_TENANT = uuid4()
_WS = uuid4()
_ACTOR_ID = uuid4()
_NOW = datetime.now(UTC)


def _mock_actor():
    actor = MagicMock()
    actor.tenant_id = _TENANT
    actor.actor_id = _ACTOR_ID
    return actor


def _db():
    return MagicMock()


def _request():
    r = MagicMock()
    r.state = MagicMock()
    r.state.request_id = "test-req"
    return r


def _sample_entry(**overrides):
    base = dict(
        log_id=uuid4(),
        occurred_at=_NOW,
        action_type="tenant_created",
        actor_id=_ACTOR_ID,
        actor_role="admin",
        actor_type="user",
        actor_display_name="Test User",
        target_entity_type="tenant",
        target_entity_id=uuid4(),
        workspace_id=_WS,
        request_id="req-001",
    )
    base.update(overrides)
    return AuditLogEntry(**base)


def _sample_page(items=None, total=0, page=1, page_size=50, has_next=False):
    return AuditLogPage(
        items=items or [],
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
    )


# ── list_audit_logs tests ───────────────────────────────────────────────────


class TestListAuditLogs:
    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_returns_200(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import list_audit_logs

        mock_svc.get_page.return_value = _sample_page()
        resp = await list_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            sort_dir="desc",
            page=1,
            page_size=50,
            db=_db(),
            actor=_mock_actor(),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_pagination_metadata(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import list_audit_logs

        mock_svc.get_page.return_value = _sample_page(
            total=100, page=2, page_size=25, has_next=True
        )
        resp = await list_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            sort_dir="desc",
            page=2,
            page_size=25,
            db=_db(),
            actor=_mock_actor(),
        )
        import json

        body = json.loads(resp.body.decode())
        assert body["total"] == 100
        assert body["page"] == 2
        assert body["has_next"] is True

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_service_called_with_filters(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import list_audit_logs

        mock_svc.get_page.return_value = _sample_page()
        await list_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type="tenant_created",
            entity_type="tenant",
            actor_id=None,
            from_date=None,
            to_date=None,
            sort_dir="asc",
            page=1,
            page_size=50,
            db=_db(),
            actor=_mock_actor(),
        )
        call_args = mock_svc.get_page.call_args
        filters = call_args[0][3]  # 4th positional arg
        assert filters.action_type == "tenant_created"
        assert filters.entity_type == "tenant"
        assert filters.sort_dir == "asc"

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_invalid_action_type_returns_400(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import list_audit_logs

        resp = await list_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type="INVALID_BOGUS",
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            sort_dir="desc",
            page=1,
            page_size=50,
            db=_db(),
            actor=_mock_actor(),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_invalid_entity_type_returns_400(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import list_audit_logs

        resp = await list_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type="INVALID_BOGUS",
            actor_id=None,
            from_date=None,
            to_date=None,
            sort_dir="desc",
            page=1,
            page_size=50,
            db=_db(),
            actor=_mock_actor(),
        )
        assert resp.status_code == 400


# ── export_audit_logs tests ──────────────────────────────────────────────────


class TestExportAuditLogs:
    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_returns_csv_content_type(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import export_audit_logs

        mock_svc.build_export_rows.return_value = []
        mock_svc.export_columns.return_value = ["log_id"]
        resp = await export_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            db=_db(),
            actor=_mock_actor(),
        )
        assert resp.media_type == "text/csv; charset=utf-8-sig"

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_csv_has_bom(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import export_audit_logs

        mock_svc.build_export_rows.return_value = []
        mock_svc.export_columns.return_value = ["log_id"]
        resp = await export_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            db=_db(),
            actor=_mock_actor(),
        )
        assert resp.body[:3] == b"\xef\xbb\xbf"

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_csv_filename_in_headers(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import export_audit_logs

        mock_svc.build_export_rows.return_value = []
        mock_svc.export_columns.return_value = ["log_id"]
        resp = await export_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            db=_db(),
            actor=_mock_actor(),
        )
        disp = resp.headers.get("content-disposition", "")
        assert "audit_logs_" in disp
        assert ".csv" in disp

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_export_with_rows(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import export_audit_logs

        mock_svc.build_export_rows.return_value = [{"log_id": "1", "action_type": "tenant_created"}]
        mock_svc.export_columns.return_value = ["log_id", "action_type"]
        resp = await export_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type=None,
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            db=_db(),
            actor=_mock_actor(),
        )
        body = resp.body.decode("utf-8-sig")
        assert "tenant_created" in body

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_export_invalid_action_type_returns_400(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import export_audit_logs

        resp = await export_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type="BOGUS",
            entity_type=None,
            actor_id=None,
            from_date=None,
            to_date=None,
            db=_db(),
            actor=_mock_actor(),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch("app.api.v1.endpoints.audit_logs._svc")
    async def test_service_receives_filters(self, mock_svc):
        from app.api.v1.endpoints.audit_logs import export_audit_logs

        mock_svc.build_export_rows.return_value = []
        mock_svc.export_columns.return_value = ["log_id"]
        await export_audit_logs(
            request=_request(),
            workspace_id=_WS,
            action_type="tenant_created",
            entity_type="tenant",
            actor_id=None,
            from_date=None,
            to_date=None,
            db=_db(),
            actor=_mock_actor(),
        )
        call_args = mock_svc.build_export_rows.call_args
        filters = call_args[0][3]  # 4th positional arg
        assert filters.action_type == "tenant_created"
        assert filters.entity_type == "tenant"


# ── Wiring test ──────────────────────────────────────────────────────────────


class TestServiceWiring:
    def test_module_level_service_exists(self):
        from app.api.v1.endpoints import audit_logs

        assert hasattr(audit_logs, "_svc")
        assert isinstance(audit_logs._svc, AuditLogSearchService)

    def test_router_registered(self):
        from app.api.v1.router import api_router

        paths = [r.path for r in api_router.routes]
        assert any("/audit/logs" in p for p in paths)
