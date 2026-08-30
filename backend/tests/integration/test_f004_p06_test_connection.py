"""
F004 Packet 6 — Test Connection API tests
==========================================

POST /api/v1/workspaces/{workspace_id}/data-sources/{data_source_id}/test-connection

Test IDs: TEST-01 through TEST-10

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest tests/integration/test_f004_p06_test_connection.py -v
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

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
    slug = f"p06test-ds-tenant-{str(tenant_id)[:8]}"
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
            (tenant_id, f"P06 Test Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "P06 Data Source Test WS"
    slug = f"p06test-ds-ws-{str(wid)[:8]}"
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


def _pg_creds(password: str = "s3cr3t") -> dict:
    return {
        "host": "db.example.com",
        "port": 5432,
        "database": "sales",
        "username": "reader",
        "password": password,
    }


def _mysql_creds() -> dict:
    return {
        "host": "mysql.example.com",
        "port": 3306,
        "database": "sales",
        "username": "reader",
        "password": "mysecret",
    }


def _snowflake_creds() -> dict:
    return {
        "account_identifier": "xy12345.eu-west",
        "account": "xy12345.eu-west",
        "warehouse": "COMPUTE_WH",
        "database": "PROD",
        "username": "svc_reader",
        "password": "snow_pw",
    }


def _bigquery_creds() -> dict:
    import json

    sa_json = json.dumps(
        {
            "type": "service_account",
            "project_id": "my-gcp-project",
            "private_key_id": "kid123",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5JJcds3xHn/ygWep4VCQtKhvhCkGCQQFGZZfNNDSmrQ\n-----END RSA PRIVATE KEY-----",  # gitleaks:allow - stub key for BigQuery connector test
            "client_email": "svc@my-gcp-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    )
    return {
        "project_id": "my-gcp-project",
        "dataset": "analytics",
        "service_account_json": sa_json,
    }


def _post_url(workspace_id: uuid.UUID) -> str:
    return BASE_URL.format(workspace_id=workspace_id)


def _test_url(workspace_id: uuid.UUID, data_source_id: str) -> str:
    return f"{BASE_URL.format(workspace_id=workspace_id)}/{data_source_id}/test-connection"


def _create_source(
    client: TestClient,
    workspace_id: uuid.UUID,
    steward_token: str,
    name: str | None = None,
    source_type: str = "postgresql",
    connection_mode: str = "direct",
    credentials: dict | None = None,
) -> dict:
    if credentials is None:
        credentials = _pg_creds()
    body = {
        "source_name": name or f"test-source-{str(uuid.uuid4())[:8]}",
        "source_type": source_type,
        "connection_mode": connection_mode,
        "environment": "staging",
        "credentials": credentials,
    }
    resp = client.post(
        _post_url(workspace_id),
        json=body,
        headers=_auth(steward_token),
    )
    assert resp.status_code == 201, f"Setup failed: {resp.text}"
    return resp.json()


def _archive_source_direct(workspace_id: uuid.UUID, data_source_id: str) -> None:
    """Archive a data source directly via DB for test setup."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE control.data_sources
            SET status = 'archived', archived_at = NOW(), archived_by = gen_random_uuid()
            WHERE data_source_id = %s AND workspace_id = %s
            """,
            (uuid.UUID(data_source_id), workspace_id),
        )
    conn.close()


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


class TestTestConnection:
    def test_test01_postgresql_socket_success(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-01: postgresql with mocked psycopg2.connect success → status: reachable."""
        ds = _create_source(client, test_workspace_id, steward_token, source_type="postgresql")
        mock_conn = MagicMock()
        with patch("psycopg2.connect", return_value=mock_conn):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "reachable"
        assert body["tested_at"] is not None
        assert body["error_summary"] is None
        mock_conn.close.assert_called_once()

    def test_test02_postgresql_operational_error(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-02: psycopg2.connect raises OperationalError → status: unreachable."""
        ds = _create_source(client, test_workspace_id, steward_token, source_type="postgresql")
        with patch(
            "psycopg2.connect",
            side_effect=psycopg2.OperationalError("FATAL: password authentication failed"),
        ):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "unreachable"
        assert body["error_summary"] is not None

    def test_test03_mysql_connection_refused(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-03: mysql socket raises ConnectionRefusedError → status: test_failed."""
        ds = _create_source(
            client,
            test_workspace_id,
            steward_token,
            source_type="mysql",
            credentials=_mysql_creds(),
        )
        with patch(
            "socket.create_connection",
            side_effect=ConnectionRefusedError("Connection refused"),
        ):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "test_failed"

    def test_test04_snowflake_timeout(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-04: snowflake socket times out → status: test_failed, CONNECTION_TIMEOUT."""
        import socket as _socket

        ds = _create_source(
            client,
            test_workspace_id,
            steward_token,
            source_type="snowflake",
            credentials=_snowflake_creds(),
        )
        with patch(
            "socket.create_connection",
            side_effect=TimeoutError("timed out"),
        ):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "test_failed"
        assert body["error_summary"] is not None
        assert "CONNECTION_TIMEOUT" in (body["error_summary"] or "")

    def test_test05_bigquery_socket_success(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-05: bigquery socket mocked to succeed → status: reachable."""
        ds = _create_source(
            client,
            test_workspace_id,
            steward_token,
            source_type="bigquery",
            credentials=_bigquery_creds(),
        )
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=mock_ctx):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "reachable"

    def test_test06_agent_mode_not_supported(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-06: connection_mode=agent → test_failed, AGENT_MODE_NOT_SUPPORTED."""
        ds = _create_source(
            client,
            test_workspace_id,
            steward_token,
            source_type="postgresql",
            connection_mode="agent",
        )
        resp = client.post(
            _test_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "test_failed"
        assert body["error_summary"] == "AGENT_MODE_NOT_SUPPORTED"

    def test_test07_archived_source_returns_409(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-07: POST /test-connection on archived source → 409."""
        ds = _create_source(client, test_workspace_id, steward_token)
        _archive_source_direct(test_workspace_id, ds["data_source_id"])
        resp = client.post(
            _test_url(test_workspace_id, ds["data_source_id"]),
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        # Error response shape: {"error": {"code": "...", "message": "..."}}
        err = body.get("error", {})
        assert err.get("code") == "DATA_SOURCE_ARCHIVED"

    def test_test08_error_summary_no_password(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-08: error_summary from failed test does not contain the password value."""
        secret_password = f"my-secret-pass-{uuid.uuid4().hex[:8]}"
        ds = _create_source(
            client,
            test_workspace_id,
            steward_token,
            source_type="postgresql",
            credentials=_pg_creds(password=secret_password),
        )
        with patch(
            "psycopg2.connect",
            side_effect=psycopg2.OperationalError(
                f"FATAL: password authentication failed for user '{secret_password}'"
            ),
        ):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert secret_password not in (body.get("error_summary") or "")

    def test_test09_audit_log_records_connection_tested(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-09: Audit log records data_source_connection_tested with outcome."""
        ds = _create_source(client, test_workspace_id, steward_token)
        mock_conn = MagicMock()
        with patch("psycopg2.connect", return_value=mock_conn):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text

        # Check audit log
        audit_resp = client.get(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/audit-logs",
            headers=_auth(steward_token),
        )
        assert audit_resp.status_code == 200
        audit_items = audit_resp.json().get("items", [])
        test_events = [e for e in audit_items if "connection_tested" in e.get("action_type", "")]
        assert len(test_events) >= 1
        assert test_events[0]["new_data"].get("outcome") is not None

    def test_test10_last_tested_at_set(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """TEST-10: last_tested_at is set to a recent timestamp after test."""
        ds = _create_source(client, test_workspace_id, steward_token)
        before = datetime.now(tz=UTC)

        mock_conn = MagicMock()
        with patch("psycopg2.connect", return_value=mock_conn):
            resp = client.post(
                _test_url(test_workspace_id, ds["data_source_id"]),
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        tested_at = datetime.fromisoformat(body["tested_at"].replace("Z", "+00:00"))
        assert tested_at >= before

        # Also verify last_tested_at is set on the data source record
        detail_resp = client.get(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}",
            headers=_auth(steward_token),
        )
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["last_tested_at"] is not None
        assert detail["last_test_status"] == "reachable"
