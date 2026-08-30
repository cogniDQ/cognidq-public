"""
Integration tests — F003 Packet 6: Observability Verification

Verifies that the four Prometheus-style metric log entries are emitted
under the correct conditions for the workspace settings endpoints.

Metric verification strategy: capture log records with `caplog` inside
the Docker integration test runtime, confirming the expected log message
appears after each operation.

Run:
    docker exec dq-backend-1 python -m pytest \
        tests/integration/test_f003_p06_observability.py -v
"""

from __future__ import annotations

import logging
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

_SLUG_PREFIX = "p6obs-"

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _settings_cfg():
    from app.core.config import settings

    return settings


def _make_token(tenant_id: uuid.UUID, role: str) -> str:
    s = _settings_cfg()
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


def _create_workspace(tenant_id: uuid.UUID, slug: str, status: str = "active") -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    workspace_id = uuid.uuid4()
    actor = uuid.uuid4()
    with conn.cursor() as cur:
        status_reason = "Archived for test" if status == "archived" else None
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone,
                status, status_reason, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s,
                'P6 obs test workspace', 'UTC',
                %s, %s, NOW(), NOW(), %s, %s, 0
            )
            """,
            (
                workspace_id,
                tenant_id,
                f"P6 Obs {slug}",
                f"p6 obs {slug}",
                slug,
                status,
                status_reason,
                actor,
                actor,
            ),
        )
    conn.close()
    return workspace_id


def _do_cleanup():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM control.workspace_audit_logs
            WHERE workspace_id IN (
                SELECT workspace_id FROM control.workspaces
                WHERE workspace_slug LIKE %s
            )
            """,
            (_SLUG_PREFIX + "%",),
        )
        cur.execute(
            "DELETE FROM control.workspaces WHERE workspace_slug LIKE %s",
            (_SLUG_PREFIX + "%",),
        )
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p6obs-%'")
    conn.close()


def _get_url(ws_id: uuid.UUID) -> str:
    return f"/api/v1/workspaces/{ws_id}/settings"


def _patch_url(ws_id: uuid.UUID) -> str:
    return f"/api/v1/workspaces/{ws_id}/settings"


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
    return _create_tenant("p6obs-main-tenant")


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    _do_cleanup()
    yield
    _do_cleanup()


# ---------------------------------------------------------------------------
# Helpers to search captured log records
# ---------------------------------------------------------------------------


def _has_log(records, fragment: str) -> bool:
    return any(fragment in r.getMessage() for r in records)


# ---------------------------------------------------------------------------
# TC01 — GET /settings → workspace_settings_read_count emitted
# ---------------------------------------------------------------------------


class TestGetSettingsMetric:
    def test_read_success_metric_emitted(self, client: TestClient, tenant_id: uuid.UUID, caplog):
        """TC01: Successful GET → workspace_settings_read_count logged."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc01-read")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.get(_get_url(ws_id), headers=_auth(token))

        assert resp.status_code == 200
        assert _has_log(caplog.records, "workspace_settings_read_count +1"), (
            f"Expected 'workspace_settings_read_count +1' in logs. "
            f"Got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_read_failure_no_read_metric(self, client: TestClient, tenant_id: uuid.UUID, caplog):
        """TC02: Failed GET (404) → read metric NOT emitted."""
        token = _make_token(tenant_id, "workspace_administrator")
        ghost_id = uuid.uuid4()

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.get(_get_url(ghost_id), headers=_auth(token))

        assert resp.status_code == 404
        assert not _has_log(caplog.records, "workspace_settings_read_count"), (
            "Read metric should NOT fire on 404"
        )


# ---------------------------------------------------------------------------
# TC03 — PATCH /settings (real update) → workspace_settings_update_count emitted
# ---------------------------------------------------------------------------


class TestPatchUpdateMetric:
    def test_update_success_metric_emitted(self, client: TestClient, tenant_id: uuid.UUID, caplog):
        """TC03: Successful PATCH with change → workspace_settings_update_count logged."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc03-upd")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={"timezone_policy": {"default_timezone": "Europe/London"}},
            )

        assert resp.status_code == 200
        assert _has_log(caplog.records, "workspace_settings_update_count"), (
            f"Expected 'workspace_settings_update_count' in logs. "
            f"Got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_update_metric_includes_changed_fields_label(
        self, client: TestClient, tenant_id: uuid.UUID, caplog
    ):
        """TC04: changed_fields label contains the updated domain name."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc04-fields")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={"timezone_policy": {"default_timezone": "Asia/Tokyo"}},
            )

        assert resp.status_code == 200
        # The field should be "default_timezone" (field name inside the update obj)
        relevant = [
            r.getMessage()
            for r in caplog.records
            if "workspace_settings_update_count" in r.getMessage()
        ]
        assert len(relevant) >= 1
        assert "default_timezone" in relevant[0]


# ---------------------------------------------------------------------------
# TC05 — PATCH /settings (no-op) → workspace_settings_noop_count emitted
# ---------------------------------------------------------------------------


class TestPatchNoopMetric:
    def test_noop_metric_emitted(self, client: TestClient, tenant_id: uuid.UUID, caplog):
        """TC05: PATCH with no actual change → workspace_settings_noop_count logged."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc05-noop")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            # UTC is the default — sending it back right away is guaranteed no-op
            resp = client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={"timezone_policy": {"default_timezone": "UTC"}},
            )

        assert resp.status_code == 200
        assert _has_log(caplog.records, "workspace_settings_noop_count +1"), (
            f"Expected 'workspace_settings_noop_count +1' in logs. "
            f"Got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_noop_does_not_emit_update_count(
        self, client: TestClient, tenant_id: uuid.UUID, caplog
    ):
        """TC06: PATCH no-op → update_count NOT emitted (only noop_count)."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc06-noop2")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={"timezone_policy": {"default_timezone": "UTC"}},
            )

        assert not _has_log(caplog.records, "workspace_settings_update_count"), (
            "update_count should NOT fire for a no-op"
        )


# ---------------------------------------------------------------------------
# TC07 — PATCH failures → workspace_settings_update_failure_count emitted
# ---------------------------------------------------------------------------


class TestPatchFailureMetric:
    def test_validation_error_emits_failure_metric(
        self, client: TestClient, tenant_id: uuid.UUID, caplog
    ):
        """TC07: Invalid timezone → failure metric with 'validation_error' reason."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc07-badinput")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={"timezone_policy": {"default_timezone": "Not/Real"}},
            )

        assert resp.status_code == 422
        assert _has_log(caplog.records, "workspace_settings_update_failure_count"), (
            f"Expected failure metric. Got: {[r.getMessage() for r in caplog.records]}"
        )

    def test_workspace_not_found_emits_failure_metric(
        self, client: TestClient, tenant_id: uuid.UUID, caplog
    ):
        """TC08: 404 workspace → failure metric with 'workspace_not_found' reason."""
        token = _make_token(tenant_id, "workspace_administrator")
        ghost_id = uuid.uuid4()

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.patch(
                _patch_url(ghost_id),
                headers=_auth(token),
                json={"timezone_policy": {"default_timezone": "UTC"}},
            )

        assert resp.status_code == 404
        assert _has_log(caplog.records, "workspace_settings_update_failure_count"), (
            f"Expected failure metric. Got: {[r.getMessage() for r in caplog.records]}"
        )
        assert _has_log(caplog.records, "workspace_not_found")

    def test_empty_request_emits_failure_metric(
        self, client: TestClient, tenant_id: uuid.UUID, caplog
    ):
        """TC09: Empty body → failure metric with 'missing_required_field' reason."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc09-empty")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={},
            )

        assert resp.status_code == 422
        assert _has_log(caplog.records, "workspace_settings_update_failure_count")
        assert _has_log(caplog.records, "missing_required_field")

    def test_unknown_field_emits_failure_metric(
        self, client: TestClient, tenant_id: uuid.UUID, caplog
    ):
        """TC10: Unknown field → failure metric with 'validation_error' reason."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc10-unk")
        token = _make_token(tenant_id, "workspace_administrator")

        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.patch(
                _patch_url(ws_id),
                headers=_auth(token),
                json={"unknown_key": "value"},
            )

        assert resp.status_code == 422
        assert _has_log(caplog.records, "workspace_settings_update_failure_count")
        assert _has_log(caplog.records, "validation_error")
