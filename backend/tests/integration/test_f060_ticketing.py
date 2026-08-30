"""
F060 — External Ticketing Integration Hooks — Integration Tests
===============================================================

Tests:
    TKT-01  POST /ticketing-configs requires auth
    TKT-02  POST /ticketing-configs with invalid system_name returns 422
    TKT-03  POST /ticketing-configs happy path returns 201
    TKT-04  GET /ticketing-configs returns list
    TKT-05  GET /ticketing-configs/{id} returns config detail
    TKT-06  PATCH /ticketing-configs/{id} updates fields
    TKT-07  DELETE /ticketing-configs/{id} returns 204 and config is gone
    TKT-08  GET /ticketing-systems returns valid system names list
    TKT-09  PUT /issues/{id}/external-ticket links ticket reference
    TKT-10  PUT /incidents/{id}/external-ticket links ticket reference

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest \\
        tests/integration/test_f060_ticketing.py -v
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
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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
    slug = f"f060test-{str(tid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (%s,%s,%s,'active','eu-west','starter',%s,%s,0,NOW(),NOW())
            """,
            (tid, f"F060 Tenant {str(tid)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tid


@pytest.fixture(scope="module")
def workspace_id(tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"F060 Workspace {str(wid)[:8]}"
    slug = f"f060ws-{str(wid)[:8]}"
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
            (uid, f"f060-{str(uid)[:8]}@test.local"),
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


@pytest.fixture(scope="module")
def seeded_issue_id(workspace_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    """Seed a minimal issue for external ticket linking tests."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    iid = uuid.uuid4()
    flow_id = uuid.uuid4()
    fe_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dq_flows (id, workspace_id, name, flow_definition, version, status, created_by, created_at, updated_at)
            VALUES (%s, %s, %s, '{}'::jsonb, 1, 'active', %s, NOW(), NOW())
            ON CONFLICT DO NOTHING
            """,
            (flow_id, _ORG_ID, f"f060-flow-{str(flow_id)[:8]}", user_id),
        )
        cur.execute(
            """
            INSERT INTO flow_executions (id, flow_id, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT DO NOTHING
            """,
            (fe_id, flow_id),
        )
        cur.execute(
            """
            INSERT INTO issues (
                id, workspace_id, tenant_id, flow_execution_id,
                issue_type, severity, status, title,
                opened_at, created_at, updated_at
            ) VALUES (%s,%s,%s,%s,
                      'threshold_breach','major','open','F060 test issue',
                      NOW(),NOW(),NOW())
            """,
            (iid, workspace_id, tenant_id, fe_id),
        )
    conn.close()
    return iid


@pytest.fixture(scope="module")
def seeded_incident_id(
    workspace_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    """Seed a minimal incident for external ticket linking tests."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    inc_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO incidents (
                id, workspace_id, tenant_id, title, severity, priority, status,
                created_by_user_id, opened_at, created_at, updated_at
            ) VALUES (%s,%s,%s,'F060 test incident','major','P2','open',%s,NOW(),NOW(),NOW())
            """,
            (inc_id, workspace_id, tenant_id, user_id),
        )
    conn.close()
    return inc_id


@pytest.fixture(scope="module", autouse=True)
def cleanup(workspace_id: uuid.UUID, tenant_id: uuid.UUID):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM ticketing_integration_configs WHERE workspace_id = %s", (workspace_id,)
        )
        cur.execute("DELETE FROM incidents WHERE workspace_id = %s", (workspace_id,))
        cur.execute("DELETE FROM issues WHERE workspace_id = %s", (workspace_id,))
        cur.execute(
            "DELETE FROM flow_executions WHERE flow_id IN "
            "(SELECT id FROM dq_flows WHERE name LIKE 'f060-flow-%')"
        )
        cur.execute("DELETE FROM dq_flows WHERE name LIKE 'f060-flow-%'")
        cur.execute(
            "DELETE FROM control.workspace_audit_logs WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.workspace_role_assignments WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute("DELETE FROM users WHERE email LIKE 'f060-%@test.local'")
        cur.execute("DELETE FROM control.workspaces WHERE workspace_id = %s", (workspace_id,))
        cur.execute("DELETE FROM control.tenants WHERE tenant_id = %s", (tenant_id,))
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tkt_01_create_config_requires_auth(client: TestClient, workspace_id: uuid.UUID):
    """TKT-01: POST /ticketing-configs without auth returns 401."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        json={"system_name": "jira", "display_name": "Jira"},
    )
    assert resp.status_code == 401, resp.text


def test_tkt_02_create_config_invalid_system(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """TKT-02: POST /ticketing-configs with unknown system_name returns 422."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        json={"system_name": "notreal", "display_name": "Unknown"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 422, resp.text


def test_tkt_03_create_config_happy_path(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """TKT-03: POST /ticketing-configs happy path returns 201."""
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        json={
            "system_name": "jira",
            "display_name": "Jira Cloud",
            "base_url": "https://mycompany.atlassian.net",
            "project_key": "DQ",
            "default_issue_type": "Bug",
            "enabled": True,
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["system_name"] == "jira"
    assert data["display_name"] == "Jira Cloud"
    assert data["project_key"] == "DQ"
    assert data["enabled"] is True


def test_tkt_04_list_configs(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """TKT-04: GET /ticketing-configs returns list with created config."""
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


def test_tkt_05_get_config_by_id(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """TKT-05: GET /ticketing-configs/{id} returns correct config."""
    list_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        headers=_auth(admin_token),
    )
    cfg_id = list_resp.json()["items"][0]["id"]

    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs/{cfg_id}",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == cfg_id


def test_tkt_06_patch_config(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """TKT-06: PATCH /ticketing-configs/{id} updates fields."""
    list_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        headers=_auth(admin_token),
    )
    cfg_id = list_resp.json()["items"][0]["id"]

    resp = client.patch(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs/{cfg_id}",
        json={"display_name": "Jira Updated", "enabled": False},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["display_name"] == "Jira Updated"
    assert data["enabled"] is False


def test_tkt_07_delete_config(client: TestClient, workspace_id: uuid.UUID, admin_token: str):
    """TKT-07: DELETE /ticketing-configs/{id} returns 204 and config is gone."""
    # Create a throwaway config
    create_resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs",
        json={"system_name": "linear", "display_name": "Linear"},
        headers=_auth(admin_token),
    )
    assert create_resp.status_code == 201
    cfg_id = create_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs/{cfg_id}",
        headers=_auth(admin_token),
    )
    assert del_resp.status_code == 204, del_resp.text

    get_resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/ticketing-configs/{cfg_id}",
        headers=_auth(admin_token),
    )
    assert get_resp.status_code == 404, get_resp.text


def test_tkt_08_list_ticketing_systems(
    client: TestClient, workspace_id: uuid.UUID, admin_token: str
):
    """TKT-08: GET /ticketing-systems returns all valid system names."""
    resp = client.get(
        f"/api/v1/workspaces/{workspace_id}/ticketing-systems",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "systems" in data
    systems = set(data["systems"])
    expected = {"jira", "linear", "github", "servicenow", "pagerduty", "custom"}
    assert expected == systems, f"Unexpected systems: {systems}"


def test_tkt_09_link_issue_external_ticket(
    client: TestClient,
    workspace_id: uuid.UUID,
    admin_token: str,
    seeded_issue_id: uuid.UUID,
):
    """TKT-09: PUT /issues/{id}/external-ticket links external ticket."""
    resp = client.put(
        f"/api/v1/workspaces/{workspace_id}/issues/{seeded_issue_id}/external-ticket",
        json={
            "external_ticket_id": "DQ-1234",
            "external_ticket_url": "https://mycompany.atlassian.net/browse/DQ-1234",
            "external_system": "jira",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["external_ticket_id"] == "DQ-1234"
    assert data["external_system"] == "jira"
    assert "atlassian" in (data["external_ticket_url"] or "")


def test_tkt_10_link_incident_external_ticket(
    client: TestClient,
    workspace_id: uuid.UUID,
    admin_token: str,
    seeded_incident_id: uuid.UUID,
):
    """TKT-10: PUT /incidents/{id}/external-ticket links external ticket."""
    resp = client.put(
        f"/api/v1/workspaces/{workspace_id}/incidents/{seeded_incident_id}/external-ticket",
        json={
            "external_ticket_id": "INC-42",
            "external_ticket_url": "https://github.com/org/repo/issues/42",
            "external_system": "github",
        },
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["external_ticket_id"] == "INC-42"
    assert data["external_system"] == "github"
