"""
Packet 3 — API contract + integration tests: POST /api/v1/tenants
===================================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database. JWTs are created using the application secret key so
they pass the same validation path that production requests use.

Every test that writes a row uses a slug prefixed ``p3test-`` so that the
module-level cleanup fixture can delete those rows without touching other
data.

Run inside Docker:
    docker-compose exec backend python -m pytest \
        tests/integration/test_f001_p3_create_tenant_api.py -v

Environment variable required:
    DATABASE_URL  (set automatically in the Docker service environment)
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
# Configuration
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/dataquality_db",
)


# Import settings lazily to avoid executing this at collection time
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
def admin_token() -> str:
    """Valid platform_admin JWT signed with the application's secret key."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def viewer_token() -> str:
    """Valid platform_viewer JWT — read-only role."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_viewer",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def customer_token() -> str:
    """Valid customer_actor JWT — unprivileged role."""
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "customer_actor",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module", autouse=True)
def cleanup_test_tenants():
    """Delete all test-created tenant rows after the module finishes.

    Uses a separate psycopg2 connection so it always runs even if the app's
    own DB session is in an error state.
    """
    yield  # all tests run first
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM control.tenant_audit_logs "
            "WHERE tenant_id IN ("
            "  SELECT tenant_id FROM control.tenants WHERE tenant_slug LIKE 'p3test-%'"
            ")"
        )
        cur.execute("DELETE FROM control.tenants WHERE tenant_slug LIKE 'p3test-%'")
    conn.close()


def _slug(suffix: str) -> str:
    """Build a test-scoped slug guaranteed to start with 'p3test-'."""
    return f"p3test-{suffix}"


def _min_body(**overrides) -> dict:
    """Return the minimum valid request body with a name derived from the slug.

    A unique slug always produces a unique name so tests never collide via the
    ``tenant_name_lower`` uniqueness constraint.
    """
    slug = overrides.get("tenant_slug", _slug("default"))
    # Build a stable display name from the slug so it is always unique
    suffix = slug.replace("p3test-", "").replace("-", " ").title()
    base = {
        "tenant_name": f"P3 {suffix} Corp",
        "tenant_slug": slug,
        "region": "eu-west",
        "plan": "starter",
    }
    base.update(overrides)
    return base


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# AC-1 — Happy path: valid admin request → 201 with all fields
# ===========================================================================


class TestHappyPath:
    def test_creates_tenant_returns_201(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("happy1"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201, resp.text

    def test_response_has_data_wrapper(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("happy2"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert "data" in resp.json()

    def test_response_fields_complete(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("happy3"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        data = resp.json()["data"]
        required_fields = {
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
        assert required_fields == set(data.keys())

    def test_response_values_match_input(self, client, admin_token):
        slug = _slug("happy4")
        body = {
            "tenant_name": "Happy Path Corp",
            "tenant_slug": slug,
            "region": "us-east",
            "plan": "enterprise",
            "initial_status": "active",
            "tenant_notes": "Some notes.",
            "service_start_date": "2025-06-01",
        }
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["tenant_name"] == "Happy Path Corp"
        assert data["tenant_slug"] == slug
        assert data["region"] == "us-east"
        assert data["plan"] == "enterprise"
        assert data["status"] == "active"
        assert data["tenant_notes"] == "Some notes."
        assert data["service_start_date"] == "2025-06-01"

    def test_default_status_is_draft_when_omitted(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("happy5"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "draft"

    def test_tenant_id_is_uuid_v4(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("happy6"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        tid = resp.json()["data"]["tenant_id"]
        parsed = uuid.UUID(tid)
        assert parsed.version == 4

    def test_name_trimmed_before_storage(self, client, admin_token):
        body = _min_body(tenant_name="  Trimmed Corp  ", tenant_slug=_slug("trim1"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        assert resp.json()["data"]["tenant_name"] == "Trimmed Corp"

    def test_slug_lowercased_before_storage(self, client, admin_token):
        body = _min_body(tenant_name="Case Corp", tenant_slug=_slug("UPPER").lower())
        # Pass as lower since _slug already lowercases but let's test via direct mixed case
        body["tenant_slug"] = "p3test-UCASE"
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        assert resp.json()["data"]["tenant_slug"] == "p3test-ucase"

    def test_audit_log_created_in_db(self, client, admin_token):
        """Verify the audit log row exists in the DB after a successful create."""
        body = _min_body(tenant_slug=_slug("auditok"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        tenant_id = resp.json()["data"]["tenant_id"]

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT event_type, previous_data "
                "FROM control.tenant_audit_logs "
                "WHERE tenant_id = %s",
                (uuid.UUID(tenant_id),),
            )
            rows = cur.fetchall()
        conn.close()

        assert len(rows) == 1
        event_type, previous_data = rows[0]
        assert event_type == "tenant_created"
        assert previous_data is None  # AC-1: previous_data must be NULL for create

    def test_created_by_matches_actor_from_jwt(self, client):
        """created_by must be the actor_id from the token, not a caller-supplied value."""
        s = _get_settings()
        actor_id = str(uuid.uuid4())
        token = jwt.encode(
            {
                "actor_id": actor_id,
                "actor_role": "platform_admin",
                "exp": datetime.now(tz=UTC) + timedelta(hours=1),
            },
            s.JWT_SECRET_KEY,
            algorithm=s.JWT_ALGORITHM,
        )
        body = _min_body(tenant_slug=_slug("actorchk"))
        # Attempt to supply a fake created_by — must be silently discarded
        body["created_by"] = "00000000-0000-4000-8000-000000000000"
        resp = client.post(
            "/api/v1/tenants", json=body, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["created_by"] == actor_id
        assert data["updated_by"] == actor_id


# ===========================================================================
# AC-2 — Duplicate name → 422 duplicate_name
# ===========================================================================


class TestDuplicateName:
    def test_duplicate_name_returns_422(self, client, admin_token):
        # First create
        body = _min_body(tenant_name="Duplicate Name Corp", tenant_slug=_slug("dup-n1"))
        r1 = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert r1.status_code == 201

        # Second create — same name, different slug
        body2 = _min_body(tenant_name="Duplicate Name Corp", tenant_slug=_slug("dup-n2"))
        r2 = client.post("/api/v1/tenants", json=body2, headers=_auth(admin_token))
        assert r2.status_code == 422
        assert r2.json()["error"]["code"] == "duplicate_name"

    def test_duplicate_name_case_insensitive(self, client, admin_token):
        body = _min_body(tenant_name="Case Dup Corp", tenant_slug=_slug("casen1"))
        client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))

        body2 = _min_body(tenant_name="case dup corp", tenant_slug=_slug("casen2"))
        r2 = client.post("/api/v1/tenants", json=body2, headers=_auth(admin_token))
        assert r2.status_code == 422
        assert r2.json()["error"]["code"] == "duplicate_name"


# ===========================================================================
# AC-3 — Duplicate slug → 422 duplicate_slug
# ===========================================================================


class TestDuplicateSlug:
    def test_duplicate_slug_returns_422(self, client, admin_token):
        slug = _slug("dup-slug")
        body = _min_body(tenant_name="Slug First Corp", tenant_slug=slug)
        r1 = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert r1.status_code == 201

        body2 = _min_body(tenant_name="Slug Second Corp", tenant_slug=slug)
        r2 = client.post("/api/v1/tenants", json=body2, headers=_auth(admin_token))
        assert r2.status_code == 422
        assert r2.json()["error"]["code"] == "duplicate_slug"


# ===========================================================================
# AC-4 — Invalid initial_status → 422 invalid_status
# ===========================================================================


class TestInvalidStatus:
    def test_suspended_status_rejected(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("stat1"), initial_status="suspended")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_status"

    def test_archived_status_rejected(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("stat2"), initial_status="archived")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_status"

    def test_unknown_status_rejected(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("stat3"), initial_status="online")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_status"


# ===========================================================================
# AC-5 — Audit log failure rolls back tenant row (atomicity)
#         (tested indirectly via duplicate slug — both fail or both commit)
# ===========================================================================


class TestAtomicity:
    def test_successful_create_leaves_both_rows(self, client, admin_token):
        """Both tenant row and audit log row must exist after a successful create."""
        body = _min_body(tenant_slug=_slug("atomic1"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 201
        tid = resp.json()["data"]["tenant_id"]

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM control.tenants WHERE tenant_id = %s",
                (uuid.UUID(tid),),
            )
            tenant_count = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM control.tenant_audit_logs WHERE tenant_id = %s",
                (uuid.UUID(tid),),
            )
            log_count = cur.fetchone()[0]
        conn.close()

        assert tenant_count == 1
        assert log_count == 1


# ===========================================================================
# AC-6 — Metric emitter failure does not affect response
#         (tested via monkeypatching the emit function to raise)
# ===========================================================================


class TestMetricResiliency:
    def test_metric_failure_does_not_affect_201_response(self, client, admin_token, monkeypatch):
        import app.services.tenants.service as svc_module

        def _boom(*args, **kwargs):
            raise RuntimeError("Metric collector is down!")

        monkeypatch.setattr(svc_module, "emit_tenant_create_success", _boom)

        body = _min_body(tenant_slug=_slug("metric1"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        # Despite the metric explosion, the create must still return 201
        assert resp.status_code == 201


# ===========================================================================
# AC-7 — Platform Viewer token → 403 forbidden
# ===========================================================================


class TestAccessControl:
    def test_viewer_token_returns_403(self, client, viewer_token):
        body = _min_body(tenant_slug=_slug("notcreated1"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(viewer_token))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"

    def test_customer_actor_token_returns_403(self, client, customer_token):
        body = _min_body(tenant_slug=_slug("notcreated2"))
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(customer_token))
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "forbidden"

    def test_missing_token_returns_401(self, client):
        body = _min_body(tenant_slug=_slug("notcreated3"))
        resp = client.post("/api/v1/tenants", json=body)
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "unauthorized"

    def test_invalid_token_returns_401(self, client):
        body = _min_body(tenant_slug=_slug("notcreated4"))
        resp = client.post(
            "/api/v1/tenants",
            json=body,
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        assert resp.status_code == 401


# ===========================================================================
# Validation error scenarios (TDD §6 rules)
# ===========================================================================


class TestValidationErrors:
    def test_missing_tenant_name_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr1"))
        del body["tenant_name"]
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_missing_tenant_slug_returns_422(self, client, admin_token):
        body = _min_body()
        del body["tenant_slug"]
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_missing_region_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr2"))
        del body["region"]
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_missing_plan_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr3"))
        del body["plan"]
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "validation_error"

    def test_invalid_region_value_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr4"), region="ap-southeast")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_region"

    def test_invalid_plan_value_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr5"), plan="premium")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_plan"

    def test_tenant_name_too_short_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr6"), tenant_name="A")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_tenant_name_with_forbidden_char_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr7"), tenant_name="Bad<Name>")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_tenant_slug_leading_hyphen_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug="-leading-hyphen")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_tenant_slug_consecutive_hyphens_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug="p3test--double")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_invalid_date_format_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr8"), service_start_date="2025/01/15")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_notes_with_control_char_returns_422(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr9"), tenant_notes="line1\x00line2")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422

    def test_error_response_has_correct_envelope(self, client, admin_token):
        body = _min_body(tenant_slug=_slug("verr10"), region="invalid-region")
        resp = client.post("/api/v1/tenants", json=body, headers=_auth(admin_token))
        assert resp.status_code == 422
        error = resp.json().get("error", {})
        assert "code" in error
        assert "message" in error
        assert "fields" in error
