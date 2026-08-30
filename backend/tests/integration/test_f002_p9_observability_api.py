"""
P09 Observability — Integration Tests
=======================================

Verifies end-to-end metric and tracing behaviour (TDD §12.1, §12.2, §12.3):

  TG-5  — X-Request-ID propagated into audit log row
  TG-11 — X-Forwarded-For parsed → source_ip stored in audit log row
  TG-13 — Non-WA POST /workspaces → workspace_create_failure_count{unauthorized}
  TG-6  — Registry failure on GET /workspaces/{id} → dataset_count metric fired

Run inside Docker:
    docker-compose exec backend python -m pytest \\
        tests/integration/test_f002_p9_observability_api.py -v

Environment variable required:
    DATABASE_URL  (set automatically in the Docker service environment)
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
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)


def _get_settings():
    from app.core.config import settings

    return settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Module-scoped TestClient — starts/stops the app once per module."""
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def test_tenant_id() -> uuid.UUID:
    """Create a test tenant for P09 and return its UUID."""
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
                %s, 'P9 Test Tenant', 'p9test-tenant',
                'active', 'us-east', 'enterprise',
                NOW(), NOW(), %s, %s, 0
            ) ON CONFLICT (tenant_slug) DO UPDATE
            SET status = 'active'
            RETURNING tenant_id
            """,
            (tenant_id, uuid.uuid4(), uuid.uuid4()),
        )
        result = cur.fetchone()
        if result:
            tenant_id = result[0]

    conn.close()
    return tenant_id


@pytest.fixture(scope="module")
def workspace_admin_token(test_tenant_id: uuid.UUID) -> str:
    """Valid workspace_administrator JWT for the test tenant."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "workspace_administrator",
        "tenant_id": str(test_tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def wrong_role_token() -> str:
    """Valid JWT with a non-WA role (platform_admin) — wrong role for create."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "tenant_id": str(uuid.uuid4()),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_data():
    """Delete all p9test-scoped rows after the module finishes."""
    yield

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM control.workspace_audit_logs
            WHERE workspace_id IN (
                SELECT workspace_id FROM control.workspaces
                WHERE workspace_slug LIKE 'p9test-%'
            )
            """
        )
        cur.execute("DELETE FROM control.workspaces WHERE workspace_slug LIKE 'p9test-%'")
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug = 'p9test-tenant'")
    conn.close()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_workspace_body(slug_suffix: str, **kwargs) -> dict:
    body: dict = {
        "workspace_name": f"P9 Test {slug_suffix}",
        "workspace_slug": f"p9test-{slug_suffix}",
        "description": "P09 observability test workspace",
    }
    body.update(kwargs)
    return body


# ---------------------------------------------------------------------------
# Helper: read audit log row from DB
# ---------------------------------------------------------------------------


def _fetch_latest_audit_log(workspace_slug: str) -> dict | None:
    """Fetch the most recent audit log row for the workspace with the given slug."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT al.request_id, al.source_ip, al.action_type,
                   al.actor_id, al.actor_role
            FROM control.workspace_audit_logs al
            JOIN control.workspaces ws USING (workspace_id)
            WHERE ws.workspace_slug = %s
            ORDER BY al.occurred_at DESC
            LIMIT 1
            """,
            (workspace_slug,),
        )
        row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ===========================================================================
# TG-5 — X-Request-ID propagated into audit log row
# ===========================================================================


class TestTG5RequestIdPropagation:
    """
    When a known UUID is passed as X-Request-ID, the same UUID must appear in
    the audit log row created for that workspace (TDD §12.3 / TG-5).
    """

    def test_request_id_stored_in_audit_log(self, client: TestClient, workspace_admin_token: str):
        """POST /workspaces with X-Request-ID → audit log row.request_id matches."""
        known_request_id = str(uuid.uuid4())
        slug = "tg5-req-id-01"

        resp = client.post(
            "/api/v1/workspaces",
            json=_create_workspace_body(slug),
            headers={
                **_auth_headers(workspace_admin_token),
                "X-Request-ID": known_request_id,
            },
        )

        assert resp.status_code == 201, resp.text

        row = _fetch_latest_audit_log(f"p9test-{slug}")
        assert row is not None, "Audit log row not found for created workspace"
        stored_id = str(row["request_id"])
        assert stored_id == known_request_id, (
            f"Audit log request_id {stored_id!r} != {known_request_id!r}"
        )

    def test_bad_request_id_still_generates_valid_uuid(
        self, client: TestClient, workspace_admin_token: str
    ):
        """A malformed X-Request-ID is silently replaced and still stored."""
        slug = "tg5-req-id-02"

        resp = client.post(
            "/api/v1/workspaces",
            json=_create_workspace_body(slug),
            headers={
                **_auth_headers(workspace_admin_token),
                "X-Request-ID": "not-a-uuid",
            },
        )
        assert resp.status_code == 201, resp.text

        row = _fetch_latest_audit_log(f"p9test-{slug}")
        assert row is not None
        # Request-ID must be a valid UUID (auto-generated replacement)
        try:
            uuid.UUID(str(row["request_id"]))
        except (ValueError, TypeError) as exc:
            pytest.fail(f"Stored request_id is not a valid UUID: {row['request_id']!r} ({exc})")


# ===========================================================================
# TG-11 — X-Forwarded-For → source_ip in audit log
# ===========================================================================


class TestTG11SourceIpPropagation:
    """
    When X-Forwarded-For is provided, the leftmost IP is extracted and stored
    as source_ip in the audit log row (TDD §12.2 / TG-11).
    """

    def test_forwarded_ip_stored_in_audit_log(self, client: TestClient, workspace_admin_token: str):
        """POST /workspaces with X-Forwarded-For → source_ip in audit log."""
        slug = "tg11-src-ip-01"
        client_ip = "1.2.3.4"

        resp = client.post(
            "/api/v1/workspaces",
            json=_create_workspace_body(slug),
            headers={
                **_auth_headers(workspace_admin_token),
                "X-Forwarded-For": f"{client_ip}, 10.0.0.1",
            },
        )
        assert resp.status_code == 201, resp.text

        row = _fetch_latest_audit_log(f"p9test-{slug}")
        assert row is not None
        assert row["source_ip"] == client_ip, f"source_ip {row['source_ip']!r} != {client_ip!r}"


# ===========================================================================
# TG-13 — Non-WA role → workspace_create_failure_count{unauthorized}
# ===========================================================================


class TestTG13UnauthorizedCreateMetric:
    """
    POST /workspaces with a non-workspace_administrator role must emit
    workspace_create_failure_count{failure_reason="unauthorized"} (TDD §12.1 / TG-13).

    The metric is emitted by verify_workspace_create_admin, which intercepts
    the 403 before the endpoint body can run.
    """

    def test_wrong_role_emits_unauthorized_metric(
        self, client: TestClient, wrong_role_token: str, caplog
    ):
        """platform_admin token → 403 + metric line in logs."""
        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.post(
                "/api/v1/workspaces",
                json=_create_workspace_body("tg13-forbidden-01"),
                headers=_auth_headers(wrong_role_token),
            )

        assert resp.status_code == 403, resp.text

        metric_logged = any(
            "workspace_create_failure_count" in r.getMessage()
            and "failure_reason=unauthorized" in r.getMessage()
            for r in caplog.records
        )
        assert metric_logged, (
            "Expected 'workspace_create_failure_count failure_reason=unauthorized' in logs. "
            f"Got records: {[r.getMessage() for r in caplog.records]}"
        )

    def test_no_auth_header_emits_unauthorized_metric(self, client: TestClient, caplog):
        """Missing Authorization header → 401 + metric."""
        with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
            resp = client.post(
                "/api/v1/workspaces",
                json=_create_workspace_body("tg13-no-auth-01"),
            )

        assert resp.status_code == 401, resp.text

        metric_logged = any(
            "workspace_create_failure_count" in r.getMessage()
            and "failure_reason=unauthorized" in r.getMessage()
            for r in caplog.records
        )
        assert metric_logged, (
            "Expected unauthorized metric on missing auth. "
            f"Got: {[r.getMessage() for r in caplog.records]}"
        )


# ===========================================================================
# TG-6 — Registry failure → dataset_count metric
# ===========================================================================


class TestTG6RegistryFailureMetric:
    """
    GET /workspaces/{id} when the dataset registry raises → must emit
    workspace_detail_count_query_failure_count{count_type="dataset_count"}
    (TDD §12.1 / TG-6).
    """

    def test_failing_registry_emits_dataset_count_metric(
        self,
        client: TestClient,
        workspace_admin_token: str,
        test_tenant_id: uuid.UUID,
        caplog,
    ):
        """Registry outage on detail request logs the count_query_failure metric."""
        from app.api.v1.endpoints.workspaces import get_workspace_service
        from app.main import app
        from app.services.workspaces.rbac import RBACServiceStub
        from app.services.workspaces.registry import DatasetRegistryStub, MemberRegistryStub
        from app.services.workspaces.repository import (
            AuditLogWriter,
            TenantRepository,
            WorkspaceRepository,
        )
        from app.services.workspaces.service import WorkspaceService

        # Create a workspace first
        slug = "tg6-registry-fail-01"
        body = _create_workspace_body(slug)
        create_resp = client.post(
            "/api/v1/workspaces",
            json=body,
            headers=_auth_headers(workspace_admin_token),
        )
        assert create_resp.status_code == 201, create_resp.text
        workspace_id = create_resp.json()["data"]["workspace_id"]

        failing_service = WorkspaceService(
            workspace_repo=WorkspaceRepository(),
            tenant_repo=TenantRepository(),
            audit_writer=AuditLogWriter(),
            rbac_service=RBACServiceStub(),
            dataset_registry=DatasetRegistryStub(raise_error=True),  # simulate outage
            member_registry=MemberRegistryStub(),
        )

        app.dependency_overrides[get_workspace_service] = lambda: failing_service
        try:
            with caplog.at_level(logging.WARNING, logger="app.services.workspaces.service"):
                with caplog.at_level(logging.INFO, logger="app.services.workspaces.metrics"):
                    resp = client.get(
                        f"/api/v1/workspaces/{workspace_id}",
                        headers=_auth_headers(workspace_admin_token),
                    )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["dataset_count"] is None

        metric_logged = any(
            "workspace_detail_count_query_failure_count" in r.getMessage()
            and "count_type=dataset_count" in r.getMessage()
            for r in caplog.records
        )
        assert metric_logged, (
            "Expected 'workspace_detail_count_query_failure_count count_type=dataset_count' "
            f"in logs. Got: {[r.getMessage() for r in caplog.records]}"
        )


# ===========================================================================
# Fire-and-forget safety — metric exception must not break the endpoint
# ===========================================================================


class TestFireAndForgetSafety:
    """
    If an emit_* function raises internally, the endpoint must still return
    its normal response (TDD §8.1 fire-and-forget contract).
    """

    def test_broken_metric_does_not_break_create(
        self,
        client: TestClient,
        workspace_admin_token: str,
        monkeypatch,
    ):
        """emit_workspace_create_success raising RuntimeError → 201 still returned."""
        import app.services.workspaces.metrics as m

        original = m.emit_workspace_create_success

        def boom(*args, **kwargs):
            raise RuntimeError("metric system down")

        monkeypatch.setattr(m, "emit_workspace_create_success", boom)

        slug = "ff-safety-01"
        try:
            resp = client.post(
                "/api/v1/workspaces",
                json=_create_workspace_body(slug),
                headers=_auth_headers(workspace_admin_token),
            )
            # fire-and-forget: the function itself catches the error, so endpoint is unaffected
            assert resp.status_code == 201, resp.text
        finally:
            monkeypatch.setattr(m, "emit_workspace_create_success", original)
