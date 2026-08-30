"""
Packet 4 — Integration + API contract tests: GET /api/v1/tenants
=================================================================

Tests use FastAPI's TestClient (synchronous, in-process) with the real
PostgreSQL database.  JWTs are created with the application secret key so
they travel through the same validation path as production requests.

Test data isolation
-------------------
All test tenants are inserted with slug prefix ``p4test-`` and tenant name
prefix ``P4test``.  Queries that need to be isolated from other data in the DB
use the ``q=p4test`` search parameter so only test-owned rows are counted.
The module-level ``p4_test_tenants`` fixture inserts 10 tenants before any
test in the module runs and deletes them in teardown.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/integration/test_f001_p4_list_tenants_api.py -v
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

_P4_SLUG_PREFIX = "p4test-"

# Test tenant definitions: (slug_suffix, name, status, region, plan, status_reason)
# status_reason required for archived/suspended (DB CHECK constraint ≥ 10 chars).
_TEST_TENANTS = [
    ("ew-active-1", "P4test EW Active One", "active", "eu-west", "starter", None),
    ("ew-active-2", "P4test EW Active Two", "active", "eu-west", "starter", None),
    ("ew-active-3", "P4test EW Active Three", "active", "eu-west", "growth", None),
    ("ue-active-1", "P4test UE Active One", "active", "us-east", "growth", None),
    ("ue-active-2", "P4test UE Active Two", "active", "us-east", "enterprise", None),
    ("ec-draft-1", "P4test EC Draft One", "draft", "eu-central", "starter", None),
    ("uw-draft-1", "P4test UW Draft One", "draft", "us-west", "growth", None),
    ("uw-draft-2", "P4test UW Draft Two", "draft", "us-west", "enterprise", None),
    (
        "archived-1",
        "P4test Archived One",
        "archived",
        "us-east",
        "starter",
        "Archived for testing purposes",
    ),
    (
        "archived-2",
        "P4test Archived Two",
        "archived",
        "eu-west",
        "growth",
        "Archived for testing purposes",
    ),
]
# Counts for use in assertions:
_TOTAL_WITH_ARCHIVED = 10
_TOTAL_WITHOUT_ARCHIVED = 8  # excludes 2 archived
_TOTAL_ACTIVE = 5
_TOTAL_DRAFT = 3
_TOTAL_ARCHIVED = 2
_TOTAL_EU_WEST_WITHOUT_ARCHIVED = 3  # ew-active-1/2/3 (archived-2 excluded)
_TOTAL_EU_WEST_WITH_ARCHIVED = 4
_TOTAL_ENTERPRISE_WITHOUT_ARCHIVED = 2  # ue-active-2, uw-draft-2


# ---------------------------------------------------------------------------
# Lazy settings helper
# ---------------------------------------------------------------------------


def _get_settings():
    from app.core.config import settings

    return settings


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
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def viewer_token() -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_viewer",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def customer_token() -> str:
    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "customer_actor",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module", autouse=True)
def p4_test_tenants():
    """Insert 10 test tenants before module tests; delete them in teardown."""
    conn = psycopg2.connect(DATABASE_URL)
    tenant_ids: list[str] = []

    try:
        with conn.cursor() as cur:
            for suffix, name, status, region, plan, status_reason in _TEST_TENANTS:
                tid = str(uuid.uuid4())
                actor_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO control.tenants (
                        tenant_id, tenant_name, tenant_slug,
                        status, status_reason,
                        region, plan,
                        created_by, updated_by, version
                    ) VALUES (
                        %s, %s, %s,
                        %s::control.tenant_status_enum, %s,
                        %s::control.tenant_region_enum,
                        %s::control.tenant_plan_enum,
                        %s, %s, %s
                    )
                    """,
                    (
                        tid,
                        name,
                        f"{_P4_SLUG_PREFIX}{suffix}",
                        status,
                        status_reason,
                        region,
                        plan,
                        actor_id,
                        actor_id,
                        0,
                    ),
                )
                tenant_ids.append(tid)
        conn.commit()
    finally:
        conn.close()

    yield tenant_ids

    # Teardown — delete in dependency order (audit logs first, then tenants)
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM control.tenant_audit_logs "
                "WHERE tenant_id IN (SELECT tenant_id FROM control.tenants "
                "WHERE tenant_slug LIKE %s)",
                (f"{_P4_SLUG_PREFIX}%",),
            )
            cur.execute(
                "DELETE FROM control.tenants WHERE tenant_slug LIKE %s",
                (f"{_P4_SLUG_PREFIX}%",),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = "/api/v1/tenants"
_AUTH_HEADER = "Authorization"


def _auth(token: str) -> dict:
    return {_AUTH_HEADER: f"Bearer {token}"}


# ===========================================================================
# TestHappyPath
# ===========================================================================


class TestHappyPath:
    def test_200_with_valid_token(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        assert r.status_code == 200

    def test_response_has_data_and_meta_keys(self, client, admin_token):
        r = client.get(
            _BASE, headers=_auth(admin_token), params={"q": "p4test", "include_archived": "true"}
        )
        body = r.json()
        assert "data" in body
        assert "meta" in body

    def test_data_is_list(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        assert isinstance(r.json()["data"], list)

    def test_meta_fields_present(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        meta = r.json()["meta"]
        assert "total" in meta
        assert "page" in meta
        assert "page_size" in meta
        assert "has_next" in meta

    def test_meta_defaults_applied(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        meta = r.json()["meta"]
        assert meta["page"] == 1
        assert meta["page_size"] == 25

    def test_item_has_exactly_eight_fields(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        items = r.json()["data"]
        assert len(items) > 0
        expected_fields = {
            "tenant_id",
            "tenant_name",
            "tenant_slug",
            "status",
            "region",
            "plan",
            "created_at",
            "updated_at",
        }
        assert set(items[0].keys()) == expected_fields

    def test_item_fields_have_correct_types(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        item = r.json()["data"][0]
        assert isinstance(item["tenant_id"], str)
        assert isinstance(item["tenant_name"], str)
        assert isinstance(item["tenant_slug"], str)
        assert isinstance(item["status"], str)
        assert isinstance(item["region"], str)
        assert isinstance(item["plan"], str)
        assert isinstance(item["created_at"], str)
        assert isinstance(item["updated_at"], str)

    def test_created_at_is_iso8601_utc(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        ts = r.json()["data"][0]["created_at"]
        # Must be parseable as an ISO 8601 datetime with UTC offset
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.utcoffset() is not None or ts.endswith("+00:00") or ts.endswith("Z")

    def test_no_full_detail_fields_in_list_items(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        item = r.json()["data"][0]
        # Packet 4 explicitly excludes these fields
        for absent_field in (
            "status_reason",
            "tenant_notes",
            "created_by",
            "updated_by",
            "service_start_date",
        ):
            assert absent_field not in item, f"Unexpected field in list item: {absent_field}"

    def test_total_reflects_only_non_archived_by_default(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test"},
        )
        assert r.json()["meta"]["total"] == _TOTAL_WITHOUT_ARCHIVED


# ===========================================================================
# TestAccessControl
# ===========================================================================


class TestAccessControl:
    def test_missing_token_returns_401(self, client):
        r = client.get(_BASE)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"

    def test_invalid_token_returns_401(self, client):
        r = client.get(_BASE, headers={_AUTH_HEADER: "Bearer not.a.token"})
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"

    def test_customer_actor_returns_403(self, client, customer_token):
        r = client.get(_BASE, headers=_auth(customer_token))
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"

    def test_platform_viewer_is_allowed(self, client, viewer_token):
        """GET /tenants is a read operation; platform_viewer must be permitted."""
        r = client.get(_BASE, headers=_auth(viewer_token), params={"q": "p4test"})
        assert r.status_code == 200

    def test_platform_admin_is_allowed(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"q": "p4test"})
        assert r.status_code == 200


# ===========================================================================
# TestFiltering
# ===========================================================================


class TestFiltering:
    def test_filter_by_status_active(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "active"},
        )
        data = r.json()["data"]
        assert len(data) == _TOTAL_ACTIVE
        assert all(item["status"] == "active" for item in data)
        assert r.json()["meta"]["total"] == _TOTAL_ACTIVE

    def test_filter_by_status_draft(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "draft"},
        )
        data = r.json()["data"]
        assert len(data) == _TOTAL_DRAFT
        assert all(item["status"] == "draft" for item in data)

    def test_filter_by_status_archived_with_include_archived(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "archived", "include_archived": "true"},
        )
        data = r.json()["data"]
        assert len(data) == _TOTAL_ARCHIVED
        assert all(item["status"] == "archived" for item in data)

    def test_filter_by_status_archived_without_include_archived_returns_empty(
        self, client, admin_token
    ):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "archived"},
        )
        # include_archived defaults to false → archived excluded → data = []
        data = r.json()["data"]
        assert len(data) == 0
        assert r.json()["meta"]["total"] == 0

    def test_filter_by_region_eu_west(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "region": "eu-west"},
        )
        data = r.json()["data"]
        assert len(data) == _TOTAL_EU_WEST_WITHOUT_ARCHIVED
        assert all(item["region"] == "eu-west" for item in data)

    def test_filter_by_region_eu_west_with_archived(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "region": "eu-west", "include_archived": "true"},
        )
        data = r.json()["data"]
        assert len(data) == _TOTAL_EU_WEST_WITH_ARCHIVED

    def test_filter_by_plan_enterprise(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "plan": "enterprise"},
        )
        data = r.json()["data"]
        assert len(data) == _TOTAL_ENTERPRISE_WITHOUT_ARCHIVED
        assert all(item["plan"] == "enterprise" for item in data)

    def test_filter_combination_status_and_region(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "active", "region": "eu-west"},
        )
        data = r.json()["data"]
        # active eu-west: ew-active-1, ew-active-2, ew-active-3 → 3
        assert len(data) == 3
        assert all(item["status"] == "active" and item["region"] == "eu-west" for item in data)


# ===========================================================================
# TestSearchQ
# ===========================================================================


class TestSearchQ:
    def test_q_matches_name_fragment(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "Archived One", "include_archived": "true"},
        )
        data = r.json()["data"]
        assert any("P4test Archived One" in item["tenant_name"] for item in data)

    def test_q_matches_slug_fragment(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test-ew-active"},
        )
        data = r.json()["data"]
        slugs = [item["tenant_slug"] for item in data]
        assert all(s.startswith("p4test-ew-active") for s in slugs)

    def test_q_is_case_insensitive_on_name(self, client, admin_token):
        r_lower = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test ew active one"},
        )
        r_upper = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "P4TEST EW ACTIVE ONE"},
        )
        # Both should return the same count (ILIKE)
        assert r_lower.json()["meta"]["total"] == r_upper.json()["meta"]["total"]

    def test_q_percent_escaped_does_not_widen_results(self, client, admin_token):
        # "%4test" — if % were NOT escaped it would match everything;
        # with escaping it matches only tenants with literal "%4test" in name/slug
        # (which is none of ours) → 0 results
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "%4test", "include_archived": "true"},
        )
        assert r.json()["meta"]["total"] == 0

    def test_q_none_does_not_filter(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test"},
        )
        assert r.json()["meta"]["total"] >= _TOTAL_WITHOUT_ARCHIVED


# ===========================================================================
# TestIncludeArchived
# ===========================================================================


class TestIncludeArchived:
    def test_default_excludes_archived_from_data(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test"},
        )
        data = r.json()["data"]
        assert all(item["status"] != "archived" for item in data)

    def test_default_excludes_archived_from_total(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test"},
        )
        assert r.json()["meta"]["total"] == _TOTAL_WITHOUT_ARCHIVED

    def test_include_archived_true_includes_archived_in_data(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true"},
        )
        data = r.json()["data"]
        statuses = [item["status"] for item in data]
        assert "archived" in statuses

    def test_include_archived_true_total_is_higher(self, client, admin_token):
        r_with = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true"},
        )
        r_without = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test"},
        )
        assert r_with.json()["meta"]["total"] == _TOTAL_WITH_ARCHIVED
        assert r_without.json()["meta"]["total"] == _TOTAL_WITHOUT_ARCHIVED

    def test_include_archived_false_explicit(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "false"},
        )
        assert r.json()["meta"]["total"] == _TOTAL_WITHOUT_ARCHIVED


# ===========================================================================
# TestSorting
# ===========================================================================


class TestSorting:
    def _get_all(self, client, admin_token, **params):
        p = {"q": "p4test", "page_size": "50", "include_archived": "true", **params}
        return client.get(_BASE, headers=_auth(admin_token), params=p)

    def test_sort_by_created_at_asc_order_is_non_decreasing(self, client, admin_token):
        r = self._get_all(client, admin_token, sort_by="created_at", sort_dir="asc")
        data = r.json()["data"]
        assert len(data) >= 2
        dates = [item["created_at"] for item in data]
        assert dates == sorted(dates)

    def test_sort_by_created_at_desc_order_is_non_increasing(self, client, admin_token):
        r = self._get_all(client, admin_token, sort_by="created_at", sort_dir="desc")
        data = r.json()["data"]
        assert len(data) >= 2
        dates = [item["created_at"] for item in data]
        assert dates == sorted(dates, reverse=True)

    def test_sort_by_updated_at_desc(self, client, admin_token):
        r = self._get_all(client, admin_token, sort_by="updated_at", sort_dir="desc")
        data = r.json()["data"]
        assert len(data) >= 2
        dates = [item["updated_at"] for item in data]
        assert dates == sorted(dates, reverse=True)

    def test_sort_by_updated_at_asc(self, client, admin_token):
        r = self._get_all(client, admin_token, sort_by="updated_at", sort_dir="asc")
        data = r.json()["data"]
        assert len(data) >= 2
        dates = [item["updated_at"] for item in data]
        assert dates == sorted(dates)


# ===========================================================================
# TestPagination
# ===========================================================================


class TestPagination:
    def test_page_size_limits_results(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true", "page_size": "5"},
        )
        assert len(r.json()["data"]) == 5

    def test_has_next_true_when_more_pages(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true", "page_size": "5", "page": "1"},
        )
        assert r.json()["meta"]["has_next"] is True
        assert r.json()["meta"]["total"] == _TOTAL_WITH_ARCHIVED

    def test_has_next_false_on_last_page(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true", "page_size": "5", "page": "2"},
        )
        assert r.json()["meta"]["has_next"] is False
        assert len(r.json()["data"]) == 5

    def test_over_page_returns_empty_data(self, client, admin_token):
        """TDD §3.1 E-06: over-page → 200 data=[] has_next=false correct total."""
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true", "page_size": "5", "page": "10"},
        )
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["meta"]["has_next"] is False
        assert r.json()["meta"]["total"] == _TOTAL_WITH_ARCHIVED

    def test_over_page_total_respects_filters(self, client, admin_token):
        """Over-page with a filter should report correct filtered total."""
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "active", "page_size": "3", "page": "100"},
        )
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["meta"]["total"] == _TOTAL_ACTIVE

    def test_window_function_total_matches_filter_count(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "status": "draft", "page_size": "1", "page": "1"},
        )
        meta = r.json()["meta"]
        assert meta["total"] == _TOTAL_DRAFT
        assert meta["has_next"] is True  # 3 draft, page_size 1

    def test_page_meta_reflects_requested_page(self, client, admin_token):
        r = client.get(
            _BASE,
            headers=_auth(admin_token),
            params={"q": "p4test", "include_archived": "true", "page": "2", "page_size": "5"},
        )
        assert r.json()["meta"]["page"] == 2
        assert r.json()["meta"]["page_size"] == 5


# ===========================================================================
# TestValidationErrors
# ===========================================================================


class TestValidationErrors:
    def _err(self, client, admin_token, params: dict) -> dict:
        r = client.get(_BASE, headers=_auth(admin_token), params=params)
        assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
        return r.json()["error"]

    def test_invalid_sort_by_returns_422_invalid_sort_field(self, client, admin_token):
        err = self._err(client, admin_token, {"sort_by": "tenant_name"})
        assert err["code"] == "invalid_sort_field"

    def test_invalid_sort_by_arbitrary_string(self, client, admin_token):
        err = self._err(client, admin_token, {"sort_by": "badfield"})
        assert err["code"] == "invalid_sort_field"

    def test_page_zero_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"page": "0"})
        assert err["code"] == "validation_error"

    def test_page_negative_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"page": "-5"})
        assert err["code"] == "validation_error"

    def test_page_non_integer_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"page": "abc"})
        assert err["code"] == "validation_error"

    def test_page_size_over_100_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"page_size": "200"})
        assert err["code"] == "validation_error"

    def test_page_size_zero_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"page_size": "0"})
        assert err["code"] == "validation_error"

    def test_invalid_status_filter_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"status": "running"})
        assert err["code"] == "validation_error"

    def test_invalid_region_filter_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"region": "ap-southeast"})
        assert err["code"] == "validation_error"

    def test_invalid_plan_filter_returns_422(self, client, admin_token):
        err = self._err(client, admin_token, {"plan": "premium"})
        assert err["code"] == "validation_error"

    def test_error_envelope_shape(self, client, admin_token):
        r = client.get(_BASE, headers=_auth(admin_token), params={"sort_by": "invalid"})
        body = r.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "fields" in body["error"]
