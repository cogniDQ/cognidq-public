"""
F004 Packet 4 — List and Get Data Source API tests
====================================================

GET  /api/v1/workspaces/{workspace_id}/data-sources
GET  /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}
GET  /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}/audit-logs

Test IDs: LIST-01 through LIST-06, GET-01 through GET-05, ALOG-01

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest tests/integration/test_f004_p04_list_get_api.py -v
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient
from jose import jwt

psycopg2.extras.register_uuid()

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

BASE_URL = "/api/v1/workspaces/{workspace_id}/data-sources"


def _get_settings():
    from app.core.config import settings

    return settings


# ─────────────────────────────────────────────────────────────────────────────
# Module-scoped fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def test_tenant_id() -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    slug = f"p04test-ds-tenant-{str(tenant_id)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, 'active', 'eu-west', 'starter',
                %s, %s, 0, NOW(), NOW()
            )
            """,
            (tenant_id, f"P04 Test Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "P04 Data Source Test WS"
    slug = f"p04test-ds-ws-{str(wid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone, status, status_reason,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s, NULL, 'UTC', 'active', NULL,
                NOW(), NOW(), %s, %s, 0
            )
            """,
            (wid, test_tenant_id, name, name.lower(), slug, actor, actor),
        )
    conn.close()
    return wid


@pytest.fixture(scope="module")
def other_tenant_id() -> uuid.UUID:
    """A second tenant (for cross-workspace isolation tests)."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    slug = f"p04test-other-tenant-{str(tenant_id)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, 'active', 'eu-west', 'starter',
                %s, %s, 0, NOW(), NOW()
            )
            """,
            (tenant_id, f"P04 Other Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


def _make_token(
    tenant_id: uuid.UUID,
    role: str,
    actor_id: uuid.UUID | None = None,
) -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(actor_id or uuid.uuid4()),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def steward_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_steward")


@pytest.fixture(scope="module")
def viewer_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_viewer")


@pytest.fixture(scope="module")
def operator_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "platform_operator")


@pytest.fixture(scope="module")
def other_tenant_token(other_tenant_id: uuid.UUID) -> str:
    return _make_token(other_tenant_id, "workspace_steward")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _pg_creds() -> dict:
    return {
        "host": "db.example.com",
        "port": 5432,
        "database": "sales",
        "username": "reader",
        "password": "s3cr3t",
    }


def _list_url(workspace_id: uuid.UUID) -> str:
    return BASE_URL.format(workspace_id=workspace_id)


def _detail_url(workspace_id: uuid.UUID, data_source_id: uuid.UUID | str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}"


def _audit_url(workspace_id: uuid.UUID, data_source_id: uuid.UUID | str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}/audit-logs"


# ─────────────────────────────────────────────────────────────────────────────
# Test data setup — create several data sources before running list/get tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def created_data_sources(
    client: TestClient,
    test_workspace_id: uuid.UUID,
    steward_token: str,
) -> list[dict]:
    """
    Create 3 data sources (2 postgresql/active, 1 mysql/active) for use in
    all list and get tests.  Returns the list of API response bodies.
    """
    sources = [
        {
            "source_name": f"pg-source-a-{str(uuid.uuid4())[:8]}",
            "source_type": "postgresql",
            "connection_mode": "direct",
            "environment": "staging",
            "credentials": _pg_creds(),
        },
        {
            "source_name": f"pg-source-b-{str(uuid.uuid4())[:8]}",
            "source_type": "postgresql",
            "connection_mode": "direct",
            "environment": "development",
            "credentials": _pg_creds(),
        },
        {
            "source_name": f"mysql-source-{str(uuid.uuid4())[:8]}",
            "source_type": "mysql",
            "connection_mode": "direct",
            "environment": "staging",
            "credentials": {
                "host": "mysql.example.com",
                "port": 3306,
                "database": "shop",
                "username": "reader",
                "password": "s3cr3t",
            },
        },
    ]
    results = []
    url = _list_url(test_workspace_id)
    for body in sources:
        resp = client.post(url, json=body, headers=_auth(steward_token))
        assert resp.status_code == 201, f"Setup failed: {resp.text}"
        results.append(resp.json())
    return results


@pytest.fixture(scope="module", autouse=True)
def cleanup(test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID, other_tenant_id: uuid.UUID):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM control.data_source_credentials
            WHERE data_source_id IN (
                SELECT data_source_id FROM control.data_sources
                WHERE workspace_id = %s
            )
            """,
            (test_workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.data_sources WHERE workspace_id = %s",
            (test_workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.workspace_audit_logs WHERE workspace_id = %s",
            (test_workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.workspaces WHERE workspace_id = %s",
            (test_workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.tenants WHERE tenant_id = %s",
            (test_tenant_id,),
        )
        cur.execute(
            "DELETE FROM control.tenants WHERE tenant_id = %s",
            (other_tenant_id,),
        )
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# LIST tests
# ─────────────────────────────────────────────────────────────────────────────


class TestListDataSources:
    def test_list01_returns_all_sources_no_filter(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """LIST-01: GET list returns all data sources for the workspace."""
        resp = client.get(
            _list_url(test_workspace_id),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "page" in body
        assert "page_size" in body
        assert "has_next" in body
        assert body["total"] >= 3, "Expected at least 3 sources"
        assert len(body["items"]) >= 3

    def test_list02_status_filter_archived_returns_only_archived(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """LIST-02: ?status=archived returns only archived sources."""
        resp = client.get(
            _list_url(test_workspace_id),
            params={"status": "archived"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # No sources have been archived yet → total should be 0
        assert body["total"] == 0
        assert body["items"] == []

    def test_list03_source_type_filter_returns_matching_types(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """LIST-03: ?source_type=postgresql returns only postgresql sources."""
        resp = client.get(
            _list_url(test_workspace_id),
            params={"source_type": "postgresql"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 2
        for item in body["items"]:
            assert item["source_type"] == "postgresql"

    def test_list04_no_credential_fields_in_list_items(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """LIST-04: No raw credential fields appear in any list item."""
        resp = client.get(
            _list_url(test_workspace_id),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        sensitive_keys = {"password", "private_key", "service_account_json", "credentials"}
        for item in resp.json()["items"]:
            for key in sensitive_keys:
                assert key not in item, f"Sensitive key '{key}' found in list item"
            # credential_reference (UUID) is OK; raw credentials dict is not
            assert "credentials" not in item

    def test_list05_workspace_viewer_can_list(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        viewer_token: str,
        created_data_sources: list[dict],
    ):
        """LIST-05: workspace_viewer can access the list endpoint (200)."""
        resp = client.get(
            _list_url(test_workspace_id),
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 200

    def test_list06_cross_workspace_returns_empty_or_404(
        self,
        client: TestClient,
        other_tenant_token: str,
        test_workspace_id: uuid.UUID,
        created_data_sources: list[dict],
    ):
        """LIST-06: Token from a different tenant against this workspace → 404."""
        resp = client.get(
            _list_url(test_workspace_id),
            headers=_auth(other_tenant_token),
        )
        # workspace doesn't belong to other tenant → 404
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# GET detail tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGetDataSource:
    def test_get01_existing_source_returns_200_with_credential_reference(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """GET-01: GET detail → 200, credential_reference present, no raw creds."""
        ds_id = created_data_sources[0]["data_source_id"]
        resp = client.get(
            _detail_url(test_workspace_id, ds_id),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data_source_id"] == ds_id
        assert body["credential_reference"] is not None
        # No plaintext credentials
        assert "credentials" not in body
        assert "password" not in body

    def test_get02_nonexistent_source_returns_404(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """GET-02: GET non-existent data_source_id → 404."""
        resp = client.get(
            _detail_url(test_workspace_id, uuid.uuid4()),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body

    def test_get03_detail_from_different_workspace_returns_404(
        self,
        client: TestClient,
        other_tenant_token: str,
        test_workspace_id: uuid.UUID,
        created_data_sources: list[dict],
    ):
        """GET-03: GET detail from a different tenant's token against this workspace → 404."""
        ds_id = created_data_sources[0]["data_source_id"]
        resp = client.get(
            _detail_url(test_workspace_id, ds_id),
            headers=_auth(other_tenant_token),
        )
        assert resp.status_code == 404

    def test_get04_workspace_viewer_can_get_detail(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        viewer_token: str,
        created_data_sources: list[dict],
    ):
        """GET-04: workspace_viewer can read detail (200)."""
        ds_id = created_data_sources[0]["data_source_id"]
        resp = client.get(
            _detail_url(test_workspace_id, ds_id),
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 200

    def test_get05_platform_operator_can_get_detail(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        operator_token: str,
        created_data_sources: list[dict],
    ):
        """GET-05: platform_operator can read detail (200)."""
        ds_id = created_data_sources[0]["data_source_id"]
        resp = client.get(
            _detail_url(test_workspace_id, ds_id),
            headers=_auth(operator_token),
        )
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Audit log test
# ─────────────────────────────────────────────────────────────────────────────


class TestAuditLogs:
    def test_alog01_audit_log_has_created_event_after_create(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
        created_data_sources: list[dict],
    ):
        """ALOG-01: GET audit-logs returns data_source.created event after create."""
        ds_id = created_data_sources[0]["data_source_id"]
        resp = client.get(
            _audit_url(test_workspace_id, ds_id),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["total"] >= 1, "Expected at least one audit event"
        action_types = [item["action_type"] for item in body["items"]]
        assert "data_source.created" in action_types, (
            f"Expected 'data_source.created' audit event, got: {action_types}"
        )
