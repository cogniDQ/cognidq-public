"""
F059 — Webhook and Event Delivery — Integration Tests
======================================================

Tests:
    WHK-01  POST /webhooks requires auth (401 without token)
    WHK-02  POST /webhooks with invalid URL returns 422
    WHK-03  POST /webhooks with invalid event_type returns 422
    WHK-04  POST /webhooks happy path returns 201 with secret_key
    WHK-05  GET /webhooks returns subscriptions list
    WHK-06  GET /webhooks/{id} returns subscription (no secret_key)
    WHK-07  PATCH /webhooks/{id} updates subscription fields
    WHK-08  DELETE /webhooks/{id} returns 204 and subscription is gone
    WHK-09  GET /webhooks/{id}/deliveries returns empty list
    WHK-10  GET /webhooks-event-types returns valid event type list

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest \\
        tests/integration/test_f059_webhooks.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient
from jose import jwt

psycopg2.extras.register_uuid()

DATABASE_URL = "postgresql://postgres:postgres@db:5432/dataquality_db"


def _get_settings():
    from app.core.config import settings

    return settings


def _make_token_for_user(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(user_id),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    slug = f"f059test-{str(tid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (%s,%s,%s,'active','eu-west','starter',%s,%s,0,NOW(),NOW())
            """,
            (tid, f"F059 Tenant {str(tid)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tid


@pytest.fixture(scope="module")
def workspace_id(tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"F059 Workspace {str(wid)[:8]}"
    slug = f"f059test-ws-{str(wid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone, status, status_reason,
                created_at, updated_at, created_by, updated_by, version
            ) VALUES (%s,%s,%s,%s,%s,NULL,'UTC','active',NULL,NOW(),NOW(),%s,%s,0)
            """,
            (wid, tenant_id, name, name.lower(), slug, actor, actor),
        )
    conn.close()
    return wid


@pytest.fixture(scope="module")
def user_id(workspace_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    uid = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (id, email, password_hash, status, created_at, updated_at)
            VALUES (%s, %s, 'hash', 'active', NOW(), NOW())
            ON CONFLICT DO NOTHING
            """,
            (uid, f"f059-{str(uid)[:8]}@test.local"),
        )
        cur.execute(
            """
            INSERT INTO control.workspace_role_assignments
                (workspace_id, user_id, role_name, granted_by, granted_at)
            VALUES (%s, %s, 'workspace_administrator', %s, NOW())
            ON CONFLICT DO NOTHING
            """,
            (workspace_id, uid, uid),
        )
    conn.close()
    return uid


@pytest.fixture(scope="module")
def admin_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return _make_token_for_user(user_id, tenant_id, "workspace_administrator")


@pytest.fixture(scope="module", autouse=True)
def cleanup(workspace_id: uuid.UUID, tenant_id: uuid.UUID):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM webhook_delivery_log WHERE workspace_id = %s", (workspace_id,))
        cur.execute("DELETE FROM webhook_subscriptions WHERE workspace_id = %s", (workspace_id,))
        cur.execute(
            "DELETE FROM control.workspace_audit_logs WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.workspace_role_assignments WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute("DELETE FROM users WHERE email LIKE 'f059-%@test.local'")
        cur.execute("DELETE FROM control.workspaces WHERE workspace_id = %s", (workspace_id,))
        cur.execute("DELETE FROM control.tenants WHERE tenant_id = %s", (tenant_id,))
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_whk_01_create_webhook_requires_auth(client: TestClient, workspace_id: uuid.UUID):
    """WHK-01: POST /webhooks without auth returns 401."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={
            "name": "test",
            "target_url": "https://example.com/hook",
            "event_types": ["execution_failed"],
        },
    )
    assert resp.status_code == 401, resp.text


def test_whk_02_create_webhook_invalid_url(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """WHK-02: POST /webhooks with non-HTTPS URL or bad URL returns 422."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={
            "name": "bad-url",
            "target_url": "not-a-url",
            "event_types": ["execution_failed"],
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422, resp.text


def test_whk_03_create_webhook_invalid_event_type(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """WHK-03: POST /webhooks with unknown event_type returns 422."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={
            "name": "bad-event",
            "target_url": "https://example.com/hook",
            "event_types": ["nonexistent_event"],
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422, resp.text


def test_whk_04_create_webhook_happy_path(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """WHK-04: POST /webhooks happy path returns 201 with secret_key in response."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={
            "name": "My Hook",
            "target_url": "https://example.com/hook",
            "event_types": ["execution_failed", "issue_created"],
            "enabled": True,
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "My Hook"
    assert data["target_url"] == "https://example.com/hook"
    assert set(data["event_types"]) == {"execution_failed", "issue_created"}
    assert data["enabled"] is True
    assert "secret_key" in data
    assert len(data["secret_key"]) > 10  # auto-generated secret


def test_whk_05_list_webhooks(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """WHK-05: GET /webhooks returns subscriptions list with items and total."""
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1  # at least the one from WHK-04
    # Secret key must NOT be revealed in list
    for item in data["items"]:
        assert "secret_key" not in item


def test_whk_06_get_webhook_by_id(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """WHK-06: GET /webhooks/{id} returns correct subscription without secret_key."""
    # Get available subscription from list
    list_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        headers=_auth(admin_token),
    )
    items = list_resp.json()["items"]
    assert len(items) >= 1
    sub_id = items[0]["id"]

    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks/{sub_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == sub_id
    assert "secret_key" not in data


def test_whk_07_patch_webhook(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """WHK-07: PATCH /webhooks/{id} updates name and enabled fields."""
    list_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        headers=_auth(admin_token),
    )
    sub_id = list_resp.json()["items"][0]["id"]

    resp = client.patch(
        f"/api/v1/workspaces/{workspace_id}/webhooks/{sub_id}",
        json={"name": "Updated Hook", "enabled": False},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "Updated Hook"
    assert data["enabled"] is False


def test_whk_08_delete_webhook(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """WHK-08: DELETE /webhooks/{id} returns 204 and subsequent GET returns 404."""
    # Create a fresh webhook to delete
    create_resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        json={
            "name": "To Delete",
            "target_url": "https://example.com/delete-me",
            "event_types": ["incident_created"],
        },
        headers=_auth(admin_token),
    )
    assert create_resp.status_code == 201
    sub_id = create_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/workspaces/{workspace_id}/webhooks/{sub_id}",
        headers=_auth(admin_token),
    )
    assert del_resp.status_code == 204, del_resp.text

    get_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks/{sub_id}",
        headers=_auth(admin_token),
    )
    assert get_resp.status_code == 404, get_resp.text


def test_whk_09_list_deliveries_empty(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """WHK-09: GET /webhooks/{id}/deliveries returns empty list for new subscription."""
    list_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks",
        headers=_auth(admin_token),
    )
    sub_id = list_resp.json()["items"][0]["id"]

    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks/{sub_id}/deliveries",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


def test_whk_10_event_types_endpoint(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """WHK-10: GET /webhooks-event-types returns the valid event types list."""
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/webhooks-event-types",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "event_types" in data
    event_types = set(data["event_types"])
    expected = {"execution_failed", "issue_created", "incident_created", "incident_updated"}
    assert expected == event_types, f"Unexpected event types: {event_types}"
