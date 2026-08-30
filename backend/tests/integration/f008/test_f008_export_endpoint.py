"""
F008 P02 — Integration tests: GET /workspaces/{workspace_id}/audit/permissions/export
======================================================================================

Tests the permission audit CSV export endpoint via FastAPI TestClient + real
PostgreSQL database.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/f008/test_f008_export_endpoint.py -v

Tests cover ACs:
  AC-P02-009  200, correct content-type, correct Content-Disposition header
  AC-P02-010  CSV header row matches spec (_EXPORT_COLUMNS)
  AC-P02-011  Truncation notice row appended when repo returns > 10 000 rows
              (tested via unit-level service mock to avoid inserting 10 001 rows)
  AC-P02-012  Formula-injection escaping: leading '=' prefixed with single quote
  AC-P02-002  403 without view_audit_logs permission
"""

from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient

psycopg2.extras.register_uuid()

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)

API_PREFIX = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers (mirrored from the list endpoint test module)
# ---------------------------------------------------------------------------


def _get_settings():
    from app.core.config import settings

    return settings


def _make_token(actor_id: uuid.UUID, role: str, tenant_id: uuid.UUID) -> str:
    from jose import jwt

    s = _get_settings()
    payload = {
        "actor_id": str(actor_id),
        "actor_role": role,
        "tenant_id": str(tenant_id),
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _new_tenant(cur) -> uuid.UUID:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug,
            status, region, plan,
            created_by, updated_by, version, created_at, updated_at
        ) VALUES (
            %s, %s, %s, 'active', 'eu-west', 'starter',
            %s, %s, 0, NOW(), NOW()
        )
        """,
        (tid, f"T-{tid}", f"t-{str(tid)[:8]}", actor, actor),
    )
    return tid


def _new_workspace(cur, tenant_id: uuid.UUID) -> uuid.UUID:
    ws_id = uuid.uuid4()
    actor = uuid.uuid4()
    name = f"WS-{ws_id}"
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id, workspace_name, workspace_name_lower,
            workspace_slug, status, default_timezone,
            created_at, updated_at, created_by, updated_by, version
        ) VALUES (
            %s, %s, %s, %s, %s, 'active', 'UTC',
            NOW(), NOW(), %s, %s, 0
        )
        """,
        (ws_id, tenant_id, name, name.lower(), f"ws-{str(ws_id)[:8]}", actor, actor),
    )
    return ws_id


def _new_user(cur, full_name: str | None = None) -> uuid.UUID:
    uid = uuid.uuid4()
    cur.execute(
        "INSERT INTO users (id, email, full_name, status) VALUES (%s, %s, %s, 'active')",
        (uid, f"user-{uid}@test.example", full_name),
    )
    return uid


def _insert_role(cur, workspace_id, user_id, role_name, granted_by=None):
    ra_id = uuid.uuid4()
    cur.execute(
        """
        INSERT INTO control.workspace_role_assignments
            (id, workspace_id, user_id, role_name, granted_by)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (ra_id, workspace_id, user_id, role_name, granted_by),
    )


def _insert_audit_log(
    cur,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    action_type: str,
    actor_id: uuid.UUID | None = None,
    actor_role: str = "workspace_administrator",
    actor_type: str = "user",
    target_entity_type: str | None = None,
    target_entity_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
) -> uuid.UUID:
    log_id = uuid.uuid4()
    ts = occurred_at or datetime.now(tz=UTC)
    cur.execute(
        """
        INSERT INTO control.workspace_audit_logs (
            log_id, tenant_id, workspace_id,
            action_type, actor_id, actor_role, actor_type,
            target_entity_type, target_entity_id,
            new_data, occurred_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, %s)
        """,
        (
            log_id,
            tenant_id,
            workspace_id,
            action_type,
            actor_id,
            actor_role,
            actor_type,
            target_entity_type,
            target_entity_id,
            ts,
        ),
    )
    return log_id


def _parse_csv(content: bytes) -> list[dict[str, str]]:
    """Decode UTF-8-BOM response and parse all rows including truncation notices."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _export_url(ws_id: uuid.UUID) -> str:
    return f"{API_PREFIX}/workspaces/{ws_id}/audit/permissions/export"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture()
def cur(db_conn):
    """Autocommit cursor — inserts are committed immediately so the HTTP
    handler's separate DB connection can see the test data."""
    cursor = db_conn.cursor()
    yield cursor
    cursor.close()


# ---------------------------------------------------------------------------
# AC-P02-009: 200, content-type, content-disposition
# ---------------------------------------------------------------------------


class TestExportPermissionAudit200:
    def test_returns_200_with_correct_headers(self, client, cur):
        """200 + text/csv content-type + filename attachment."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")
        _insert_audit_log(cur, tid, ws_id, "role_assigned", actor_id=actor_id)

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            _export_url(ws_id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert "text/csv" in resp.headers.get("content-type", "")
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "permission_audit_" in disposition

    def test_bom_bytes_present_at_start_of_response(self, client, cur):
        """Response body must start with UTF-8 BOM bytes 0xEF 0xBB 0xBF."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            _export_url(ws_id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.content[:3] == b"\xef\xbb\xbf", (
            f"Expected UTF-8 BOM at start of response, got: {resp.content[:3]!r}"
        )


# ---------------------------------------------------------------------------
# AC-P02-010: Header row matches spec
# ---------------------------------------------------------------------------


class TestExportHeaderRow:
    def test_csv_header_row_matches_export_columns(self, client, cur):
        """First row of the CSV must exactly match _EXPORT_COLUMNS."""
        from app.services.permission_audit.service import _EXPORT_COLUMNS

        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        token = _make_token(actor_id, "workspace_administrator", tid)
        resp = client.get(
            _export_url(ws_id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        # Decode with BOM and extract header line
        text = resp.content.decode("utf-8-sig")
        header_line = text.splitlines()[0]
        headers = [h.strip() for h in header_line.split(",")]
        assert headers == list(_EXPORT_COLUMNS), (
            f"Header mismatch.\nGot:      {headers}\nExpected: {list(_EXPORT_COLUMNS)}"
        )


# ---------------------------------------------------------------------------
# AC-P02-002: 403 without view_audit_logs
# ---------------------------------------------------------------------------


class TestExportPermissionAudit403:
    def test_returns_403_for_data_engineer(self, client, cur):
        """data_engineer lacks view_audit_logs → 403."""
        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "data_engineer")

        token = _make_token(actor_id, "data_engineer", tid)
        resp = client.get(
            _export_url(ws_id),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# AC-P02-011: Truncation notice row (tested via service mock)
# ---------------------------------------------------------------------------


class TestExportTruncation:
    def test_truncation_notice_row_appended_when_limit_exceeded(self, client, cur):
        """
        When the repository returns 10 001 rows (i.e. hit the hard cap),
        the service appends a notice row and the CSV endpoint includes it.

        Inserting 10 001 rows in the integration test DB is prohibitively slow,
        so we mock ``PermissionAuditRepository.get_export_rows`` to return
        a list of 10 001 minimal row-dicts and verify the endpoint appends the
        truncation notice row.
        """
        from app.services.permission_audit.service import _EXPORT_COLUMNS

        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        # Build 10 001 fake repository rows (minimal required fields)
        fake_rows = [
            {
                "log_id": str(uuid.uuid4()),
                "occurred_at": datetime.now(tz=UTC).isoformat(),
                "action_type": "role_assigned",
                "actor_id": str(actor_id),
                "actor_display_name": None,
                "actor_role": "workspace_administrator",
                "actor_type": "user",
                "target_entity_type": None,
                "target_entity_id": None,
                "target_display_name": None,
                "workspace_id": str(ws_id),
                "request_id": None,
            }
            for _ in range(10_001)
        ]

        repo_path = (
            "app.services.permission_audit.repository.PermissionAuditRepository.export_entries"
        )
        with patch(repo_path, return_value=fake_rows):
            token = _make_token(actor_id, "workspace_administrator", tid)
            resp = client.get(
                _export_url(ws_id),
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        rows = _parse_csv(resp.content)
        # Last row must be the truncation notice
        last_row = rows[-1]
        first_col_value = last_row.get(_EXPORT_COLUMNS[0], "")
        assert first_col_value.startswith("# NOTE:"), (
            f"Expected truncation notice in last row, got: {first_col_value!r}"
        )
        # Exactly 10 000 data rows (truncated) + 1 notice = 10 001 rows total
        assert len(rows) == 10_001, f"Expected 10001 rows, got {len(rows)}"


# ---------------------------------------------------------------------------
# AC-P02-012: Formula injection escaping
# ---------------------------------------------------------------------------


class TestExportFormulaInjectionEscaping:
    def test_formula_injection_escaped_in_csv_output(self, client, cur):
        """
        actor_role starting with '=' is prefixed with single quote in the CSV.

        We use a mock here because inserting an actor_role that starts with '='
        would fail the check constraint on workspace_audit_logs.actor_role.
        Instead, we bypass the DB layer and verify the service escaping logic
        as observed through the HTTP response.
        """
        from app.services.permission_audit.service import _EXPORT_COLUMNS

        tid = _new_tenant(cur)
        ws_id = _new_workspace(cur, tid)
        actor_id = _new_user(cur)
        _insert_role(cur, ws_id, actor_id, "workspace_administrator")

        # Single fake row with an '='-prefixed actor_role
        fake_rows = [
            {
                "log_id": str(uuid.uuid4()),
                "occurred_at": datetime.now(tz=UTC).isoformat(),
                "action_type": "role_assigned",
                "actor_id": str(actor_id),
                "actor_display_name": None,
                "actor_role": "=INJECTED",
                "actor_type": "user",
                "target_entity_type": None,
                "target_entity_id": None,
                "target_display_name": None,
                "workspace_id": str(ws_id),
                "request_id": None,
            }
        ]

        repo_path = (
            "app.services.permission_audit.repository.PermissionAuditRepository.export_entries"
        )
        with patch(repo_path, return_value=fake_rows):
            token = _make_token(actor_id, "workspace_administrator", tid)
            resp = client.get(
                _export_url(ws_id),
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200, resp.text
        rows = _parse_csv(resp.content)
        assert len(rows) == 1
        escaped_role = rows[0].get("actor_role", "")
        assert escaped_role == "'=INJECTED", (
            f"Expected formula injection to be escaped. Got: {escaped_role!r}"
        )
