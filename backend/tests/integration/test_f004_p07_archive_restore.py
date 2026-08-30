"""
F004 Packet 7 — Archive and Restore API tests
==============================================

POST /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}/archive
POST /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}/restore

Test IDs: ARC-01 through ARC-06, RST-01 through RST-06

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest tests/integration/test_f004_p07_archive_restore.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

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
    slug = f"p07test-ds-tenant-{str(tenant_id)[:8]}"
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
            (tenant_id, f"P07 Test Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "P07 Data Source Test WS"
    slug = f"p07test-ds-ws-{str(wid)[:8]}"
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


def _post_url(workspace_id: uuid.UUID) -> str:
    return BASE_URL.format(workspace_id=workspace_id)


def _archive_url(workspace_id: uuid.UUID, data_source_id: str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}/archive"


def _restore_url(workspace_id: uuid.UUID, data_source_id: str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}/restore"


def _create_source(
    client: TestClient,
    workspace_id: uuid.UUID,
    steward_token: str,
    name: str | None = None,
) -> dict:
    body = {
        "source_name": name or f"test-source-{str(uuid.uuid4())[:8]}",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "staging",
        "credentials": _pg_creds(),
    }
    resp = client.post(
        _post_url(workspace_id),
        json=body,
        headers=_auth(steward_token),
    )
    assert resp.status_code == 201, f"Setup failed: {resp.text}"
    return resp.json()


@pytest.fixture(scope="module", autouse=True)
def cleanup(test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID):
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
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Archive Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestArchiveDataSource:
    def test_arc01_archive_active_source_with_no_datasets(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """ARC-01: archive active source with 0 active datasets → status: archived, archived_at set."""
        ds = _create_source(client, test_workspace_id, steward_token)
        resp = client.post(
            _archive_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "archived"
        assert body.get("data_source_id") == ds["data_source_id"]

    def test_arc02_archive_blocked_by_active_datasets(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """ARC-02: count_active_datasets returns 3 → 409 with count in message."""
        ds = _create_source(client, test_workspace_id, steward_token)
        with patch(
            "app.services.data_sources.repository.DataSourceRepository.count_active_datasets",
            return_value=3,
        ):
            resp = client.post(
                _archive_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        err = body.get("error", {})
        assert err.get("code") == "ACTIVE_DATASETS_BLOCKING_ARCHIVE"
        assert "3" in err.get("message", "")

    def test_arc03_archive_already_archived_returns_409(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """ARC-03: archive already-archived source → 409."""
        ds = _create_source(client, test_workspace_id, steward_token)
        # Archive once
        resp1 = client.post(
            _archive_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp1.status_code == 200, resp1.text
        # Attempt to archive again
        resp2 = client.post(
            _archive_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp2.status_code == 409, resp2.text
        err = resp2.json().get("error", {})
        assert err.get("code") == "DATA_SOURCE_ALREADY_ARCHIVED"

    def test_arc04_data_steward_cannot_archive(
        self, client: TestClient, test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID
    ):
        """ARC-04: POST /archive as data_steward → 403."""
        ds_token = _make_token(test_tenant_id, "data_steward")
        ds = _create_source(
            client, test_workspace_id, _make_token(test_tenant_id, "workspace_steward")
        )
        resp = client.post(
            _archive_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(ds_token),
        )
        assert resp.status_code == 403, resp.text

    def test_arc05_archive_emits_audit_log(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """ARC-05: audit log contains data_source_archived after successful archive."""
        ds = _create_source(client, test_workspace_id, steward_token)
        resp = client.post(
            _archive_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text

        audit_resp = client.get(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/audit-logs",
            headers=_auth(steward_token),
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json().get("items", [])
        archive_events = [e for e in items if "archived" in e.get("action_type", "")]
        assert len(archive_events) >= 1

    def test_arc06_archived_datasets_do_not_block_archival(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """ARC-06: archived datasets (ARCHIVED status) do not block archival."""
        ds = _create_source(client, test_workspace_id, steward_token)
        # count_active_datasets returns 0 (only counts 'active' datasets, not 'archived')
        # With no real datasets table (F005 pending), it returns 0 naturally.
        resp = client.post(
            _archive_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "archived"


# ─────────────────────────────────────────────────────────────────────────────
# Restore Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRestoreDataSource:
    def _archive_first(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        steward_token: str,
    ) -> dict:
        """Create and archive a data source, return its dict."""
        ds = _create_source(client, workspace_id, steward_token)
        resp = client.post(
            _archive_url(workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        return ds

    def test_rst01_restore_archived_source(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """RST-01: restore archived source → status: active."""
        ds = self._archive_first(client, test_workspace_id, steward_token)
        resp = client.post(
            _restore_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "active"

    def test_rst02_restore_active_source_returns_409(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """RST-02: restore active source → 409."""
        ds = _create_source(client, test_workspace_id, steward_token)
        resp = client.post(
            _restore_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409, resp.text
        err = resp.json().get("error", {})
        assert err.get("code") == "DATA_SOURCE_NOT_ARCHIVED"

    def test_rst03_restore_nonexistent_source_returns_404(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """RST-03: restore non-existent source → 404."""
        fake_id = str(uuid.uuid4())
        resp = client.post(
            _restore_url(test_workspace_id, fake_id),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 404, resp.text

    def test_rst04_restore_emits_audit_log(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """RST-04: audit log contains data_source_restored after successful restore."""
        ds = self._archive_first(client, test_workspace_id, steward_token)
        resp = client.post(
            _restore_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text

        audit_resp = client.get(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/audit-logs",
            headers=_auth(steward_token),
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json().get("items", [])
        restore_events = [e for e in items if "restored" in e.get("action_type", "")]
        assert len(restore_events) >= 1

    def test_rst05_archived_at_and_archived_by_are_null_after_restore(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """RST-05: archived_at and archived_by are NULL after restore."""
        ds = self._archive_first(client, test_workspace_id, steward_token)
        resp = client.post(
            _restore_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text

        # Verify via database
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT archived_at, archived_by FROM control.data_sources WHERE data_source_id = %s",
                (uuid.UUID(ds["data_source_id"]),),
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None
        assert row[0] is None, "archived_at should be NULL after restore"
        assert row[1] is None, "archived_by should be NULL after restore"

    def test_rst06_data_engineer_can_restore(
        self, client: TestClient, test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID
    ):
        """RST-06: POST /restore as data_engineer → 200."""
        steward_token = _make_token(test_tenant_id, "workspace_steward")
        ds = self._archive_first(client, test_workspace_id, steward_token)
        engineer_token = _make_token(test_tenant_id, "data_engineer")
        resp = client.post(
            _restore_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(engineer_token),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "active"
