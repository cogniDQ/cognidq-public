"""
Integration tests — F003 Packet 5: PATCH /api/v1/workspaces/{id}/settings

Tests run inside Docker against the real PostgreSQL database.
The DB trigger (trg_workspace_settings_on_insert) auto-creates the
workspace_settings row, so all tests start with defaults in place.

Run:
    docker exec dq-backend-1 python -m pytest \
        tests/integration/test_f003_p05_patch_settings_api.py -v
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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/dataquality_db",
)

_SLUG_PREFIX = "p5set-"

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _settings_cfg():
    from app.core.config import settings

    return settings


def _make_token(tenant_id: uuid.UUID, role: str, actor_id: uuid.UUID | None = None) -> str:
    s = _settings_cfg()
    payload = {
        "actor_id": str(actor_id or uuid.uuid4()),
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
        cur.execute(
            """
            INSERT INTO control.workspaces (
                workspace_id, tenant_id, workspace_name, workspace_name_lower,
                workspace_slug, description, default_timezone,
                status, status_reason, created_at, updated_at, created_by, updated_by, version
            ) VALUES (
                %s, %s, %s, %s, %s,
                'P5 settings test workspace', 'UTC',
                %s, CASE WHEN %s = 'archived' THEN 'Test archived workspace' ELSE NULL END,
                NOW(), NOW(), %s, %s, 0
            )
            """,
            (
                workspace_id,
                tenant_id,
                f"P5 Settings {slug}",
                f"p5 settings {slug}",
                slug,
                status,
                status,
                actor,
                actor,
            ),
        )
    conn.close()
    return workspace_id


def _audit_count(workspace_id: uuid.UUID, action_type: str = "workspace_settings_updated") -> int:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM control.workspace_audit_logs
            WHERE workspace_id = %s AND action_type = %s
            """,
            (workspace_id, action_type),
        )
        count = cur.fetchone()[0]
    conn.close()
    return count


def _patch_url(workspace_id: uuid.UUID) -> str:
    return f"/api/v1/workspaces/{workspace_id}/settings"


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
    return _create_tenant("p5set-main-tenant")


@pytest.fixture(scope="module")
def other_tenant_id() -> uuid.UUID:
    return _create_tenant("p5set-other-tenant")


def _do_cleanup():
    """Delete all test rows for this module (safe to call multiple times)."""
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
        cur.execute(
            "DELETE FROM control.tenants WHERE tenant_slug LIKE 'p5set-%'",
        )
    conn.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    _do_cleanup()  # pre-clean any stale data from aborted prior runs
    yield
    _do_cleanup()  # post-clean


# ---------------------------------------------------------------------------
# TC01 — Happy path: PATCH timezone_policy → 200
# ---------------------------------------------------------------------------


class TestPatchTimezonePolicy:
    def test_update_timezone_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC01: WA updates timezone_policy → 200 with new value."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc01-tz")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "America/New_York"}},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["timezone_policy"]["default_timezone"] == "America/New_York"

    def test_update_timezone_writes_audit_log(self, client: TestClient, tenant_id: uuid.UUID):
        """TC02: Successful PATCH → audit log row created."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc02-audit")
        token = _make_token(tenant_id, "workspace_administrator")
        before = _audit_count(ws_id)

        client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "Europe/London"}},
        )

        assert _audit_count(ws_id) == before + 1

    def test_response_contains_full_settings_shape(self, client: TestClient, tenant_id: uuid.UUID):
        """TC03: 200 response contains all required top-level fields."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc03-shape")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "Asia/Tokyo"}},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        for key in (
            "workspace_id",
            "tenant_id",
            "timezone_policy",
            "severity_policy",
            "sla_policy",
            "issue_grouping_policy",
            "naming_standards",
            "updated_at",
            "updated_by",
        ):
            assert key in data, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# TC04 — Happy path: PATCH severity_policy
# ---------------------------------------------------------------------------


class TestPatchSeverityPolicy:
    def test_update_severity_labels_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC04: WA updates severity_policy → 200 with new labels."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc04-sev")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={
                "severity_policy": {
                    "critical_label": "P0",
                    "major_label": "P1",
                    "minor_label": "P2",
                    "informational_label": "P3",
                }
            },
        )

        assert resp.status_code == 200
        sp = resp.json()["data"]["severity_policy"]
        assert sp["critical_label"] == "P0"
        assert sp["major_label"] == "P1"
        assert sp["minor_label"] == "P2"
        assert sp["informational_label"] == "P3"


# ---------------------------------------------------------------------------
# TC05 — Happy path: PATCH sla_policy
# ---------------------------------------------------------------------------


class TestPatchSlaPolicy:
    def test_update_sla_hours_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC05: WA updates sla_policy → 200 with new hours."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc05-sla")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={
                "sla_policy": {
                    "critical_hours": 2,
                    "major_hours": 12,
                    "minor_hours": 48,
                    "informational_hours": 96,
                }
            },
        )

        assert resp.status_code == 200
        sla = resp.json()["data"]["sla_policy"]
        assert sla["critical_hours"] == 2
        assert sla["major_hours"] == 12
        assert sla["minor_hours"] == 48
        assert sla["informational_hours"] == 96

    def test_sla_informational_hours_can_be_null(self, client: TestClient, tenant_id: uuid.UUID):
        """TC06: informational_hours omitted → null/None accepted."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc06-sla-null")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={
                "sla_policy": {
                    "critical_hours": 3,
                    "major_hours": 18,
                    "minor_hours": 60,
                }
            },
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["sla_policy"]["informational_hours"] is None


# ---------------------------------------------------------------------------
# TC07 — Happy path: PATCH issue_grouping_policy
# ---------------------------------------------------------------------------


class TestPatchIssueGroupingPolicy:
    def test_update_grouping_mode_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC07: WA updates issue_grouping_policy → 200 with new mode."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc07-igp")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"issue_grouping_policy": "one_per_rule"},
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["issue_grouping_policy"] == "one_per_rule"


# ---------------------------------------------------------------------------
# TC08 — Happy path: PATCH naming_standards
# ---------------------------------------------------------------------------


class TestPatchNamingStandards:
    def test_update_naming_standards_datasets_200(self, client: TestClient, tenant_id: uuid.UUID):
        """TC08: WA updates naming_standards.datasets → 200."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc08-ns")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={
                "naming_standards": {
                    "datasets": {
                        "required_prefix": "ds_",
                        "max_length": 64,
                    },
                    "rules": {},
                }
            },
        )

        assert resp.status_code == 200
        ns = resp.json()["data"]["naming_standards"]
        assert ns["datasets"]["required_prefix"] == "ds_"
        assert ns["datasets"]["max_length"] == 64


# ---------------------------------------------------------------------------
# TC09 — No-op: resending identical values → 200, no new audit row
# ---------------------------------------------------------------------------


class TestNoOp:
    def test_noop_same_default_timezone_no_audit(self, client: TestClient, tenant_id: uuid.UUID):
        """TC09: PATCH with the current stored value → 200, no audit row written."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc09-noop")
        token = _make_token(tenant_id, "workspace_administrator")

        # Initial PATCH to set a known value
        client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "Europe/Paris"}},
        )
        after_first = _audit_count(ws_id)

        # Second PATCH with the same value → no-op
        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "Europe/Paris"}},
        )

        assert resp.status_code == 200
        assert _audit_count(ws_id) == after_first  # no new audit row

    def test_noop_returns_full_settings(self, client: TestClient, tenant_id: uuid.UUID):
        """TC10: No-op → still returns full settings shape in response."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc10-noop-shape")
        token = _make_token(tenant_id, "workspace_administrator")
        # UTC is the default — sending it back is guaranteed no-op
        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "workspace_id" in data
        assert "timezone_policy" in data


# ---------------------------------------------------------------------------
# TC11 — Validation errors
# ---------------------------------------------------------------------------


class TestValidationErrors:
    def test_invalid_timezone_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC11: unrecognised timezone string → 422 with timezone field error."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc11-badtz")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "Invalid/Timezone"}},
        )

        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] is not None

    def test_invalid_sla_ordering_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC12: critical_hours > major_hours → 422 ordering violation."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc12-sla-order")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={
                "sla_policy": {
                    "critical_hours": 100,
                    "major_hours": 10,
                    "minor_hours": 1,
                }
            },
        )

        assert resp.status_code == 422

    def test_invalid_grouping_mode_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC13: unrecognised grouping mode → 422."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc13-igp-bad")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"issue_grouping_policy": "by_unicorn"},
        )

        assert resp.status_code == 422

    def test_empty_severity_label_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC14: empty severity label string → 422."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc14-sev-empty")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={
                "severity_policy": {
                    "critical_label": "",
                    "major_label": "Major",
                    "minor_label": "Minor",
                    "informational_label": "Info",
                }
            },
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# TC15 — Unknown fields / empty request
# ---------------------------------------------------------------------------


class TestUnknownFieldsAndEmptyRequest:
    def test_unknown_top_level_field_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC15: unknown top-level key → 422 with error.code == 'unknown_fields'."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc15-unk")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"rogue_field": "value"},
        )

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "unknown_fields"

    def test_empty_body_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC16: empty JSON object → 422 with error.code == 'empty_request'."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc16-empty")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={},
        )

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "empty_request"


# ---------------------------------------------------------------------------
# TC17 — Authorization errors
# ---------------------------------------------------------------------------


class TestAuthorizationErrors:
    def test_no_token_returns_401(self, client: TestClient, tenant_id: uuid.UUID):
        """TC17: no Authorization header → 401."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc17-noauth")

        resp = client.patch(
            _patch_url(ws_id),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 401

    def test_platform_admin_patch_returns_403(self, client: TestClient, tenant_id: uuid.UUID):
        """TC18: platform_admin PATCH → 403 (write not allowed for platform operators)."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc18-pa-403")
        token = _make_token(tenant_id, "platform_admin")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 403

    def test_platform_viewer_patch_returns_403(self, client: TestClient, tenant_id: uuid.UUID):
        """TC19: platform_viewer PATCH → 403."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc19-pv-403")
        token = _make_token(tenant_id, "platform_viewer")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 403

    def test_data_engineer_patch_returns_403(self, client: TestClient, tenant_id: uuid.UUID):
        """TC20: data_engineer PATCH → 403 (read-only role)."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc20-de-403")
        token = _make_token(tenant_id, "data_engineer")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 403

    def test_cross_tenant_returns_404(
        self, client: TestClient, tenant_id: uuid.UUID, other_tenant_id: uuid.UUID
    ):
        """TC21: WA from different tenant → 404 (tenant isolation)."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc21-cross")
        # Token belongs to other tenant
        token = _make_token(other_tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# TC22 — Archived workspace
# ---------------------------------------------------------------------------


class TestArchivedWorkspace:
    def test_patch_archived_workspace_returns_422(self, client: TestClient, tenant_id: uuid.UUID):
        """TC22: PATCH on archived workspace → 422 with workspace_not_active."""
        ws_id = _create_workspace(tenant_id, _SLUG_PREFIX + "tc22-arch", status="archived")
        token = _make_token(tenant_id, "workspace_administrator")

        resp = client.patch(
            _patch_url(ws_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "workspace_not_active"


# ---------------------------------------------------------------------------
# TC23 — Workspace not found
# ---------------------------------------------------------------------------


class TestWorkspaceNotFound:
    def test_patch_nonexistent_workspace_returns_404(
        self, client: TestClient, tenant_id: uuid.UUID
    ):
        """TC23: PATCH on random UUID that doesn't exist → 404."""
        token = _make_token(tenant_id, "workspace_administrator")
        ghost_id = uuid.uuid4()

        resp = client.patch(
            _patch_url(ghost_id),
            headers=_auth(token),
            json={"timezone_policy": {"default_timezone": "UTC"}},
        )

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "workspace_not_found"
