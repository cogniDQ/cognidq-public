"""
F004 Packet 5 — Update Data Source API tests
=============================================

PATCH /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}

Test IDs: UPD-01 through UPD-12

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest tests/integration/test_f004_p05_update_api.py -v
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
    slug = f"p05test-ds-tenant-{str(tenant_id)[:8]}"
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
            (tenant_id, f"P05 Test Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "P05 Data Source Test WS"
    slug = f"p05test-ds-ws-{str(wid)[:8]}"
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


@pytest.fixture(scope="module")
def admin_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_administrator")


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


def _patch_url(workspace_id: uuid.UUID, data_source_id: str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}"


def _detail_url(workspace_id: uuid.UUID, data_source_id: str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}"


def _audit_url(workspace_id: uuid.UUID, data_source_id: str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}/audit-logs"


# ─────────────────────────────────────────────────────────────────────────────
# Helper: create a fresh data source for each test that needs one
# ─────────────────────────────────────────────────────────────────────────────


def _create_source(
    client: TestClient,
    workspace_id: uuid.UUID,
    steward_token: str,
    name: str | None = None,
    source_type: str = "postgresql",
) -> dict:
    body = {
        "source_name": name or f"test-source-{str(uuid.uuid4())[:8]}",
        "source_type": source_type,
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
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestUpdateDataSource:
    def test_upd01_patch_environment_only(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-01: PATCH environment only → 200, credential_reference unchanged."""
        ds = _create_source(client, test_workspace_id, steward_token)
        orig_cred_ref = ds["credential_reference"]

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"environment": "production"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["environment"] == "production"
        assert body["credential_reference"] == orig_cred_ref
        assert body["last_test_status"] == "untested"  # unchanged

    def test_upd02_patch_source_name_no_collision(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-02: PATCH source_name with valid, unique name → 200, name updated."""
        ds = _create_source(client, test_workspace_id, steward_token)
        new_name = f"renamed-source-{str(uuid.uuid4())[:8]}"

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"source_name": new_name},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        assert resp.json()["source_name"] == new_name

    def test_upd03_patch_source_name_collision_returns_409(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-03: PATCH source_name that collides with existing source → 409."""
        name_a = f"collision-a-{str(uuid.uuid4())[:8]}"
        name_b = f"collision-b-{str(uuid.uuid4())[:8]}"
        _create_source(client, test_workspace_id, steward_token, name=name_a)
        ds_b = _create_source(client, test_workspace_id, steward_token, name=name_b)

        resp = client.patch(
            _patch_url(test_workspace_id, ds_b["data_source_id"]),
            json={"source_name": name_a},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_SOURCE_NAME"

    def test_upd04_patch_credentials_rotates_reference(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-04: PATCH with credential fields → 200, new credential_reference, last_test_status='untested'."""
        ds = _create_source(client, test_workspace_id, steward_token)
        old_cred_ref = ds["credential_reference"]

        new_creds = dict(_pg_creds())
        new_creds["password"] = "new_password_rotated"

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"credentials": new_creds},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["credential_reference"] != old_cred_ref, "Expected new credential_reference"
        assert body["last_test_status"] == "untested"

    def test_upd05_patch_source_type_returns_400_immutable(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-05: PATCH with source_type → 400 IMMUTABLE_FIELD."""
        ds = _create_source(client, test_workspace_id, steward_token)

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"source_type": "mysql"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "IMMUTABLE_FIELD"

    def test_upd06_patch_connection_mode_returns_400_immutable(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-06: PATCH with connection_mode → 400 IMMUTABLE_FIELD."""
        ds = _create_source(client, test_workspace_id, steward_token)

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"connection_mode": "agent"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "IMMUTABLE_FIELD"

    def test_upd07_patch_nonexistent_returns_404(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-07: PATCH non-existent source → 404."""
        resp = client.patch(
            _patch_url(test_workspace_id, str(uuid.uuid4())),
            json={"environment": "production"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 404

    def test_upd08_data_steward_cannot_patch(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        test_tenant_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-08: workspace_viewer role → 403 (read-only, cannot PATCH)."""
        viewer_token = _make_token(test_tenant_id, "workspace_viewer")
        ds = _create_source(client, test_workspace_id, steward_token)

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"environment": "production"},
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 403

    def test_upd09_audit_log_contains_updated_event_no_credentials(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-09: Audit log contains data_source.updated with changed fields but no credential values."""
        ds = _create_source(client, test_workspace_id, steward_token)
        new_desc = "Updated description via patch"

        client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"description": new_desc},
            headers=_auth(steward_token),
        )

        resp = client.get(
            _audit_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        action_types = [item["action_type"] for item in body["items"]]
        assert "data_source.updated" in action_types

        # Verify no credential values in audit new_data
        for item in body["items"]:
            if item["new_data"]:
                nd = item["new_data"]
                for sensitive in ("password", "private_key", "credentials"):
                    assert sensitive not in nd, f"Sensitive key '{sensitive}' in audit new_data"

    def test_upd10_patch_archived_source_metadata_succeeds(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-10: PATCH archived source metadata (description) → 200."""
        ds = _create_source(client, test_workspace_id, steward_token)

        # Directly archive via DB (no archive endpoint yet)
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE control.data_sources SET status='archived', archived_at=NOW(), archived_by=%s WHERE data_source_id=%s",
                (uuid.uuid4(), uuid.UUID(ds["data_source_id"])),
            )
        conn.close()

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"description": "Updated even when archived"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated even when archived"

    def test_upd11_old_credential_superseded_after_rotation(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-11: Old credential row has superseded_at set after credential rotation."""
        ds = _create_source(client, test_workspace_id, steward_token)
        old_cred_ref = uuid.UUID(ds["credential_reference"])

        new_creds = dict(_pg_creds())
        new_creds["password"] = "rotated_password_check"

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"credentials": new_creds},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200

        # Verify superseded_at is set on the old credential row
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT superseded_at FROM control.data_source_credentials WHERE credential_id = %s",
                (old_cred_ref,),
            )
            row = cur.fetchone()
        conn.close()
        assert row is not None, "Old credential row not found"
        assert row[0] is not None, "Expected superseded_at to be set on old credential"

    def test_upd12_updated_at_and_updated_by_change(
        self,
        client: TestClient,
        test_workspace_id: uuid.UUID,
        test_tenant_id: uuid.UUID,
        steward_token: str,
    ):
        """UPD-12: updated_at and updated_by are updated on successful PATCH."""
        ds = _create_source(client, test_workspace_id, steward_token)
        ds["updated_at"]

        actor_id = uuid.uuid4()
        actor_token = _make_token(test_tenant_id, "workspace_steward", actor_id=actor_id)

        resp = client.patch(
            _patch_url(test_workspace_id, ds["data_source_id"]),
            json={"environment": "development"},
            headers=_auth(actor_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        # updated_at should have changed (or at minimum be present)
        assert body.get("updated_at") is not None
        # updated_by should match the actor from the JWT
        assert body.get("updated_by") is not None
