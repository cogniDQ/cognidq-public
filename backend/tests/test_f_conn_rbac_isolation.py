"""
F-CONN-RBAC — Tenant isolation & projection-lockdown tests.

Implements spec §14.3 (RBAC Test Matrix). These tests verify that:

  * The catalog endpoint requires authentication.
  * Workspace data-source WRITE endpoints honour the
    ``WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY`` lockdown setting:
      - Default (False): legacy F004 RBAC unchanged.
      - True (production posture): only tenant admins for the workspace's
        tenant may write; everyone else gets 403 RBAC_FORBIDDEN.
  * Cross-tenant attempts are masked as 404 (no existence leak).
  * Read endpoints are NOT affected by the lockdown.
  * platform_admin always passes regardless of the flag.

Design notes
------------
We mount only the connector_catalog router for catalog tests, and only the
workspace_data_sources router for projection-lockdown tests. The DB session
is mocked per test using ``app.dependency_overrides``. We never touch a real
database — these are policy tests, not integration tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from app.api.v1.dependencies.data_source_auth import (
    DataSourceActorContext,
    verify_data_source_read_actor,
    verify_data_source_write_actor,
)
from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    get_actor_context,
)
from app.api.v1.endpoints import (
    connector_catalog as catalog_module,
)
from app.api.v1.endpoints import (
    workspace_data_sources as wds_module,
)
from app.core.config import settings
from app.models.database import get_db
from app.services.connections.errors import (
    RBAC_FORBIDDEN,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures — Tenants, actors, app factories
# ---------------------------------------------------------------------------

TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")
WORKSPACE_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _ds_actor(role: str, tenant_id: UUID) -> DataSourceActorContext:
    return DataSourceActorContext(
        actor_id=uuid4(),
        actor_role=role,
        tenant_id=tenant_id,
    )


def _tenant_actor(role: str, tenant_id: UUID) -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role=role,
        tenant_id=tenant_id,
    )


@contextmanager
def _lockdown(enabled: bool):
    """Toggle the F-CONN-RBAC lockdown setting for the duration of a test."""
    previous = getattr(settings, "WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY", False)
    settings.WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY = enabled
    try:
        yield
    finally:
        settings.WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY = previous


def _build_catalog_app(actor: ActorContext | None) -> FastAPI:
    app = FastAPI()
    app.include_router(catalog_module.router, prefix="/api/v1")
    if actor is not None:
        app.dependency_overrides[get_actor_context] = lambda: actor
    return app


def _build_wds_app(
    actor: DataSourceActorContext,
    *,
    workspace_tenant_id: UUID | None = TENANT_A,
    is_tenant_admin: bool = False,
) -> FastAPI:
    """Mount workspace_data_sources router and stub:
    * the write/read auth dependencies,
    * the DB session,
    * ``_is_tenant_admin`` (controls lockdown verdict),
    * the workspace lookup row inside the lockdown helper.
    """
    app = FastAPI()
    app.include_router(wds_module.router, prefix="/api/v1")

    app.dependency_overrides[verify_data_source_write_actor] = lambda: actor
    app.dependency_overrides[verify_data_source_read_actor] = lambda: actor

    fake_db = MagicMock(name="db_session")
    if workspace_tenant_id is None:
        fake_db.execute.return_value.fetchone.return_value = None
    else:
        fake_db.execute.return_value.fetchone.return_value = (workspace_tenant_id,)
    app.dependency_overrides[get_db] = lambda: fake_db

    return app


# ---------------------------------------------------------------------------
# Test 1 — Catalog endpoint requires authentication
# ---------------------------------------------------------------------------


def test_catalog_endpoint_requires_authentication():
    """No JWT, no catalog. The OpenAPI is public; the data is not."""
    from app.api.v1.dependencies.tenant_auth import (
        TenantAPIError,
        tenant_api_error_handler,
    )

    app = FastAPI()
    app.include_router(catalog_module.router, prefix="/api/v1")
    app.add_exception_handler(TenantAPIError, tenant_api_error_handler)
    # Do NOT override get_actor_context — let it run, which will reject
    # missing Authorization with 401.
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/connectors")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test 2 — Catalog endpoint succeeds for any authenticated tenant user
# ---------------------------------------------------------------------------


def test_catalog_endpoint_allows_any_authenticated_tenant_user():
    actor = _tenant_actor("business_analyst", TENANT_A)
    app = _build_catalog_app(actor)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/v1/connectors")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert body["total"] >= 1


# ---------------------------------------------------------------------------
# Test 3 — Default mode (lockdown OFF): non-tenant-admin write succeeds
# ---------------------------------------------------------------------------


def test_default_mode_allows_workspace_steward_to_write():
    """Backwards-compat: with the lockdown OFF, legacy F004 behaviour stands."""
    actor = _ds_actor("workspace_steward", TENANT_A)
    app = _build_wds_app(actor)

    # Stub out the service so we don't need a real DB.
    with (
        _lockdown(False),
        patch.object(wds_module._service, "_perform_connection_test") as mock_test,
    ):
        mock_test.return_value = {
            "status": "reachable",
            "tested_at": None,
            "error_summary": None,
        }
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_A}/data-sources/test-config",
            json={
                "type": "postgresql",
                "connection_config": {
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "password": "p",
                },
            },
        )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Test 4 — Lockdown ON: non-tenant-admin write rejected with RBAC_FORBIDDEN
# ---------------------------------------------------------------------------


def test_lockdown_blocks_non_tenant_admin_write():
    """With the lockdown active, a non-admin role hits 403 RBAC_FORBIDDEN."""
    actor = _ds_actor("workspace_steward", TENANT_A)
    app = _build_wds_app(actor, workspace_tenant_id=TENANT_A)

    with (
        _lockdown(True),
        patch(
            "app.api.v1.dependencies.tenant_auth._is_tenant_admin",
            return_value=False,
        ),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_A}/data-sources/test-config",
            json={
                "type": "postgresql",
                "connection_config": {
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "password": "p",
                },
            },
        )

    assert response.status_code == 403
    body = response.json()
    # FastAPI HTTPException nests the detail under "detail".
    detail = body.get("detail") or body
    inner = detail.get("error") if isinstance(detail, dict) else None
    assert inner is not None, body
    assert inner["code"] == RBAC_FORBIDDEN
    assert "tenant" in inner["message"].lower()


# ---------------------------------------------------------------------------
# Test 5 — Lockdown ON: tenant_admin write succeeds
# ---------------------------------------------------------------------------


def test_lockdown_allows_tenant_admin_write():
    """tenant_admin for the workspace's tenant always passes."""
    actor = _ds_actor("tenant_admin", TENANT_A)
    app = _build_wds_app(actor, workspace_tenant_id=TENANT_A)

    with (
        _lockdown(True),
        patch(
            "app.api.v1.dependencies.tenant_auth._is_tenant_admin",
            return_value=True,
        ),
        patch.object(wds_module._service, "_perform_connection_test") as mock_test,
    ):
        mock_test.return_value = {
            "status": "reachable",
            "tested_at": None,
            "error_summary": None,
        }
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_A}/data-sources/test-config",
            json={
                "type": "postgresql",
                "connection_config": {
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "password": "p",
                },
            },
        )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Test 6 — Lockdown ON: platform_admin write always succeeds
# ---------------------------------------------------------------------------


def test_lockdown_allows_platform_admin_write():
    actor = _ds_actor("platform_admin", TENANT_A)
    app = _build_wds_app(actor, workspace_tenant_id=TENANT_A)

    with (
        _lockdown(True),
        patch.object(wds_module._service, "_perform_connection_test") as mock_test,
    ):
        mock_test.return_value = {
            "status": "reachable",
            "tested_at": None,
            "error_summary": None,
        }
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_A}/data-sources/test-config",
            json={
                "type": "postgresql",
                "connection_config": {
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "password": "p",
                },
            },
        )
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Test 7 — Lockdown ON: cross-tenant attempt is masked as 404
# ---------------------------------------------------------------------------


def test_lockdown_cross_tenant_attempt_is_404():
    """Tenant-A admin pointing at a workspace owned by Tenant-B → 404."""
    actor = _ds_actor("tenant_admin", TENANT_A)
    app = _build_wds_app(actor, workspace_tenant_id=TENANT_B)

    with _lockdown(True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_B}/data-sources/test-config",
            json={
                "type": "postgresql",
                "connection_config": {
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "password": "p",
                },
            },
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 8 — Lockdown ON: missing workspace returns 404 (no leak)
# ---------------------------------------------------------------------------


def test_lockdown_missing_workspace_is_404():
    actor = _ds_actor("tenant_admin", TENANT_A)
    app = _build_wds_app(actor, workspace_tenant_id=None)  # row=None

    with _lockdown(True):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/api/v1/workspaces/{WORKSPACE_A}/data-sources/test-config",
            json={
                "type": "postgresql",
                "connection_config": {
                    "host": "h",
                    "port": 5432,
                    "database": "d",
                    "username": "u",
                    "password": "p",
                },
            },
        )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test 9 — Lockdown ON: read endpoints are unaffected
# ---------------------------------------------------------------------------


def test_lockdown_does_not_affect_read_endpoints():
    """The lockdown is write-only; viewers still see data sources."""
    actor = _ds_actor("workspace_viewer", TENANT_A)
    app = _build_wds_app(actor, workspace_tenant_id=TENANT_A)

    with _lockdown(True), patch.object(wds_module._service, "list_sources", return_value=([], 0)):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/api/v1/workspaces/{WORKSPACE_A}/data-sources",
        )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0


# ---------------------------------------------------------------------------
# Test 10 — Lockdown helper is idempotent / pure (defensive)
# ---------------------------------------------------------------------------


def test_lockdown_helper_is_noop_when_disabled():
    """Direct call: with the flag off, the helper short-circuits with no DB call."""
    from app.api.v1.dependencies.data_source_auth import (
        enforce_data_source_tenant_admin_lockdown,
    )

    db = MagicMock(name="db")
    actor = _ds_actor("workspace_viewer", TENANT_A)

    with _lockdown(False):
        # Should not raise, should not query the DB.
        enforce_data_source_tenant_admin_lockdown(WORKSPACE_A, actor, db)

    db.execute.assert_not_called()
