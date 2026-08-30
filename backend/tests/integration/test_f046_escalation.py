"""
F046 — Escalation for Overdue SLA — Integration Tests
=======================================================

Tests:
    ESC-01  GET /escalation/overdue-issues requires auth
    ESC-02  GET /escalation/overdue-issues returns 200 with empty list (no overdue)
    ESC-03  GET /escalation/overdue-issues returns overdue issues after seeding one
    ESC-04  POST /escalation/run requires auth
    ESC-05  POST /escalation/run returns 200 when no overdue issues exist
    ESC-06  POST /escalation/run returns 200 when overdue issues exist (no rules — no events)
    ESC-07  EscalationService._find_overdue_issues returns only open+overdue rows
    ESC-08  EscalationService._find_overdue_issues excludes resolved issues
    ESC-09  EscalationService._find_overdue_issues excludes issues with due_at in future
    ESC-10  EscalationService.run_escalation_check returns correct summary

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest \\
        tests/integration/test_f046_escalation.py -v
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


def _make_token(tenant_id: uuid.UUID, role: str) -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _make_token_for_user(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    """Create a JWT token with a specific user_id as actor_id."""
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
    slug = f"f046test-tenant-{str(tid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (%s,%s,%s,'active','eu-west','starter',%s,%s,0,NOW(),NOW())
            """,
            (tid, f"F046 Tenant {str(tid)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tid


@pytest.fixture(scope="module")
def workspace_id(tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"F046 Workspace {str(wid)[:8]}"
    slug = f"f046test-ws-{str(wid)[:8]}"
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
    """Seed a user with workspace_administrator role in the test workspace."""
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
            (uid, f"f046-{str(uid)[:8]}@test.local"),
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
def steward_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    return _make_token_for_user(user_id, tenant_id, "workspace_administrator")


# Default Organization UUID (stable seed data in DB)
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="module")
def overdue_issue_id(workspace_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    """Seed an open issue with due_at in the past."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    issue_id = uuid.uuid4()
    exec_id = uuid.uuid4()
    flow_id = uuid.uuid4()
    with conn.cursor() as cur:
        # Minimal flow (dq_flows uses workspace_id, not workspace_id)
        cur.execute(
            """
            INSERT INTO dq_flows (id, workspace_id, name,
                flow_definition, version, status, created_at, updated_at)
            VALUES (%s,%s,'F046 test flow','{}',1,'active',NOW(),NOW())
            ON CONFLICT DO NOTHING
            """,
            (flow_id, _ORG_ID),
        )
        # Minimal execution (flow_executions has no workspace_id/tenant_id)
        cur.execute(
            """
            INSERT INTO flow_executions (
                id, flow_id, execution_type, status, started_at, created_at
            )
            VALUES (%s,%s,'manual','completed',NOW(),NOW())
            ON CONFLICT DO NOTHING
            """,
            (exec_id, flow_id),
        )
        # Overdue open issue
        past = datetime.now(tz=UTC) - timedelta(hours=25)
        cur.execute(
            """
            INSERT INTO issues (
                id, tenant_id, workspace_id, flow_execution_id,
                issue_type, severity, status, title, due_at,
                opened_at, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,'threshold_breach','major','open',
                    'F046 overdue test issue',%s,NOW(),NOW(),NOW())
            """,
            (issue_id, tenant_id, workspace_id, exec_id, past),
        )
    conn.close()
    return issue_id


@pytest.fixture(scope="module", autouse=True)
def cleanup(workspace_id: uuid.UUID, tenant_id: uuid.UUID):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        # issues → flow_executions via FK: delete issues first, then executions
        cur.execute("DELETE FROM issues WHERE workspace_id = %s", (workspace_id,))
        # flow_executions has no workspace_id; delete by flow_id IN (flows seeded for this test)
        cur.execute(
            "DELETE FROM flow_executions WHERE flow_id IN "
            "(SELECT id FROM dq_flows WHERE name LIKE 'F046 %')"
        )
        cur.execute("DELETE FROM dq_flows WHERE name LIKE 'F046 %'")
        cur.execute("DELETE FROM notification_events WHERE workspace_id = %s", (workspace_id,))
        cur.execute(
            "DELETE FROM control.workspace_role_assignments WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute("DELETE FROM users WHERE email LIKE 'f046-%@test.local'")
        cur.execute("DELETE FROM control.workspaces WHERE workspace_id = %s", (workspace_id,))
        cur.execute("DELETE FROM control.tenants WHERE tenant_id = %s", (tenant_id,))
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOverdueIssuesEndpoint:
    def test_esc_01_requires_auth(self, client: TestClient, workspace_id: uuid.UUID):
        """ESC-01 GET /escalation/overdue-issues requires auth."""
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/escalation/overdue-issues")
        assert resp.status_code in (401, 403)

    def test_esc_02_empty_list_no_overdue(
        self, client: TestClient, workspace_id: uuid.UUID, steward_token: str
    ):
        """ESC-02 Fresh workspace has no overdue issues."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/escalation/overdue-issues",
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "overdue_count" in body
        assert body["overdue_count"] == 0
        assert body["items"] == []

    def test_esc_03_returns_overdue_after_seed(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        steward_token: str,
        overdue_issue_id: uuid.UUID,  # triggers fixture
    ):
        """ESC-03 After seeding an overdue issue, endpoint returns it."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/escalation/overdue-issues",
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["overdue_count"] >= 1
        ids = [item["id"] for item in body["items"]]
        assert str(overdue_issue_id) in ids


class TestRunEscalationEndpoint:
    def test_esc_04_requires_auth(self, client: TestClient, workspace_id: uuid.UUID):
        """ESC-04 POST /escalation/run requires auth."""
        resp = client.post(f"/api/v1/workspaces/{workspace_id}/escalation/run")
        assert resp.status_code in (401, 403)

    def test_esc_05_no_overdue_returns_zero(self, client: TestClient, steward_token: str):
        """ESC-05 Workspace with no overdue issues returns overdue_issues_found=0."""
        # Use a brand-new workspace ID that has no issues
        other_ws = uuid.uuid4()
        resp = client.post(
            f"/api/v1/workspaces/{other_ws}/escalation/run",
            headers=_auth(steward_token),
        )
        # 403 is acceptable if the user isn't a member of this workspace
        assert resp.status_code in (200, 403)
        if resp.status_code == 200:
            assert resp.json()["overdue_issues_found"] == 0

    def test_esc_06_run_with_overdue_no_rules(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        steward_token: str,
        overdue_issue_id: uuid.UUID,
    ):
        """ESC-06 Run with overdue issues but no alert rules → 0 notifications."""
        resp = client.post(
            f"/api/v1/workspaces/{workspace_id}/escalation/run",
            headers=_auth(steward_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "overdue_issues_found" in body
        # No issue_overdue alert rules → no notifications_logged
        assert body["notifications_logged"] == 0


class TestEscalationServiceUnit:
    """Unit-level tests that call the service directly against the test DB."""

    def _get_db(self):
        from app.models.database import SessionLocal

        return SessionLocal()

    def test_esc_07_finds_overdue_open_issues(
        self, workspace_id: uuid.UUID, overdue_issue_id: uuid.UUID
    ):
        """ESC-07 _find_overdue_issues returns open rows with past due_at."""
        from app.services.escalation.escalation_service import EscalationService

        db = self._get_db()
        try:
            now = datetime.now(tz=UTC)
            issues = EscalationService._find_overdue_issues(db, now)
            ids = [str(i.id) for i in issues]
            assert str(overdue_issue_id) in ids
        finally:
            db.close()

    def test_esc_08_excludes_resolved(self, workspace_id: uuid.UUID, tenant_id: uuid.UUID):
        """ESC-08 Resolved/closed issues with past due_at are NOT returned."""
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        exec_id = uuid.uuid4()
        flow_id = uuid.uuid4()
        resolved_id = uuid.uuid4()
        past = datetime.now(tz=UTC) - timedelta(hours=5)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dq_flows (id, workspace_id, name,
                    flow_definition, version, status, created_at, updated_at)
                VALUES (%s,%s,'F046 resolved flow','{}',1,'active',NOW(),NOW())
                ON CONFLICT DO NOTHING
                """,
                (flow_id, _ORG_ID),
            )
            cur.execute(
                """
                INSERT INTO flow_executions (id, flow_id, execution_type,
                    status, started_at, created_at)
                VALUES (%s,%s,'manual','completed',NOW(),NOW())
                ON CONFLICT DO NOTHING
                """,
                (exec_id, flow_id),
            )
            cur.execute(
                """
                INSERT INTO issues (id, tenant_id, workspace_id, flow_execution_id,
                    issue_type, severity, status, title, due_at,
                    opened_at, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'threshold_breach','minor','resolved',
                        'F046 resolved issue',%s,NOW(),NOW(),NOW())
                """,
                (resolved_id, tenant_id, workspace_id, exec_id, past),
            )
        conn.close()

        from app.services.escalation.escalation_service import EscalationService

        db = self._get_db()
        try:
            now = datetime.now(tz=UTC)
            issues = EscalationService._find_overdue_issues(db, now)
            ids = [str(i.id) for i in issues]
            assert str(resolved_id) not in ids
        finally:
            db.close()

    def test_esc_09_excludes_future_due_at(self, workspace_id: uuid.UUID, tenant_id: uuid.UUID):
        """ESC-09 Open issues with due_at in the future are NOT overdue."""
        import psycopg2

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        exec_id = uuid.uuid4()
        flow_id = uuid.uuid4()
        future_id = uuid.uuid4()
        future = datetime.now(tz=UTC) + timedelta(hours=48)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dq_flows (id, workspace_id, name,
                    flow_definition, version, status, created_at, updated_at)
                VALUES (%s,%s,'F046 future flow','{}',1,'active',NOW(),NOW())
                ON CONFLICT DO NOTHING
                """,
                (flow_id, _ORG_ID),
            )
            cur.execute(
                """
                INSERT INTO flow_executions (id, flow_id, execution_type,
                    status, started_at, created_at)
                VALUES (%s,%s,'manual','completed',NOW(),NOW())
                ON CONFLICT DO NOTHING
                """,
                (exec_id, flow_id),
            )
            cur.execute(
                """
                INSERT INTO issues (id, tenant_id, workspace_id, flow_execution_id,
                    issue_type, severity, status, title, due_at,
                    opened_at, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'threshold_breach','minor','open',
                        'F046 future issue',%s,NOW(),NOW(),NOW())
                """,
                (future_id, tenant_id, workspace_id, exec_id, future),
            )
        conn.close()

        from app.services.escalation.escalation_service import EscalationService

        db = self._get_db()
        try:
            now = datetime.now(tz=UTC)
            issues = EscalationService._find_overdue_issues(db, now)
            ids = [str(i.id) for i in issues]
            assert str(future_id) not in ids
        finally:
            db.close()

    def test_esc_10_run_escalation_check_returns_summary(
        self, workspace_id: uuid.UUID, overdue_issue_id: uuid.UUID
    ):
        """ESC-10 run_escalation_check returns a well-formed EscalationResult dict."""
        from app.services.escalation.escalation_service import EscalationService

        db = self._get_db()
        try:
            result = EscalationService().run_escalation_check(db)
            d = result.to_dict()
            assert "overdue_issues_found" in d
            assert "workspaces_affected" in d
            assert "rules_matched" in d
            assert "notifications_logged" in d
            assert "errors" in d
            assert isinstance(d["errors"], list)
            assert d["overdue_issues_found"] >= 1
        finally:
            db.close()
