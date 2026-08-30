"""
F130 P02 — Tenant Connection API Tests
========================================
20 tests covering:
  - Schemas / domain models
  - Error codes
  - Repository logic (mocked DB)
  - Service delegation
  - Endpoint router wiring
  - Auth dependencies
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ──────────────────────────────────────────────────────────────────────────────

TENANT_ID = uuid4()
CONNECTION_ID = uuid4()
WORKSPACE_ID = uuid4()
ACTOR_ID = uuid4()


def _make_connection_row(
    tenant_id: UUID = TENANT_ID,
    data_source_id: UUID = CONNECTION_ID,
    source_name: str = "prod-db",
    source_type: str = "postgresql",
    status: str = "active",
) -> dict:
    return {
        "data_source_id": data_source_id,
        "tenant_id": tenant_id,
        "workspace_id": WORKSPACE_ID,
        "source_name": source_name,
        "source_type": source_type,
        "connection_mode": "direct",
        "environment": "production",
        "description": "Main production DB",
        "status": status,
        "credential_reference": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "created_by": ACTOR_ID,
        "updated_by": ACTOR_ID,
    }


def _make_assignment_row(
    connection_id: UUID = CONNECTION_ID,
    workspace_id: UUID = WORKSPACE_ID,
) -> dict:
    return {
        "connection_id": connection_id,
        "workspace_id": workspace_id,
        "assigned_at": datetime.now(UTC),
        "assigned_by": ACTOR_ID,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. Domain model tests
# ──────────────────────────────────────────────────────────────────────────────


class TestConnectionModels:
    def test_connection_dataclass_import(self):
        from app.services.connections.models import Connection

        assert Connection is not None

    def test_workspace_assignment_dataclass_import(self):
        from app.services.connections.models import WorkspaceAssignment

        assert WorkspaceAssignment is not None

    def test_connection_dataclass_fields(self):
        import dataclasses

        from app.services.connections.models import Connection

        field_names = {f.name for f in dataclasses.fields(Connection)}
        assert "data_source_id" in field_names
        assert "tenant_id" in field_names
        assert "source_name" in field_names
        assert "source_type" in field_names
        assert "status" in field_names

    def test_workspace_assignment_dataclass_fields(self):
        import dataclasses

        from app.services.connections.models import WorkspaceAssignment

        field_names = {f.name for f in dataclasses.fields(WorkspaceAssignment)}
        assert "connection_id" in field_names
        assert "workspace_id" in field_names
        assert "assigned_at" in field_names


# ──────────────────────────────────────────────────────────────────────────────
# 2. Error codes
# ──────────────────────────────────────────────────────────────────────────────


class TestConnectionErrors:
    def test_error_codes_exported(self):
        from app.services.connections import errors

        assert errors.CONNECTION_NOT_FOUND == "CONNECTION_NOT_FOUND"
        assert errors.CONNECTION_IN_USE == "CONNECTION_IN_USE"
        assert errors.DUPLICATE_CONNECTION_NAME == "DUPLICATE_CONNECTION_NAME"
        assert errors.IMMUTABLE_FIELD == "IMMUTABLE_FIELD"

    def test_connection_api_error_structure(self):
        from app.services.connections.errors import ConnectionAPIError

        exc = ConnectionAPIError(
            status_code=404,
            code="CONNECTION_NOT_FOUND",
            message="Not found.",
            fields=["connection_id"],
        )
        assert exc.status_code == 404
        assert exc.code == "CONNECTION_NOT_FOUND"
        assert exc.fields == ["connection_id"]

    def test_connection_api_error_is_exception(self):
        from app.services.connections.errors import ConnectionAPIError

        exc = ConnectionAPIError(500, "ERR", "msg")
        assert isinstance(exc, Exception)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Repository tests (mocked DB)
# ──────────────────────────────────────────────────────────────────────────────


class TestTenantConnectionRepository:
    def _make_mock_db(self, rows=None, scalar=None):
        """Build a minimal mock SQLAlchemy Session."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows or []
        mock_result.fetchone.return_value = scalar

        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result
        return mock_db

    def test_list_by_tenant_empty(self):
        from app.services.connections.repository import TenantConnectionRepository

        repo = TenantConnectionRepository()

        mock_result_count = MagicMock()
        mock_result_count.fetchone.return_value = (0,)
        mock_result_rows = MagicMock()
        mock_result_rows.fetchall.return_value = []

        mock_db = MagicMock()
        mock_db.execute.side_effect = [mock_result_count, mock_result_rows]

        items, total = repo.list_by_tenant(mock_db, TENANT_ID)
        assert total == 0
        assert items == []

    def test_get_by_tenant_returns_none_when_missing(self):
        from app.services.connections.repository import TenantConnectionRepository

        repo = TenantConnectionRepository()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        result = repo.get_by_tenant(mock_db, TENANT_ID, CONNECTION_ID)
        assert result is None

    def test_immutable_field_raises_on_update(self):
        from app.services.connections.errors import IMMUTABLE_FIELD, ConnectionAPIError
        from app.services.connections.repository import TenantConnectionRepository

        repo = TenantConnectionRepository()

        with pytest.raises(ConnectionAPIError) as exc_info:
            repo.update(MagicMock(), TENANT_ID, CONNECTION_ID, {"source_type": "mysql"}, ACTOR_ID)

        assert exc_info.value.code == IMMUTABLE_FIELD
        assert exc_info.value.status_code == 400

    def test_immutable_field_connection_mode_raises(self):
        from app.services.connections.errors import IMMUTABLE_FIELD, ConnectionAPIError
        from app.services.connections.repository import TenantConnectionRepository

        repo = TenantConnectionRepository()

        with pytest.raises(ConnectionAPIError) as exc_info:
            repo.update(
                MagicMock(), TENANT_ID, CONNECTION_ID, {"connection_mode": "agent"}, ACTOR_ID
            )

        assert exc_info.value.code == IMMUTABLE_FIELD

    def test_delete_raises_not_found_when_missing(self):
        from app.services.connections.errors import CONNECTION_NOT_FOUND, ConnectionAPIError
        from app.services.connections.repository import TenantConnectionRepository

        repo = TenantConnectionRepository()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(ConnectionAPIError) as exc_info:
            repo.delete(mock_db, TENANT_ID, CONNECTION_ID)

        assert exc_info.value.code == CONNECTION_NOT_FOUND
        assert exc_info.value.status_code == 404

    def test_get_assignments_returns_list(self):
        from app.services.connections.repository import TenantConnectionRepository

        repo = TenantConnectionRepository()

        row = MagicMock()
        row._mapping = _make_assignment_row()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [row]
        mock_db = MagicMock()
        mock_db.execute.return_value = mock_result

        assignments = repo.get_assignments(mock_db, CONNECTION_ID)
        assert len(assignments) == 1
        assert "connection_id" in assignments[0]


# ──────────────────────────────────────────────────────────────────────────────
# 4. Service tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTenantConnectionService:
    def test_service_import(self):
        from app.services.connections.service import TenantConnectionService

        assert TenantConnectionService is not None

    def test_service_instantiation(self):
        from app.services.connections.service import TenantConnectionService

        svc = TenantConnectionService()
        assert hasattr(svc, "list_connections")
        assert hasattr(svc, "get_connection")
        assert hasattr(svc, "create_connection")
        assert hasattr(svc, "update_connection")
        assert hasattr(svc, "delete_connection")
        assert hasattr(svc, "get_workspace_assignments")
        assert hasattr(svc, "replace_workspace_assignments")

    def test_service_list_delegates_to_repo(self):
        from app.services.connections.service import TenantConnectionService

        svc = TenantConnectionService()

        with patch("app.services.connections.service._repo") as mock_repo:
            mock_repo.list_by_tenant.return_value = ([], 0)
            items, total = svc.list_connections(MagicMock(), TENANT_ID)

        assert total == 0
        mock_repo.list_by_tenant.assert_called_once()

    def test_service_get_delegates_to_repo(self):
        from app.services.connections.service import TenantConnectionService

        svc = TenantConnectionService()

        with patch("app.services.connections.service._repo") as mock_repo:
            mock_repo.get_by_tenant.return_value = None
            result = svc.get_connection(MagicMock(), TENANT_ID, CONNECTION_ID)

        assert result is None
        mock_repo.get_by_tenant.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# 5. Endpoint router tests
# ──────────────────────────────────────────────────────────────────────────────


class TestTenantConnectionsEndpoints:
    def test_router_import(self):
        from app.api.v1.endpoints.tenant_connections import router

        assert router is not None

    def test_router_prefix(self):
        from app.api.v1.endpoints.tenant_connections import router

        assert "/tenants" in router.prefix
        assert "connections" in router.prefix

    def test_router_registered_in_main_router(self):
        """Verify router.py imports tenant_connections and includes its router."""
        import ast
        import os

        router_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "app",
            "api",
            "v1",
            "router.py",
        )
        with open(router_path, encoding="utf-8") as f:
            source = f.read()

        assert "tenant_connections" in source, (
            "tenant_connections not found in router.py import or include_router calls"
        )
        assert "tenant_connections.router" in source, (
            "api_router.include_router(tenant_connections.router) not found in router.py"
        )

    def test_list_endpoint_exists(self):
        from app.api.v1.endpoints.tenant_connections import router

        get_routes = [r for r in router.routes if hasattr(r, "methods") and "GET" in r.methods]
        assert len(get_routes) >= 1

    def test_post_endpoint_exists(self):
        from app.api.v1.endpoints.tenant_connections import router

        post_routes = [r for r in router.routes if hasattr(r, "methods") and "POST" in r.methods]
        assert len(post_routes) >= 1

    def test_delete_endpoint_exists(self):
        from app.api.v1.endpoints.tenant_connections import router

        delete_routes = [
            r for r in router.routes if hasattr(r, "methods") and "DELETE" in r.methods
        ]
        assert len(delete_routes) >= 1

    def test_put_workspaces_endpoint_exists(self):
        from app.api.v1.endpoints.tenant_connections import router

        put_routes = [r for r in router.routes if hasattr(r, "methods") and "PUT" in r.methods]
        assert len(put_routes) >= 1

    def test_service_instance_on_module(self):
        from app.api.v1.endpoints.tenant_connections import _service
        from app.services.connections.service import TenantConnectionService

        assert isinstance(_service, TenantConnectionService)
