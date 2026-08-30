"""
F004 Packet 8 — Observability Verification tests
=================================================

Tests: OBS-01 through OBS-11

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest tests/integration/test_f004_p08_observability.py -v
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
from prometheus_client import REGISTRY

psycopg2.extras.register_uuid()

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

BASE_URL = "/api/v1/workspaces/{workspace_id}/data-sources"


def _get_settings():
    from app.core.config import settings

    return settings


def _get_counter_value(metric_name: str, labels: dict) -> float:
    """Read a prometheus counter total value from the default registry."""
    # prometheus_client counters expose a _total sample
    for metric in REGISTRY.collect():
        if metric.name == metric_name:
            for sample in metric.samples:
                if sample.name == f"{metric_name}_total" and sample.labels == labels:
                    return sample.value
    return 0.0


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
    slug = f"p08test-ds-tenant-{str(tenant_id)[:8]}"
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
            (tenant_id, f"P08 Test Tenant {str(tenant_id)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def test_workspace_id(test_tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = "P08 Data Source Test WS"
    slug = f"p08test-ds-ws-{str(wid)[:8]}"
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


def _post_url(workspace_id: uuid.UUID) -> str:
    return BASE_URL.format(workspace_id=workspace_id)


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
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestObservability:
    def test_obs01_create_success_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-01: data_source_create_count increments with result=success after create."""
        labels = {
            "workspace_id": str(test_workspace_id),
            "source_type": "postgresql",
            "result": "success",
        }
        before = _get_counter_value("data_source_create_count", labels)
        _create_source(client, test_workspace_id, steward_token)
        after = _get_counter_value("data_source_create_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs02_create_validation_error_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-02: data_source_create_count increments with result=validation_error on 400."""
        # Use an invalid source_type to trigger validation error
        invalid_source_type = "invalid_db_type"
        labels = {
            "workspace_id": str(test_workspace_id),
            "source_type": invalid_source_type,
            "result": "validation_error",
        }
        before = _get_counter_value("data_source_create_count", labels)
        resp = client.post(
            _post_url(test_workspace_id),
            json={
                "source_name": f"obs02-{uuid.uuid4().hex[:6]}",
                "source_type": invalid_source_type,
                "connection_mode": "direct",
                "environment": "staging",
                "credentials": _pg_creds(),
            },
            headers=_auth(steward_token),
        )
        assert resp.status_code == 400, resp.text
        after = _get_counter_value("data_source_create_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs03_create_conflict_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-03: data_source_create_count increments with result=conflict on 409."""
        name = f"obs03-dup-{uuid.uuid4().hex[:6]}"
        labels = {
            "workspace_id": str(test_workspace_id),
            "source_type": "postgresql",
            "result": "conflict",
        }
        # Create first
        _create_source(client, test_workspace_id, steward_token, name=name)
        before = _get_counter_value("data_source_create_count", labels)
        # Duplicate attempt
        resp = client.post(
            _post_url(test_workspace_id),
            json={
                "source_name": name,
                "source_type": "postgresql",
                "connection_mode": "direct",
                "environment": "staging",
                "credentials": _pg_creds(),
            },
            headers=_auth(steward_token),
        )
        assert resp.status_code == 409, resp.text
        after = _get_counter_value("data_source_create_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs04_update_success_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-04: data_source_update_count increments with result=success."""
        ds = _create_source(client, test_workspace_id, steward_token)
        labels = {
            "workspace_id": str(test_workspace_id),
            "result": "success",
        }
        before = _get_counter_value("data_source_update_count", labels)
        resp = client.patch(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}",
            json={"environment": "production"},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        after = _get_counter_value("data_source_update_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs05_archive_success_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-05: data_source_archive_count increments with result=success."""
        ds = _create_source(client, test_workspace_id, steward_token)
        labels = {
            "workspace_id": str(test_workspace_id),
            "result": "success",
        }
        before = _get_counter_value("data_source_archive_count", labels)
        resp = client.post(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/archive",
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        after = _get_counter_value("data_source_archive_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs06_restore_success_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-06: data_source_restore_count increments with result=success."""
        ds = _create_source(client, test_workspace_id, steward_token)
        # Archive first
        client.post(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/archive",
            headers=_auth(steward_token),
        )
        labels = {
            "workspace_id": str(test_workspace_id),
            "result": "success",
        }
        before = _get_counter_value("data_source_restore_count", labels)
        resp = client.post(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/restore",
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text
        after = _get_counter_value("data_source_restore_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs07_test_connection_reachable_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-07: data_source_test_connection_count increments with result=reachable."""
        ds = _create_source(client, test_workspace_id, steward_token)
        labels = {
            "workspace_id": str(test_workspace_id),
            "source_type": "postgresql",
            "result": "reachable",
        }
        before = _get_counter_value("data_source_test_connection_count", labels)
        mock_conn = MagicMock()
        with patch("psycopg2.connect", return_value=mock_conn):
            resp = client.post(
                f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/test-connection",
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "reachable"
        after = _get_counter_value("data_source_test_connection_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs08_test_connection_unreachable_increments_counter(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-08: data_source_test_connection_count increments with result=unreachable."""
        ds = _create_source(client, test_workspace_id, steward_token)
        labels = {
            "workspace_id": str(test_workspace_id),
            "source_type": "postgresql",
            "result": "unreachable",
        }
        before = _get_counter_value("data_source_test_connection_count", labels)
        with patch(
            "psycopg2.connect",
            side_effect=psycopg2.OperationalError("connection refused"),
        ):
            resp = client.post(
                f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/test-connection",
                headers=_auth(steward_token),
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "unreachable"
        after = _get_counter_value("data_source_test_connection_count", labels)
        assert after > before, f"Counter did not increment: before={before}, after={after}"

    def test_obs09_create_audit_log_has_no_password(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-09: audit log data_source_created details contain no password key."""
        secret_pw = f"my-very-secret-{uuid.uuid4().hex}"
        body = {
            "source_name": f"obs09-{uuid.uuid4().hex[:6]}",
            "source_type": "postgresql",
            "connection_mode": "direct",
            "environment": "staging",
            "credentials": _pg_creds(password=secret_pw),
        }
        resp = client.post(_post_url(test_workspace_id), json=body, headers=_auth(steward_token))
        assert resp.status_code == 201, resp.text
        ds_id = resp.json()["data_source_id"]

        audit_resp = client.get(
            f"{_post_url(test_workspace_id)}/{ds_id}/audit-logs",
            headers=_auth(steward_token),
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json().get("items", [])
        create_events = [e for e in items if "created" in e.get("action_type", "")]
        assert len(create_events) >= 1

        for event in create_events:
            new_data = event.get("new_data") or {}
            assert "password" not in new_data, f"password key found in audit: {new_data}"
            # Also ensure the actual password value is not anywhere in the serialized data
            audit_str = str(new_data)
            assert secret_pw not in audit_str, f"Secret password found in audit log: {audit_str}"

    def test_obs10_update_audit_log_has_no_credential_fields(
        self, client: TestClient, test_workspace_id: uuid.UUID, steward_token: str
    ):
        """OBS-10: audit log data_source_updated details contain no credential fields."""
        secret_pw = f"new-secret-{uuid.uuid4().hex}"
        ds = _create_source(client, test_workspace_id, steward_token)
        # Update with credential rotation
        resp = client.patch(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}",
            json={"credentials": _pg_creds(password=secret_pw)},
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200, resp.text

        audit_resp = client.get(
            f"{_post_url(test_workspace_id)}/{ds['data_source_id']}/audit-logs",
            headers=_auth(steward_token),
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json().get("items", [])
        update_events = [e for e in items if "updated" in e.get("action_type", "")]
        assert len(update_events) >= 1

        for event in update_events:
            new_data = event.get("new_data") or {}
            audit_str = str(new_data)
            for field in ("password", "private_key", "service_account_json"):
                assert field not in new_data, (
                    f"Credential field '{field}' found in audit: {new_data}"
                )
            assert secret_pw not in audit_str, "Secret password found in audit log"

    def test_obs11_all_five_metrics_have_correct_label_set(self):
        """OBS-11: all five metrics use correct label set per TDD §10."""
        from app.services.data_sources import metrics as ds_metrics

        # data_source_create_count: workspace_id, source_type, result
        assert set(ds_metrics.data_source_create_count._labelnames) == {
            "workspace_id",
            "source_type",
            "result",
        }
        # data_source_update_count: workspace_id, result
        assert set(ds_metrics.data_source_update_count._labelnames) == {"workspace_id", "result"}
        # data_source_archive_count: workspace_id, result
        assert set(ds_metrics.data_source_archive_count._labelnames) == {"workspace_id", "result"}
        # data_source_restore_count: workspace_id, result
        assert set(ds_metrics.data_source_restore_count._labelnames) == {"workspace_id", "result"}
        # data_source_test_connection_count: workspace_id, source_type, result
        assert set(ds_metrics.data_source_test_connection_count._labelnames) == {
            "workspace_id",
            "source_type",
            "result",
        }
