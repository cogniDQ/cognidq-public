"""
Packet 8 — API contract + integration tests: GET /api/v1/tenants/{tenant_id}/audit-logs
=========================================================================================

Tests cover:
    • Happy path           — 200 OK, correct envelope, all 9 log fields
    • Ordering             — results returned DESC by occurred_at
    • Filters              — event_type, actor_id, from, to, combinations
    • Pagination           — correct LIMIT/OFFSET, total, page, page_size, has_next
    • Access control       — 401 / 403 / 200 (viewer and admin both get 200)
    • Path parameter       — 400 for malformed / non-UUID strings
    • Not-found            — 404 for valid UUID with no matching tenant row
    • Query param errors   — 422 invalid_uuid_format, invalid_date_range, validation_error

Test isolation
--------------
Most tests create their own tenant rows and audit log rows (function scope)
and clean them up after.  Module-scoped fixtures provide the test client and
JWT tokens only.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/integration/test_f001_p8_audit_logs_api.py -v
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Dict, Optional

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

_P8_SLUG_PREFIX = "p8test-"
_BASE = "/api/v1/tenants"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_settings():
    from app.core.config import settings

    return settings


def _make_token(role: str) -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": role,
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _audit_url(tenant_id: str) -> str:
    return f"{_BASE}/{tenant_id}/audit-logs"


def _conn():
    return psycopg2.connect(DATABASE_URL)


def _insert_tenant(
    *,
    slug: str,
    name: str,
    status: str = "draft",
    plan: str = "starter",
    region: str = "eu-west",
    actor_id: str | None = None,
) -> str:
    """Insert a tenant row and return the generated tenant_id string."""
    tid = str(uuid.uuid4())
    aid = actor_id or str(uuid.uuid4())
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, region, plan,
                    created_by, updated_by, version
                ) VALUES (
                    %s, %s, %s,
                    %s::control.tenant_status_enum,
                    %s::control.tenant_region_enum,
                    %s::control.tenant_plan_enum,
                    %s, %s, %s
                )
                """,
                (tid, name, slug, status, region, plan, aid, aid, 0),
            )
        conn.commit()
    finally:
        conn.close()
    return tid


def _insert_audit_log(
    *,
    tenant_id: str,
    event_type: str = "tenant_created",
    actor_id: str | None = None,
    actor_role: str = "platform_admin",
    previous_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
    reason: str | None = None,
) -> str:
    """Insert a row into control.tenant_audit_logs; return the log_id string."""
    log_id = str(uuid.uuid4())
    aid = actor_id or str(uuid.uuid4())
    ts = occurred_at or datetime.now(tz=UTC)
    nd = new_data or {"tenant_name": "Test Tenant"}
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO control.tenant_audit_logs (
                    log_id, tenant_id, event_type,
                    actor_id, actor_role,
                    previous_data, new_data,
                    occurred_at, reason
                ) VALUES (
                    %s::uuid, %s::uuid, %s,
                    %s::uuid, %s,
                    %s::jsonb, %s::jsonb,
                    %s, %s
                )
                """,
                (
                    log_id,
                    tenant_id,
                    event_type,
                    aid,
                    actor_role,
                    json.dumps(previous_data) if previous_data is not None else None,
                    json.dumps(nd),
                    ts,
                    reason,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return log_id


def _cleanup_tenants_by_slug_prefix(prefix: str) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM control.tenant_audit_logs WHERE tenant_id IN "
                "(SELECT tenant_id FROM control.tenants WHERE tenant_slug LIKE %s)",
                (f"{prefix}%",),
            )
            cur.execute(
                "DELETE FROM control.outbox_events WHERE tenant_id IN "
                "(SELECT tenant_id FROM control.tenants WHERE tenant_slug LIKE %s)",
                (f"{prefix}%",),
            )
            cur.execute(
                "DELETE FROM control.tenants WHERE tenant_slug LIKE %s",
                (f"{prefix}%",),
            )
        conn.commit()
    finally:
        conn.close()


def _make_slug(suffix: str) -> str:
    return f"{_P8_SLUG_PREFIX}{suffix}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _make_token("platform_admin")


@pytest.fixture(scope="module")
def viewer_token() -> str:
    return _make_token("platform_viewer")


@pytest.fixture(scope="module")
def customer_token() -> str:
    return _make_token("customer_actor")


# ===========================================================================
# TestHappyPath
# ===========================================================================


class TestHappyPath:
    """200 OK with correct response envelope and field shapes."""

    def test_empty_log_returns_200(self, client, admin_token):
        slug = _make_slug("empty")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            assert resp.status_code == 200
            body = resp.json()
            assert body["data"] == []
            assert body["meta"]["total"] == 0
            assert body["meta"]["page"] == 1
            assert body["meta"]["page_size"] == 25
            assert body["meta"]["has_next"] is False
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_five_logs_returned_with_correct_total(self, client, admin_token):
        slug = _make_slug("five")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            for _ in range(5):
                _insert_audit_log(tenant_id=tid)
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["data"]) == 5
            assert body["meta"]["total"] == 5
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_log_object_has_nine_required_fields(self, client, admin_token):
        slug = _make_slug("fields")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            _insert_audit_log(tenant_id=tid, event_type="tenant_created")
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            assert resp.status_code == 200
            log = resp.json()["data"][0]
            expected = {
                "log_id",
                "tenant_id",
                "event_type",
                "actor_id",
                "actor_role",
                "previous_data",
                "new_data",
                "occurred_at",
                "reason",
            }
            assert set(log.keys()) == expected
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_previous_data_is_null_for_tenant_created(self, client, admin_token):
        slug = _make_slug("prevnull")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            _insert_audit_log(
                tenant_id=tid,
                event_type="tenant_created",
                previous_data=None,
            )
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            log = resp.json()["data"][0]
            assert log["previous_data"] is None
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_occurred_at_is_iso8601_string(self, client, admin_token):
        slug = _make_slug("iso")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            _insert_audit_log(tenant_id=tid)
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            log = resp.json()["data"][0]
            datetime.fromisoformat(log["occurred_at"].replace("Z", "+00:00"))
        finally:
            _cleanup_tenants_by_slug_prefix(slug)


# ===========================================================================
# TestOrdering
# ===========================================================================


class TestOrdering:
    """Results are ordered by occurred_at DESC (most recent first)."""

    def test_ordering_desc_by_occurred_at(self, client, admin_token):
        slug = _make_slug("order")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            base_ts = datetime.now(tz=UTC)
            for i in range(3):
                _insert_audit_log(
                    tenant_id=tid,
                    occurred_at=base_ts + timedelta(seconds=i),
                )
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            assert resp.status_code == 200
            logs = resp.json()["data"]
            assert len(logs) == 3
            # occurred_at strings should be in descending order
            times = [datetime.fromisoformat(l["occurred_at"].replace("Z", "+00:00")) for l in logs]
            assert times == sorted(times, reverse=True)
        finally:
            _cleanup_tenants_by_slug_prefix(slug)


# ===========================================================================
# TestFilters
# ===========================================================================


class TestFilters:
    """event_type, actor_id, from, to filters."""

    def test_filter_by_event_type_returns_only_matching(self, client, admin_token):
        slug = _make_slug("et")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            _insert_audit_log(tenant_id=tid, event_type="tenant_created")
            _insert_audit_log(tenant_id=tid, event_type="tenant_updated")
            _insert_audit_log(tenant_id=tid, event_type="tenant_status_changed")

            resp = client.get(
                _audit_url(tid),
                params={"event_type": "tenant_updated"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["meta"]["total"] == 1
            assert all(l["event_type"] == "tenant_updated" for l in body["data"])
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_filter_by_actor_id_returns_only_matching(self, client, admin_token):
        slug = _make_slug("acid")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        target_actor = str(uuid.uuid4())
        try:
            _insert_audit_log(tenant_id=tid, actor_id=target_actor)
            _insert_audit_log(tenant_id=tid, actor_id=str(uuid.uuid4()))

            resp = client.get(
                _audit_url(tid),
                params={"actor_id": target_actor},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["meta"]["total"] == 1
            assert body["data"][0]["actor_id"] == target_actor
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_filter_by_from_excludes_earlier_logs(self, client, admin_token):
        slug = _make_slug("from")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        base = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
        try:
            _insert_audit_log(
                tenant_id=tid,
                occurred_at=base - timedelta(days=1),
            )
            _insert_audit_log(
                tenant_id=tid,
                occurred_at=base + timedelta(days=1),
            )

            from_str = base.isoformat().replace("+00:00", "Z")
            resp = client.get(
                _audit_url(tid),
                params={"from": from_str},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["meta"]["total"] == 1
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_filter_by_to_excludes_later_logs(self, client, admin_token):
        slug = _make_slug("to")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        cutoff = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
        try:
            _insert_audit_log(
                tenant_id=tid,
                occurred_at=cutoff - timedelta(days=1),
            )
            _insert_audit_log(
                tenant_id=tid,
                occurred_at=cutoff + timedelta(days=1),
            )

            to_str = cutoff.isoformat().replace("+00:00", "Z")
            resp = client.get(
                _audit_url(tid),
                params={"to": to_str},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["meta"]["total"] == 1
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_combined_event_type_and_actor_id_filter(self, client, admin_token):
        slug = _make_slug("combo")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        target_actor = str(uuid.uuid4())
        try:
            # Should match: correct event_type AND correct actor
            _insert_audit_log(
                tenant_id=tid,
                event_type="tenant_updated",
                actor_id=target_actor,
            )
            # Should NOT match: wrong event_type
            _insert_audit_log(
                tenant_id=tid,
                event_type="tenant_created",
                actor_id=target_actor,
            )
            # Should NOT match: wrong actor
            _insert_audit_log(
                tenant_id=tid,
                event_type="tenant_updated",
                actor_id=str(uuid.uuid4()),
            )

            resp = client.get(
                _audit_url(tid),
                params={"event_type": "tenant_updated", "actor_id": target_actor},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            assert resp.json()["meta"]["total"] == 1
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_no_filters_returns_all_entries(self, client, admin_token):
        slug = _make_slug("nofilter")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            for et in ["tenant_created", "tenant_updated", "tenant_status_changed"]:
                _insert_audit_log(tenant_id=tid, event_type=et)
            resp = client.get(_audit_url(tid), headers=_auth(admin_token))
            assert resp.status_code == 200
            assert resp.json()["meta"]["total"] == 3
        finally:
            _cleanup_tenants_by_slug_prefix(slug)


# ===========================================================================
# TestPagination
# ===========================================================================


class TestPagination:
    """LIMIT/OFFSET pagination with total count and has_next."""

    def test_page_size_limits_results(self, client, admin_token):
        slug = _make_slug("ps")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            for _ in range(10):
                _insert_audit_log(tenant_id=tid)
            resp = client.get(
                _audit_url(tid),
                params={"page_size": "3"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["data"]) == 3
            assert body["meta"]["total"] == 10
            assert body["meta"]["has_next"] is True
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_last_page_has_next_false(self, client, admin_token):
        slug = _make_slug("lastpg")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            for _ in range(5):
                _insert_audit_log(tenant_id=tid)
            resp = client.get(
                _audit_url(tid),
                params={"page": "2", "page_size": "3"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["data"]) == 2  # 5 total, 3 on page 1, 2 on page 2
            assert body["meta"]["total"] == 5
            assert body["meta"]["has_next"] is False
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_over_page_returns_empty_data_with_correct_total(self, client, admin_token):
        slug = _make_slug("over")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            _insert_audit_log(tenant_id=tid)
            resp = client.get(
                _audit_url(tid),
                params={"page": "99", "page_size": "25"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["data"] == []
            assert body["meta"]["total"] == 1
            assert body["meta"]["has_next"] is False
        finally:
            _cleanup_tenants_by_slug_prefix(slug)

    def test_page_and_page_size_reflected_in_meta(self, client, admin_token):
        slug = _make_slug("meta")
        tid = _insert_tenant(slug=slug, name=f"P8 {slug}")
        try:
            resp = client.get(
                _audit_url(tid),
                params={"page": "3", "page_size": "10"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 200
            meta = resp.json()["meta"]
            assert meta["page"] == 3
            assert meta["page_size"] == 10
        finally:
            _cleanup_tenants_by_slug_prefix(slug)


# ===========================================================================
# TestAccessControl
# ===========================================================================


class TestAccessControl:
    """Auth enforcement — 401 / 403 / 200."""

    @pytest.fixture(autouse=True)
    def tenant(self):
        slug = _make_slug("ac")
        tid = _insert_tenant(slug=slug, name=f"P8 AC {slug}")
        self._tid = tid
        yield
        _cleanup_tenants_by_slug_prefix(slug)

    def test_missing_token_returns_401(self, client):
        resp = client.get(_audit_url(self._tid))
        assert resp.status_code == 401

    def test_customer_actor_returns_403(self, client, customer_token):
        resp = client.get(_audit_url(self._tid), headers=_auth(customer_token))
        assert resp.status_code == 403

    def test_platform_viewer_returns_200(self, client, viewer_token):
        resp = client.get(_audit_url(self._tid), headers=_auth(viewer_token))
        assert resp.status_code == 200

    def test_platform_admin_returns_200(self, client, admin_token):
        resp = client.get(_audit_url(self._tid), headers=_auth(admin_token))
        assert resp.status_code == 200


# ===========================================================================
# TestNotFound
# ===========================================================================


class TestNotFound:
    """Tenant existence check."""

    def test_nonexistent_tenant_returns_404(self, client, admin_token):
        ghost_id = str(uuid.uuid4())
        resp = client.get(_audit_url(ghost_id), headers=_auth(admin_token))
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


# ===========================================================================
# TestPathParameter
# ===========================================================================


class TestPathParameter:
    """Path parameter UUID v4 validation → 400."""

    @pytest.mark.parametrize(
        "bad_id",
        [
            "not-a-uuid",
            "12345",
            "00000000-0000-0000-0000-000000000000",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        ],
    )
    def test_malformed_path_param_returns_400(self, client, admin_token, bad_id):
        url = f"{_BASE}/{bad_id}/audit-logs"
        resp = client.get(url, headers=_auth(admin_token))
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_path_parameter"


# ===========================================================================
# TestQueryParams
# ===========================================================================


class TestQueryParams:
    """422 validation for all query parameter error paths."""

    @pytest.fixture(autouse=True)
    def tenant(self):
        slug = _make_slug("qp")
        tid = _insert_tenant(slug=slug, name=f"P8 QP {slug}")
        self._tid = tid
        yield
        _cleanup_tenants_by_slug_prefix(slug)

    def test_invalid_actor_id_returns_422_invalid_uuid_format(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"actor_id": "not-a-uuid"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_uuid_format"

    def test_invalid_event_type_returns_422_validation_error(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"event_type": "unknown_event"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_from_greater_than_to_returns_422_invalid_date_range(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={
                "from": "2026-12-01T00:00:00Z",
                "to": "2026-01-01T00:00:00Z",
            },
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_date_range"

    def test_malformed_from_datetime_returns_422(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"from": "not-a-date"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_page_less_than_one_returns_422(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"page": "0"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_page_size_zero_returns_422(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"page_size": "0"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_page_size_101_returns_422(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"page_size": "101"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_non_integer_page_returns_422(self, client, admin_token):
        resp = client.get(
            _audit_url(self._tid),
            params={"page": "abc"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_cross_tenant_isolation(self, client, admin_token):
        """Audit logs from another tenant must not appear in this tenant's results."""
        slug2 = _make_slug("other")
        other_tid = _insert_tenant(slug=slug2, name=f"P8 Other {slug2}")
        try:
            # Insert logs for OTHER tenant only
            _insert_audit_log(tenant_id=other_tid)
            _insert_audit_log(tenant_id=other_tid)

            # Query THIS tenant — should have 0 logs
            resp = client.get(_audit_url(self._tid), headers=_auth(admin_token))
            assert resp.status_code == 200
            assert resp.json()["meta"]["total"] == 0
        finally:
            _cleanup_tenants_by_slug_prefix(slug2)
