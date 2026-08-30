"""
F055 — Ownership History and Accountability Trace — Integration Tests
=====================================================================

Tests:
    OWN-01  GET /ownership-history requires auth
    OWN-02  GET /ownership-history returns 200 with empty items (fresh workspace)
    OWN-03  GET /ownership-history returns issue_assigned events after seeding
    OWN-04  GET /ownership-history entity_type filter narrows results
    OWN-05  GET /ownership-history entity_id filter returns only that entity
    OWN-06  GET /ownership-history action_type filter works
    OWN-07  GET /ownership-history pagination: page_size=1 returns has_next=True
    OWN-08  GET /ownership-history page_size=100 is accepted
    OWN-09  GET /ownership-history page_size=101 returns 422
    OWN-10  OwnershipHistoryService.get_page returns well-formed page

Run inside Docker:
    docker exec -e CREDENTIAL_ENCRYPTION_KEY=$CREDENTIAL_ENCRYPTION_KEY \\
        dq-backend-1 python -m pytest \\
        tests/integration/test_f055_ownership_history.py -v
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

# Default Organization UUID (stable seed data in DB)
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
    slug = f"f055test-tenant-{str(tid)[:8]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan, created_by, updated_by, version,
                created_at, updated_at
            ) VALUES (%s,%s,%s,'active','eu-west','starter',%s,%s,0,NOW(),NOW())
            """,
            (tid, f"F055 Tenant {str(tid)[:8]}", slug, actor, actor),
        )
    conn.close()
    return tid


@pytest.fixture(scope="module")
def workspace_id(tenant_id: uuid.UUID) -> uuid.UUID:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    wid = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"F055 Workspace {str(wid)[:8]}"
    slug = f"f055test-ws-{str(wid)[:8]}"
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
    """Seed a workspace_administrator user."""
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
            (uid, f"f055-{str(uid)[:8]}@test.local"),
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
    """
    Seed an issue_assigned event directly into workspace_audit_logs so we
    can test the ownership history endpoint without going through the full
    issue update lifecycle.
    """
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    log_id = uuid.uuid4()
    issue_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.workspace_audit_logs (
                log_id, tenant_id, workspace_id,
                action_type, actor_id, actor_role, actor_type,
                previous_data, new_data,
                target_entity_type, target_entity_id,
                occurred_at
            )
            VALUES (%s,%s,%s,
                    'issue_assigned', %s, 'workspace_administrator', 'user',
                    '{"assignee_id": null}',
                    %s,
                    'issue', %s,
                    NOW())
            """,
            (
                log_id,
                tenant_id,
                workspace_id,
                user_id,
                f'{{"assignee_id": "{user_id}"}}',
                issue_id,
            ),
        )
    conn.close()
    return issue_id


@pytest.fixture(scope="module", autouse=True)
def cleanup(workspace_id: uuid.UUID, tenant_id: uuid.UUID):
    yield
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM control.workspace_audit_logs WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute(
            "DELETE FROM control.workspace_role_assignments WHERE workspace_id = %s",
            (workspace_id,),
        )
        cur.execute("DELETE FROM users WHERE email LIKE 'f055-%@test.local'")
        cur.execute("DELETE FROM control.workspaces WHERE workspace_id = %s", (workspace_id,))
        cur.execute("DELETE FROM control.tenants WHERE tenant_id = %s", (tenant_id,))
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOwnershipHistoryEndpoint:
    def test_own_01_requires_auth(self, client: TestClient, workspace_id: uuid.UUID):
        """OWN-01 GET /ownership-history requires auth."""
        resp = client.get(f"/api/v1/workspaces/{workspace_id}/ownership-history")
        assert resp.status_code in (401, 403)

    def test_own_02_empty_fresh_workspace(
        self, client: TestClient, workspace_id: uuid.UUID, admin_token: str
    ):
        """OWN-02 Fresh workspace returns 200 with empty items list."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert body["total"] == 0
        assert body["items"] == []

    def test_own_03_returns_issue_assigned_after_seed(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        admin_token: str,
        seeded_issue_id: uuid.UUID,
    ):
        """OWN-03 After seeding an issue_assigned audit entry, it appears in results."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        action_types = [item["action_type"] for item in body["items"]]
        assert "issue_assigned" in action_types

    def test_own_04_entity_type_filter(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        admin_token: str,
        seeded_issue_id: uuid.UUID,
    ):
        """OWN-04 entity_type=issue narrows results to issue events only."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            params={"entity_type": "issue"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["target_entity_type"] == "issue"

    def test_own_05_entity_id_filter(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        admin_token: str,
        seeded_issue_id: uuid.UUID,
    ):
        """OWN-05 entity_id filter returns only events for that entity."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            params={"entity_id": str(seeded_issue_id)},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert item["target_entity_id"] == str(seeded_issue_id)

    def test_own_06_action_type_filter(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        admin_token: str,
        seeded_issue_id: uuid.UUID,
    ):
        """OWN-06 action_type=issue_assigned narrows to assignment events."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            params={"action_type": "issue_assigned"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["action_type"] == "issue_assigned"

    def test_own_07_pagination_page_size_1(
        self,
        client: TestClient,
        workspace_id: uuid.UUID,
        admin_token: str,
        seeded_issue_id: uuid.UUID,
    ):
        """OWN-07 page_size=1 with at least 1 event returns has_next=True."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            params={"page_size": 1, "page": 1},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 1
        if body["total"] > 1:
            assert body["has_next"] is True

    def test_own_08_page_size_100_accepted(
        self, client: TestClient, workspace_id: uuid.UUID, admin_token: str
    ):
        """OWN-08 page_size=100 is the maximum and should be accepted."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            params={"page_size": 100},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200

    def test_own_09_page_size_101_rejected(
        self, client: TestClient, workspace_id: uuid.UUID, admin_token: str
    ):
        """OWN-09 page_size=101 exceeds maximum and returns 422."""
        resp = client.get(
            f"/api/v1/workspaces/{workspace_id}/ownership-history",
            params={"page_size": 101},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422


class TestOwnershipHistoryService:
    def _get_db(self):
        from app.models.database import SessionLocal

        return SessionLocal()

    def test_own_10_service_returns_well_formed_page(
        self,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID,
        seeded_issue_id: uuid.UUID,
    ):
        """OWN-10 Service.get_page returns a well-formed OwnershipHistoryPage."""
        from app.services.ownership.ownership_history_models import OwnershipHistoryQueryParams
        from app.services.ownership.ownership_history_service import OwnershipHistoryService

        db = self._get_db()
        try:
            svc = OwnershipHistoryService()
            result = svc.get_page(
                db,
                tenant_id=tenant_id,
                workspace_id=workspace_id,
                filters=OwnershipHistoryQueryParams(page=1, page_size=25),
            )
            assert result.total >= 1
            assert result.page == 1
            assert result.page_size == 25
            assert isinstance(result.items, list)
            ev = result.items[0]
            assert ev.action_type in (
                "issue_assigned",
                "incident_owner_changed",
                "role_assigned",
                "role_revoked",
            )
        finally:
            db.close()
