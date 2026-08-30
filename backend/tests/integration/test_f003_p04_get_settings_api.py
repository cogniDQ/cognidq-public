"""
Integration tests — F003 Packet 4: GET /api/v1/workspaces/{id}/settings

Tests run inside Docker against the real PostgreSQL database.
A DB trigger (trg_workspace_settings_on_insert) automatically creates a
workspace_settings row for every workspace INSERT, so all tests can rely on
the row existing without separate setup.

Run:
    docker exec dq-backend-1 python -m pytest \
        tests/integration/test_f003_p04_get_settings_api.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient
from jose import jwt

psycopg2.extras.register_uuid()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

_SLUG_PREFIX = "p4set-"


def _settings():
    from app.core.config import settings

    return settings


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _make_token(tenant_id: uuid.UUID, role: str) -> str:
    s = _settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _create_workspace(tenant_id: uuid.UUID, slug: str, status: str = "active") -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    workspace_id = uuid.uuid4()
    created_by = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone,
                status, status_reason, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s,
                'P4 settings test workspace', 'UTC',
                %s, NULL, NOW(), NOW(), %s, %s, 0
            )
            """,
            (
                workspace_id,
                tenant_id,
                f"P4 Settings WS {slug}",
                f"p4 settings ws {slug}",
                slug,
                status,
                created_by,
                created_by,
            ),
        )
    conn.close()
    return workspace_id


def _create_tenant(slug: str) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, 'active', 'us-east', 'enterprise',
                NOW(), NOW(), %s, %s, 0
            ) ON CONFLICT (tenant_slug) DO UPDATE SET status = 'active'
            RETURNING tenant_id
            """,
            (tenant_id, f"Tenant {slug}", slug, uuid.uuid4(), uuid.uuid4()),
        )
        row = cur.fetchone()
        if row:
            tenant_id = row[0]
    conn.close()
    return tenant_id


def _settings_url(workspace_id: uuid.UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def tenant_id() -> uuid.UUID:
    return _create_tenant("p4set-main-tenant")


@pytest.fixture(scope="module")
def other_tenant_id() -> uuid.UUID:
    return _create_tenant("p4set-other-tenant")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # workspace_settings rows deleted via cascade or directly
        cur.execute(
            "DELETE FROM control.workspaces WHERE workspace_slug LIKE %s",
            (_SLUG_PREFIX + "%",),
        )
        cur.execute(
            "DELETE FROM control.tenants WHERE tenant_slug LIKE 'p4set-%'",
        )
    conn.close()


# ---------------------------------------------------------------------------
# TC01 — Happy path: WA reads own workspace → 200 + full shape
# ---------------------------------------------------------------------------


class TestGetSettingsHappyPath:
    def test_workspace_admin_reads_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC01: workspace_administrator → 200 with full settings shape."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc01-wa")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["workspace_id"] == str(ws_id)
        assert data["tenant_id"] == str(tenant_id)

    def test_response_contains_all_required_fields(self, client: TestClient, tenant_id: uuid.UUID):
        """TC02: Response shape matches TDD §4.1 exactly."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc02-shape")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200
        data = resp.json()["data"]

        # Top-level fields
        assert "workspace_id" in data
        assert "tenant_id" in data
        assert "timezone_policy" in data
        assert "severity_policy" in data
        assert "sla_policy" in data
        assert "issue_grouping_policy" in data
        assert "naming_standards" in data
        assert "updated_at" in data
        assert "updated_by" in data

    def test_defaults_applied_for_null_jsonb_fields(self, client: TestClient, tenant_id: uuid.UUID):
        """TC03: Newly created workspace → NULL JSONB → defaults returned."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc03-defaults")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200
        data = resp.json()["data"]

        # timezone_policy — DB default is UTC
        assert data["timezone_policy"]["default_timezone"] == "UTC"

        # severity_policy — built-in defaults
        sp = data["severity_policy"]
        assert sp["critical_label"] == "Critical"
        assert sp["major_label"] == "Major"
        assert sp["minor_label"] == "Minor"
        assert sp["informational_label"] == "Informational"

        # sla_policy — built-in defaults
        sla = data["sla_policy"]
        assert sla["critical_hours"] == 4
        assert sla["major_hours"] == 24
        assert sla["minor_hours"] == 72
        assert sla["informational_hours"] is None

        # naming_standards — empty constraints
        ns = data["naming_standards"]
        assert "datasets" in ns
        assert "rules" in ns

    def test_data_engineer_reads_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC04: data_engineer role → 200 (in allowed read set)."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc04-de")
        token = _make_token(tenant_id, "data_engineer")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200

    def test_data_steward_reads_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC05: data_steward role → 200 (in allowed read set)."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc05-ds")
        token = _make_token(tenant_id, "data_steward")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200

    def test_platform_admin_reads_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC06: platform_admin → 200."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc06-pa")
        token = _make_token(tenant_id, "platform_admin")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200

    def test_platform_viewer_reads_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC07: platform_viewer → 200."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc07-pv")
        token = _make_token(tenant_id, "platform_viewer")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TC08 — Cross-tenant access
# ---------------------------------------------------------------------------


class TestGetSettingsCrossTenant:
    def test_platform_admin_reads_other_tenant_workspace_200(
        self, client: TestClient, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
    ):
        """TC08: Platform Admin can access workspace in another Tenant → 200."""
        ws_id = _create_workspace(other_tenant_id, _SLUG_PREFIX + "tc08-cross")
        # Token issued for tenant_id, but workspace belongs to other_tenant_id
        token = _make_token(tenant_id, "platform_admin")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200

    def test_platform_viewer_reads_other_tenant_workspace_200(
        self, client: TestClient, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
    ):
        """TC09: Platform Viewer can access workspace in another Tenant → 200."""
        ws_id = _create_workspace(other_tenant_id, _SLUG_PREFIX + "tc09-cross-pv")
        token = _make_token(tenant_id, "platform_viewer")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200

    def test_workspace_admin_cross_tenant_returns_404(
        self, client: TestClient, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
    ):
        """TC10: WA cannot access workspace in other Tenant → 404."""
        ws_id = _create_workspace(other_tenant_id, _SLUG_PREFIX + "tc10-wa-cross")
        # JWT tenant_id is tenant_id but workspace belongs to other_tenant_id
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "workspace_not_found"

    def test_data_engineer_cross_tenant_returns_404(
        self, client: TestClient, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
    ):
        """TC11: data_engineer cannot access workspace in other Tenant → 404."""
        ws_id = _create_workspace(other_tenant_id, _SLUG_PREFIX + "tc11-de-cross")
        token = _make_token(tenant_id, "data_engineer")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TC12 — Authorization failures
# ---------------------------------------------------------------------------


class TestGetSettingsAuth:
    def test_no_token_returns_401(self, client: TestClient, tenant_id: uuid.UUID):
        """TC12: Missing Authorization header → 401."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc12-noauth")

        resp = client.get(_settings_url(ws_id))

        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client: TestClient, tenant_id: uuid.UUID):
        """TC13: Malformed/invalid token → 401."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc13-badtoken")

        resp = client.get(
            _settings_url(ws_id),
            headers={"Authorization": "Bearer not.a.real.token"},
        )

        assert resp.status_code == 401

    def test_forbidden_role_returns_403(self, client: TestClient, tenant_id: uuid.UUID):
        """TC14: Role not in allowed set (e.g., some_custom_role) → 403."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc14-forbidden")
        token = _make_token(tenant_id, "some_custom_role")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# TC15 — Not found
# ---------------------------------------------------------------------------


class TestGetSettingsNotFound:
    def test_nonexistent_workspace_returns_404(self, client: TestClient, tenant_id: uuid.UUID):
        """TC15: Workspace does not exist at all → 404."""
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(
            _settings_url(uuid.uuid4()),
            headers=_auth(token),
        )

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "workspace_not_found"


# ---------------------------------------------------------------------------
# TC16 — Response field types
# ---------------------------------------------------------------------------


class TestGetSettingsResponseTypes:
    def test_sla_hours_are_integers(self, client: TestClient, tenant_id: uuid.UUID):
        """TC16: SLA hours must be integers in the response."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc16-types")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))
        assert resp.status_code == 200
        sla = resp.json()["data"]["sla_policy"]
        assert isinstance(sla["critical_hours"], int)
        assert isinstance(sla["major_hours"], int)
        assert isinstance(sla["minor_hours"], int)

    def test_naming_standards_structure(self, client: TestClient, tenant_id: uuid.UUID):
        """TC17: naming_standards has datasets and rules sub-objects."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc17-naming")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))
        assert resp.status_code == 200
        ns = resp.json()["data"]["naming_standards"]
        assert isinstance(ns["datasets"], dict)
        assert isinstance(ns["rules"], dict)

    def test_issue_grouping_policy_is_string(self, client: TestClient, tenant_id: uuid.UUID):
        """TC18: issue_grouping_policy must be a string."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc18-grouping")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.get(_settings_url(ws_id), headers=_auth(token))
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"]["issue_grouping_policy"], str)
