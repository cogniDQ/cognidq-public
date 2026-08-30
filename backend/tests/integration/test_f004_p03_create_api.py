"""
F004 Packet 3 — Create Data Source API tests
==============================================

POST /api/v1/workspaces/{workspace_id}/data-sources

Test IDs: DS-CREATE-01 through DS-CREATE-15

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f004_p03_create_api.py -v

Environment variables:
    DATABASE_URL  — Postgres DSN (set automatically in Docker service)
    CREDENTIAL_ENCRYPTION_KEY — Fernet key (set in docker-compose.yml)
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

ENDPOINT = "/api/v1/workspaces/{workspace_id}/data-sources"


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
    """Create a tenant for this module's tests and return its id."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    tenant_id = uuid.uuid4()
    actor = uuid.uuid4()
    slug = f"p03test-ds-tenant-{str(tenant_id)[:8]}"
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
            (tenant_id, f"P03 Test Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    """Create a workspace for this module's tests and return its id."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "P03 Data Source Test WS"
    slug = f"p03test-ds-ws-{str(wid)[:8]}"
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


@pytest.fixture(scope="module")
def viewer_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "workspace_viewer")


@pytest.fixture(scope="module")
def operator_token(test_tenant_id: uuid.UUID) -> str:
    return _make_token(test_tenant_id, "platform_operator")


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


def _bq_creds() -> dict:
    import json

    sa = {
        "type": "service_account",
        "project_id": "my-gcp-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5J\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "sa@my-gcp-project.iam.gserviceaccount.com",
        "client_id": "123456789",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    return {
        "project_id": "my-gcp-project",
        "dataset_id": "analytics",
        "service_account_json": json.dumps(sa),
    }


def _url(workspace_id: uuid.UUID) -> str:
    return ENDPOINT.format(workspace_id=workspace_id)


@pytest.fixture(scope="module", autouse=True)
def cleanup(test_workspace_id: uuid.UUID, test_tenant_id: uuid.UUID):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # Supersede credentials first to avoid FK issues
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
            "DELETE FROM control.workspaces WHERE workspace_id = %s",
            (test_workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.tenants WHERE tenant_id = %s",
            (test_tenant_id,),
        )
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-01: Valid PostgreSQL payload → 201
# ─────────────────────────────────────────────────────────────────────────────
def test_create_postgresql_returns_201(client, test_workspace_id, steward_token):
    """DS-CREATE-01: Steward creates a postgresql source → 201 with correct fields."""
    body = {
        "source_name": "Sales DB",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "production",
        "credentials": _pg_creds(),
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_name"] == "Sales DB"
    assert data["source_type"] == "postgresql"
    assert data["status"] == "active"
    assert data["last_test_status"] == "untested"
    assert "credential_reference" in data
    assert data["credential_reference"] is not None
    # credentials MUST NOT appear in the response
    assert "credentials" not in data
    assert "password" not in str(data)


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-02: workspace_administrator can also create → 201
# ─────────────────────────────────────────────────────────────────────────────
def test_create_admin_role_returns_201(client, test_workspace_id, admin_token):
    """DS-CREATE-02: workspace_administrator can create a data source."""
    body = {
        "source_name": "Admin Created Source",
        "source_type": "mysql",
        "connection_mode": "direct",
        "environment": "staging",
        "credentials": {
            "host": "mysql.example.com",
            "port": 3306,
            "database": "app_db",
            "username": "reader",
            "password": "pass123",
        },
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(admin_token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_name"] == "Admin Created Source"
    assert data["source_type"] == "mysql"


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-03: workspace_viewer cannot create → 403
# ─────────────────────────────────────────────────────────────────────────────
def test_create_viewer_role_returns_403(client, test_workspace_id, viewer_token):
    """DS-CREATE-03: workspace_viewer is read-only → 403."""
    body = {
        "source_name": "Viewer Forbidden DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": _pg_creds(),
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(viewer_token))
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-04: platform_operator cannot create → 403
# ─────────────────────────────────────────────────────────────────────────────
def test_create_platform_operator_returns_403(client, test_workspace_id, operator_token):
    """DS-CREATE-04: platform_operator cannot write data sources → 403."""
    body = {
        "source_name": "Operator Forbidden DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": _pg_creds(),
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(operator_token))
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-05: No auth header → 401
# ─────────────────────────────────────────────────────────────────────────────
def test_create_no_auth_returns_401(client, test_workspace_id):
    """DS-CREATE-05: Missing Authorization header → 401."""
    body = {
        "source_name": "No Auth DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": _pg_creds(),
    }
    resp = client.post(_url(test_workspace_id), json=body)
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-06: Duplicate source_name → 409
# ─────────────────────────────────────────────────────────────────────────────
def test_create_duplicate_name_returns_409(client, test_workspace_id, steward_token):
    """DS-CREATE-06: Creating a source_name already used in the workspace → 409."""
    body = {
        "source_name": "Duplicate Test Source",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": _pg_creds(),
    }
    # First create
    r1 = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert r1.status_code == 201
    # Second create (same source_name, case-insensitive check at DB level)
    r2 = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "DUPLICATE_SOURCE_NAME"


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-07: Duplicate name is case-insensitive → 409
# ─────────────────────────────────────────────────────────────────────────────
def test_create_duplicate_name_case_insensitive_returns_409(
    client, test_workspace_id, steward_token
):
    """DS-CREATE-07: 'SALES DB' conflicts with existing 'sales db' → 409."""
    body_lower = {
        "source_name": "case insensitive source",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": _pg_creds(),
    }
    r1 = client.post(_url(test_workspace_id), json=body_lower, headers=_auth(steward_token))
    assert r1.status_code == 201
    body_upper = {**body_lower, "source_name": "CASE INSENSITIVE SOURCE"}
    r2 = client.post(_url(test_workspace_id), json=body_upper, headers=_auth(steward_token))
    assert r2.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-08: Missing credentials → 400 with field errors
# ─────────────────────────────────────────────────────────────────────────────
def test_create_missing_credentials_returns_400(client, test_workspace_id, steward_token):
    """DS-CREATE-08: Omitting credentials entirely → 400."""
    body = {
        "source_name": "Missing Cred DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "production",
        "credentials": {},
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 400
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-09: Invalid source_type → 400
# ─────────────────────────────────────────────────────────────────────────────
def test_create_invalid_source_type_returns_400(client, test_workspace_id, steward_token):
    """DS-CREATE-09: Unknown source_type 'mongo' → 400."""
    body = {
        "source_name": "Bad Type DS",
        "source_type": "mongo",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": {"host": "db.example.com", "port": 27017},
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    field_names = [f["field"] for f in (data["error"].get("fields") or [])]
    assert "source_type" in field_names


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-10: SSRF prevention — private IP host → 400
# ─────────────────────────────────────────────────────────────────────────────
def test_create_ssrf_private_host_returns_400(client, test_workspace_id, steward_token):
    """DS-CREATE-10: Host pointing to RFC1918 address in direct mode → 400 (SSRF)."""
    body = {
        "source_name": "SSRF Test DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": {
            "host": "192.168.1.100",
            "port": 5432,
            "database": "prod",
            "username": "attacker",
            "password": "evil",
        },
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-11: Workspace from different tenant → 404
# ─────────────────────────────────────────────────────────────────────────────
def test_create_wrong_tenant_workspace_returns_404(client, steward_token):
    """DS-CREATE-11: workspace_id that belongs to a different tenant → 404."""
    other_workspace_id = uuid.uuid4()  # non-existent → definitely not in actor's tenant
    body = {
        "source_name": "Cross Tenant DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "development",
        "credentials": _pg_creds(),
    }
    resp = client.post(_url(other_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-12: BigQuery valid with service_account_json → 201
# ─────────────────────────────────────────────────────────────────────────────
def test_create_bigquery_returns_201(client, test_workspace_id, steward_token):
    """DS-CREATE-12: BigQuery source with required service_account_json → 201."""
    body = {
        "source_name": "BQ Analytics",
        "source_type": "bigquery",
        "connection_mode": "direct",
        "environment": "production",
        "credentials": _bq_creds(),
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["source_type"] == "bigquery"


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-13: Agent mode — credentials not validated for structure → 201
# ─────────────────────────────────────────────────────────────────────────────
def test_create_agent_mode_minimal_creds_returns_201(client, test_workspace_id, steward_token):
    """DS-CREATE-13: Agent mode bypasses host/port SSRF and structure checks → 201."""
    body = {
        "source_name": "Agent Mode DS",
        "source_type": "postgresql",
        "connection_mode": "agent",
        "environment": "development",
        # minimal creds — agent mode does not enforce exact structure
        "credentials": {"connection_string": "postgresql://safe_agent_host/db"},
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-14: Response NEVER returns plaintext credentials
# ─────────────────────────────────────────────────────────────────────────────
def test_create_response_has_credential_reference_not_credentials(
    client, test_workspace_id, steward_token
):
    """DS-CREATE-14: Credential payload must not appear in any response field."""
    secret_password = "super_secret_password_12345"
    body = {
        "source_name": "Secret Check DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "production",
        "credentials": {
            "host": "db.example.com",
            "port": 5432,
            "database": "prod",
            "username": "reader",
            "password": secret_password,
        },
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 201
    response_text = resp.text
    # Plaintext secret must not appear anywhere in the response
    assert secret_password not in response_text
    assert "credentials" not in resp.json()
    # credential_reference UUID must be present
    assert resp.json()["credential_reference"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# DS-CREATE-15: Description field is stored and returned
# ─────────────────────────────────────────────────────────────────────────────
def test_create_with_description_returns_description(client, test_workspace_id, steward_token):
    """DS-CREATE-15: Optional description field is persisted and returned."""
    body = {
        "source_name": "Described DS",
        "source_type": "postgresql",
        "connection_mode": "direct",
        "environment": "production",
        "credentials": _pg_creds(),
        "description": "Primary OLTP replica for reporting pipelines.",
    }
    resp = client.post(_url(test_workspace_id), json=body, headers=_auth(steward_token))
    assert resp.status_code == 201
    assert resp.json()["description"] == "Primary OLTP replica for reporting pipelines."
