"""
Packet 6 — API contract + integration tests: PATCH /api/v1/tenants/{tenant_id}
================================================================================

Tests cover:
    • Happy path           — 200 OK, correct envelope, 13 fields, values correct
    • Access control       — 401/403 enforcement (admin only writes)
    • Not-found            — 404 for valid UUID with no matching row
    • Path parameter       — 400 for malformed / non-UUID strings
    • Immutable fields     — 422 immutable_field for tenant_slug / region / tenant_id
    • Status field         — 422 use_status_endpoint when status in body
    • No mutable fields    — 422 no_mutable_fields (empty body, no-op diff)
    • Archived tenant      — 422 archived_tenant
    • status_reason guard  — 422 on suspended/archived without valid reason
    • Duplicate name       — 422 duplicate_name
    • Concurrency          — 409 conflict when row lock held by another connection
    • Audit log            — only changed fields appear in audit previous/new data
    • Version increment    — version bumped by every successful PATCH

Test isolation
--------------
One primary tenant (slug ``p6test-meta-1``) is created at module scope.
A secondary tenant (slug ``p6test-meta-2``) is used for duplicate-name tests.
All fixture rows are cleaned up in teardown.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/integration/test_f001_p6_update_tenant_api.py -v
"""

from __future__ import annotations

import os
import threading
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

_P6_SLUG_PREFIX = "p6test-"
_BASE = "/api/v1/tenants"

# ---------------------------------------------------------------------------
# Lazy helpers
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


def _url(tenant_id: str) -> str:
    return f"{_BASE}/{tenant_id}"


def _insert_tenant(
    conn,
    *,
    slug: str,
    name: str,
    status: str = "active",
    plan: str = "starter",
    region: str = "eu-west",
    status_reason: str | None = None,
    actor_id: str | None = None,
) -> str:
    """Insert a tenant row and return the generated tenant_id string."""
    tid = str(uuid.uuid4())
    aid = actor_id or str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO control.tenants (
                tenant_id, tenant_name, tenant_slug,
                status, region, plan,
                status_reason,
                created_by, updated_by, version
            ) VALUES (
                %s, %s, %s,
                %s::control.tenant_status_enum,
                %s::control.tenant_region_enum,
                %s::control.tenant_plan_enum,
                %s,
                %s, %s, %s
            )
            """,
            (
                tid,
                name,
                slug,
                status,
                region,
                plan,
                status_reason,
                aid,
                aid,
                0,
            ),
        )
    conn.commit()
    return tid


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


@pytest.fixture(scope="module", autouse=True)
def p6_tenants():
    """
    Insert the two module-scoped test tenants and clean up on teardown.

    Yields a dict::

        {
            "primary": {"tenant_id": ..., "tenant_name": ..., "tenant_slug": ...},
            "secondary": {"tenant_id": ..., "tenant_name": ..., "tenant_slug": ...},
        }
    """
    conn = psycopg2.connect(DATABASE_URL)
    try:
        primary_id = _insert_tenant(
            conn,
            slug=f"{_P6_SLUG_PREFIX}meta-1",
            name="P6 Primary Corp",
            status="active",
            plan="starter",
        )
        secondary_id = _insert_tenant(
            conn,
            slug=f"{_P6_SLUG_PREFIX}meta-2",
            name="P6 Secondary Corp",
            status="active",
            plan="growth",
        )
    finally:
        conn.close()

    yield {
        "primary": {
            "tenant_id": primary_id,
            "tenant_name": "P6 Primary Corp",
            "tenant_slug": f"{_P6_SLUG_PREFIX}meta-1",
        },
        "secondary": {
            "tenant_id": secondary_id,
            "tenant_name": "P6 Secondary Corp",
            "tenant_slug": f"{_P6_SLUG_PREFIX}meta-2",
        },
    }

    # Teardown — delete audit logs first, then tenant rows
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM control.tenant_audit_logs WHERE tenant_id IN "
                "(SELECT tenant_id FROM control.tenants WHERE tenant_slug LIKE %s)",
                (f"{_P6_SLUG_PREFIX}%",),
            )
            cur.execute(
                "DELETE FROM control.tenants WHERE tenant_slug LIKE %s",
                (f"{_P6_SLUG_PREFIX}%",),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DB-read helper
# ---------------------------------------------------------------------------


def _fetch_tenant(tenant_id: str) -> dict:
    """Fetch the current row for *tenant_id* directly from the DB."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM control.tenants WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None, f"Tenant {tenant_id} not found in DB"
    return dict(row)


def _fetch_latest_audit(tenant_id: str) -> dict | None:
    """Return the most-recent audit log row for *tenant_id*, or None."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM control.tenant_audit_logs
                WHERE tenant_id = %s::uuid
                ORDER BY occurred_at DESC
                LIMIT 1
                """,
                (tenant_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


# ===========================================================================
# TestHappyPath
# ===========================================================================


class TestHappyPath:
    """PATCH succeeds — 200 OK, correct envelope / field values / side effects."""

    def test_200_response_code(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "First happy-path note"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200

    def test_response_has_data_envelope(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "Envelope check note"},
            headers=_auth(admin_token),
        )
        body = resp.json()
        assert "data" in body
        assert "error" not in body

    def test_response_has_exactly_thirteen_fields(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "Thirteen-field note"},
            headers=_auth(admin_token),
        )
        data = resp.json()["data"]
        expected = {
            "tenant_id",
            "tenant_name",
            "tenant_slug",
            "status",
            "status_reason",
            "region",
            "plan",
            "service_start_date",
            "tenant_notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
        assert set(data.keys()) == expected

    def test_updated_field_reflected_in_response(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"plan": "growth"},
            headers=_auth(admin_token),
        )
        assert resp.json()["data"]["plan"] == "growth"

    def test_tenant_id_in_response_matches_path(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "ID check"},
            headers=_auth(admin_token),
        )
        assert resp.json()["data"]["tenant_id"] == tid

    def test_version_incremented_in_db(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        before = _fetch_tenant(tid)["version"]
        client.patch(
            _url(tid),
            json={"tenant_notes": "Version bump check"},
            headers=_auth(admin_token),
        )
        after = _fetch_tenant(tid)["version"]
        assert after == before + 1

    def test_audit_log_created_for_update(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        client.patch(
            _url(tid),
            json={"tenant_notes": "Audit log check"},
            headers=_auth(admin_token),
        )
        audit = _fetch_latest_audit(tid)
        assert audit is not None
        assert audit["event_type"] == "tenant_updated"

    def test_audit_log_contains_only_changed_fields(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        client.patch(
            _url(tid),
            json={"tenant_name": "P6 Primary Corp Renamed"},
            headers=_auth(admin_token),
        )
        audit = _fetch_latest_audit(tid)
        assert "tenant_name" in audit["new_data"]
        assert "plan" not in audit["new_data"]


# ===========================================================================
# TestAccessControl
# ===========================================================================


class TestAccessControl:
    """Only platform_admin may PATCH; viewers and customers are rejected."""

    def test_missing_token_returns_401(self, client, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(_url(tid), json={"tenant_notes": "x"})
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self, client, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "x"},
            headers={"Authorization": "Bearer not.a.valid.token"},
        )
        assert resp.status_code == 401

    def test_viewer_returns_403(self, client, viewer_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "x"},
            headers=_auth(viewer_token),
        )
        assert resp.status_code == 403

    def test_customer_returns_403(self, client, customer_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": "x"},
            headers=_auth(customer_token),
        )
        assert resp.status_code == 403

    def test_admin_returns_200(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        # Use a unique note value to ensure change set is non-empty
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": f"Admin access check {uuid.uuid4()}"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200


# ===========================================================================
# TestNotFound
# ===========================================================================


class TestNotFound:
    """Valid UUID that does not exist in the DB → 404."""

    def test_unknown_uuid_returns_404(self, client, admin_token):
        unknown = str(uuid.uuid4())
        resp = client.patch(
            _url(unknown),
            json={"tenant_notes": "ghost"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 404

    def test_404_error_envelope(self, client, admin_token):
        unknown = str(uuid.uuid4())
        resp = client.patch(
            _url(unknown),
            json={"tenant_notes": "ghost"},
            headers=_auth(admin_token),
        )
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == "not_found"


# ===========================================================================
# TestPathParameter
# ===========================================================================


class TestPathParameter:
    """Malformed path parameter → 400 invalid_path_parameter."""

    def test_non_uuid_string_returns_400(self, client, admin_token):
        resp = client.patch(
            _url("not-a-uuid"),
            json={"tenant_notes": "x"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 400

    def test_400_error_code(self, client, admin_token):
        resp = client.patch(
            _url("abc-123"),
            json={"tenant_notes": "x"},
            headers=_auth(admin_token),
        )
        assert resp.json()["error"]["code"] == "invalid_path_parameter"


# ===========================================================================
# TestImmutableFields
# ===========================================================================


class TestImmutableFields:
    """Attempts to change immutable fields → 422 immutable_field."""

    def test_tenant_slug_rejected(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_slug": "new-slug"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "immutable_field"

    def test_region_rejected(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"region": "us-east"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "immutable_field"

    def test_tenant_id_rejected(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_id": str(uuid.uuid4())},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "immutable_field"

    def test_mixed_immutable_and_mutable_still_rejected(self, client, admin_token, p6_tenants):
        """Presence of an immutable field triggers rejection even alongside valid fields."""
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_slug": "bad", "tenant_name": "Good Name"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "immutable_field"


# ===========================================================================
# TestStatusField
# ===========================================================================


class TestStatusField:
    """status in body → 422 use_status_endpoint."""

    def test_status_alone_rejected(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"status": "suspended"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "use_status_endpoint"

    def test_status_with_other_fields_rejected(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"status": "active", "tenant_notes": "note"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "use_status_endpoint"


# ===========================================================================
# TestNoMutableFields
# ===========================================================================


class TestNoMutableFields:
    """Bodies that supply no genuinely new values → 422 no_mutable_fields."""

    def test_empty_body_rejected(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "no_mutable_fields"

    def test_unknown_key_only_rejected(self, client, admin_token, p6_tenants):
        """A key that is not a recognised field is not an immutable field
        either, so the endpoint should return no_mutable_fields."""
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"unknown_key": "value"},
            headers=_auth(admin_token),
        )
        # unknown_key is not in immutable set and not in mutable set
        # so model_fields_set & _PATCH_MUTABLE_FIELDS is empty → 422
        assert resp.status_code == 422


# ===========================================================================
# TestArchivedTenant
# ===========================================================================


class TestArchivedTenant:
    """Archived tenants cannot be modified."""

    def test_archived_tenant_returns_422(self, client, admin_token):
        conn = psycopg2.connect(DATABASE_URL)
        try:
            archived_id = _insert_tenant(
                conn,
                slug=f"{_P6_SLUG_PREFIX}archived-1",
                name="P6 Archived Corp",
                status="archived",
                status_reason="Archived for testing purposes",
            )
        finally:
            conn.close()

        resp = client.patch(
            _url(archived_id),
            json={"tenant_notes": "cannot touch"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "archived_tenant"

    def test_active_tenant_not_blocked(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        resp = client.patch(
            _url(tid),
            json={"tenant_notes": f"Active check {uuid.uuid4()}"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200


# ===========================================================================
# TestStatusReasonGuard
# ===========================================================================


class TestStatusReasonGuard:
    """status_reason validation for suspended tenants."""

    def test_clear_status_reason_on_suspended_returns_422(self, client, admin_token):
        conn = psycopg2.connect(DATABASE_URL)
        try:
            susp_id = _insert_tenant(
                conn,
                slug=f"{_P6_SLUG_PREFIX}susp-1",
                name="P6 Suspended Corp A",
                status="suspended",
                status_reason="Original long enough reason",
            )
        finally:
            conn.close()

        resp = client.patch(
            _url(susp_id),
            json={"status_reason": None},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "status_reason_required_for_current_status"

    def test_short_status_reason_on_suspended_returns_422(self, client, admin_token):
        conn = psycopg2.connect(DATABASE_URL)
        try:
            susp_id = _insert_tenant(
                conn,
                slug=f"{_P6_SLUG_PREFIX}susp-2",
                name="P6 Suspended Corp B",
                status="suspended",
                status_reason="Original long enough reason",
            )
        finally:
            conn.close()

        resp = client.patch(
            _url(susp_id),
            json={"status_reason": "Short"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_long_status_reason_on_suspended_succeeds(self, client, admin_token):
        conn = psycopg2.connect(DATABASE_URL)
        try:
            susp_id = _insert_tenant(
                conn,
                slug=f"{_P6_SLUG_PREFIX}susp-3",
                name="P6 Suspended Corp C",
                status="suspended",
                status_reason="Original long enough reason",
            )
        finally:
            conn.close()

        resp = client.patch(
            _url(susp_id),
            json={"status_reason": "This is an updated and long enough reason"},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200

    def test_status_reason_clearable_on_active(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        # First set a reason
        client.patch(
            _url(tid),
            json={"status_reason": "Setting a reason first"},
            headers=_auth(admin_token),
        )
        # Then clear it — active tenant allows this
        resp = client.patch(
            _url(tid),
            json={"status_reason": None},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200


# ===========================================================================
# TestDuplicateName
# ===========================================================================


class TestDuplicateName:
    """Changing tenant_name to a value already taken → 422 duplicate_name."""

    def test_duplicate_name_returns_422(self, client, admin_token, p6_tenants):
        """Renaming primary to secondary's name should be rejected."""
        tid = p6_tenants["primary"]["tenant_id"]
        taken_name = p6_tenants["secondary"]["tenant_name"]
        resp = client.patch(
            _url(tid),
            json={"tenant_name": taken_name},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "duplicate_name"

    def test_same_tenant_name_triggers_no_change_not_duplicate(
        self, client, admin_token, p6_tenants
    ):
        """Setting tenant_name to its current value → no_mutable_fields (not duplicate_name)."""
        tid = p6_tenants["primary"]["tenant_id"]
        db_row = _fetch_tenant(tid)
        current_name = db_row["tenant_name"]

        resp = client.patch(
            _url(tid),
            json={"tenant_name": current_name},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "no_mutable_fields"


# ===========================================================================
# TestConcurrency
# ===========================================================================


class TestConcurrency:
    """409 conflict returned when the row is locked by another connection."""

    def test_concurrent_patch_returns_409(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]

        barrier = threading.Barrier(2)
        release = threading.Event()
        errors: list[Exception] = []

        def _hold_lock():
            """Hold a FOR UPDATE NOWAIT lock until release event is set."""
            try:
                conn2 = psycopg2.connect(DATABASE_URL)
                conn2.autocommit = False
                try:
                    with conn2.cursor() as cur:
                        cur.execute(
                            "SELECT 1 FROM control.tenants "
                            "WHERE tenant_id = %s::uuid FOR UPDATE NOWAIT",
                            (tid,),
                        )
                        barrier.wait()  # signal: lock is now held
                        release.wait()  # hold until test is done
                    conn2.rollback()
                finally:
                    conn2.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
                try:
                    barrier.wait(timeout=1)
                except Exception:  # noqa: BLE001
                    pass

        t = threading.Thread(target=_hold_lock, daemon=True)
        t.start()
        try:
            barrier.wait(timeout=5)  # wait until lock is held
            assert not errors, f"Lock holder failed: {errors}"

            resp = client.patch(
                _url(tid),
                json={"tenant_notes": f"concurrent {uuid.uuid4()}"},
                headers=_auth(admin_token),
            )
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "conflict"
        finally:
            release.set()
            t.join(timeout=5)


# ===========================================================================
# TestAuditAndVersion
# ===========================================================================


class TestAuditAndVersion:
    """Verify audit log content and version counter."""

    def test_only_changed_fields_in_audit_new_data(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        unique_notes = f"Audit field test {uuid.uuid4()}"
        client.patch(
            _url(tid),
            json={"tenant_notes": unique_notes},
            headers=_auth(admin_token),
        )
        audit = _fetch_latest_audit(tid)
        assert "tenant_notes" in audit["new_data"]
        assert "plan" not in audit["new_data"]
        assert "tenant_name" not in audit["new_data"]

    def test_audit_previous_data_matches_old_db_value(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        old_notes = _fetch_tenant(tid)["tenant_notes"]
        new_notes = f"Updated notes {uuid.uuid4()}"
        client.patch(
            _url(tid),
            json={"tenant_notes": new_notes},
            headers=_auth(admin_token),
        )
        audit = _fetch_latest_audit(tid)
        assert audit["previous_data"]["tenant_notes"] == old_notes

    def test_every_patch_increments_version(self, client, admin_token, p6_tenants):
        tid = p6_tenants["primary"]["tenant_id"]
        v1 = _fetch_tenant(tid)["version"]

        client.patch(
            _url(tid),
            json={"tenant_notes": f"Ver inc 1 {uuid.uuid4()}"},
            headers=_auth(admin_token),
        )
        v2 = _fetch_tenant(tid)["version"]

        client.patch(
            _url(tid),
            json={"tenant_notes": f"Ver inc 2 {uuid.uuid4()}"},
            headers=_auth(admin_token),
        )
        v3 = _fetch_tenant(tid)["version"]

        assert v2 == v1 + 1
        assert v3 == v2 + 1
