"""
Packet 8 — Unit tests: list_audit_logs endpoint query-parameter validation
==========================================================================

Tests cover the query-parameter validation logic in the HTTP handler
(``list_audit_logs`` in ``tenants.py``) and the ``TenantRepository.exists``
stub path.  All DB I/O is mocked; no Docker / live database is required.

Tested logic:
    - ``event_type`` enum validation  → 422 ``validation_error``
    - ``actor_id`` UUID v4 validation → 422 ``invalid_uuid_format``
    - ``from`` / ``to`` ISO 8601 parsing → 422 ``validation_error``
    - ``from > to`` detection         → 422 ``invalid_date_range``
    - ``page`` integer validation      → 422 ``validation_error``
    - ``page_size`` range validation   → 422 ``validation_error``
    - Tenant not-found pre-check       → 404 ``not_found``
    - Happy-path response shape        → 200

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/unit/services/f001/test_p8_audit_logs.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from app.api.v1.dependencies.tenant_auth import TenantAPIError
from fastapi.testclient import TestClient
from jose import jwt

# ---------------------------------------------------------------------------
# Helpers
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


_ADMIN_TOKEN: str | None = None
_VIEWER_TOKEN: str | None = None

_TENANT_ID = str(uuid.uuid4())

_BASE_URL = f"/api/v1/tenants/{_TENANT_ID}/audit-logs"


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


def _empty_list_result():
    """Patch return value for a successful but empty audit log query."""
    return ([], 0)


# ---------------------------------------------------------------------------
# Patch targets
# ---------------------------------------------------------------------------

_REPO_EXISTS = "app.api.v1.endpoints.tenants.TenantRepository.exists"
_REPO_LIST = "app.api.v1.endpoints.tenants.AuditLogRepository.list_by_tenant"


# ===========================================================================
# TestTenantExistsPrecheck
# ===========================================================================


class TestTenantExistsPrecheck:
    """Tenant existence pre-check before any query-param validation."""

    def test_nonexistent_tenant_returns_404(self, client, admin_token):
        with patch(_REPO_EXISTS, return_value=False):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"]["code"] == "not_found"

    def test_existing_tenant_proceeds(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        assert resp.status_code == 200


# ===========================================================================
# TestEventTypeValidation
# ===========================================================================


class TestEventTypeValidation:
    """event_type query parameter validation."""

    @pytest.mark.parametrize(
        "valid_et",
        [
            "tenant_created",
            "tenant_updated",
            "tenant_status_changed",
        ],
    )
    def test_valid_event_type_accepted(self, client, admin_token, valid_et):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"event_type": valid_et},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "bad_et",
        [
            "tenant_deleted",
            "TENANT_CREATED",
            "created",
            "",
            "unknown",
        ],
    )
    def test_invalid_event_type_returns_422(self, client, admin_token, bad_et):
        with patch(_REPO_EXISTS, return_value=True):
            resp = client.get(
                _BASE_URL,
                params={"event_type": bad_et},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"
        assert any(f["field"] == "event_type" for f in body["error"]["fields"])


# ===========================================================================
# TestActorIdValidation
# ===========================================================================


class TestActorIdValidation:
    """actor_id UUID v4 query parameter validation."""

    def test_valid_uuid_v4_accepted(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"actor_id": str(uuid.uuid4())},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "bad_id",
        [
            "not-a-uuid",
            "12345678-1234-5678-1234-567812345678",  # version 5, not 4
            "00000000-0000-0000-0000-000000000000",
            "plainstring",
            "12345",
        ],
    )
    def test_invalid_actor_id_returns_422(self, client, admin_token, bad_id):
        with patch(_REPO_EXISTS, return_value=True):
            resp = client.get(
                _BASE_URL,
                params={"actor_id": bad_id},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "invalid_uuid_format"
        assert any(f["field"] == "actor_id" for f in body["error"]["fields"])


# ===========================================================================
# TestDatetimeValidation
# ===========================================================================


class TestDatetimeValidation:
    """from / to ISO 8601 parsing and from > to detection."""

    _VALID_FROM = "2025-01-01T00:00:00Z"
    _VALID_TO = "2025-12-31T23:59:59Z"

    def test_valid_from_and_to_accepted(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"from": self._VALID_FROM, "to": self._VALID_TO},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200

    @pytest.mark.parametrize(
        "bad_dt,field_name",
        [
            ("not-a-date", "from"),
            ("2025-13-01T00:00:00Z", "from"),
            ("not-a-date", "to"),
        ],
    )
    def test_invalid_datetime_returns_422(self, client, admin_token, bad_dt, field_name):
        params: dict = {}
        if field_name == "from":
            params["from"] = bad_dt
        else:
            params["from"] = self._VALID_FROM
            params["to"] = bad_dt
        with patch(_REPO_EXISTS, return_value=True):
            resp = client.get(
                _BASE_URL,
                params=params,
                headers=_auth(admin_token),
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"

    def test_from_greater_than_to_returns_422(self, client, admin_token):
        with patch(_REPO_EXISTS, return_value=True):
            resp = client.get(
                _BASE_URL,
                params={"from": "2025-12-31T00:00:00Z", "to": "2025-01-01T00:00:00Z"},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "invalid_date_range"
        assert any(f["field"] == "from" for f in body["error"]["fields"])

    def test_from_equal_to_to_is_accepted(self, client, admin_token):
        """Boundary: from == to is valid (potential single-second window)."""
        ts = "2025-06-15T12:00:00Z"
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"from": ts, "to": ts},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200

    def test_only_from_supplied_is_valid(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"from": self._VALID_FROM},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200

    def test_only_to_supplied_is_valid(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"to": self._VALID_TO},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200


# ===========================================================================
# TestPaginationValidation
# ===========================================================================


class TestPaginationValidation:
    """page and page_size query parameter validation."""

    def test_default_pagination_applied(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["page"] == 1
        assert body["meta"]["page_size"] == 25

    def test_explicit_valid_pagination(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"page": "3", "page_size": "50"},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["page"] == 3
        assert body["meta"]["page_size"] == 50

    @pytest.mark.parametrize("bad_page", ["0", "-1", "abc", "1.5"])
    def test_invalid_page_returns_422(self, client, admin_token, bad_page):
        with patch(_REPO_EXISTS, return_value=True):
            resp = client.get(
                _BASE_URL,
                params={"page": bad_page},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"

    @pytest.mark.parametrize("bad_ps", ["0", "101", "-5", "abc"])
    def test_invalid_page_size_returns_422(self, client, admin_token, bad_ps):
        with patch(_REPO_EXISTS, return_value=True):
            resp = client.get(
                _BASE_URL,
                params={"page_size": bad_ps},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "validation_error"

    def test_page_size_1_is_accepted(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"page_size": "1"},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200
        assert resp.json()["meta"]["page_size"] == 1

    def test_page_size_100_is_accepted(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(
                _BASE_URL,
                params={"page_size": "100"},
                headers=_auth(admin_token),
            )
        assert resp.status_code == 200
        assert resp.json()["meta"]["page_size"] == 100


# ===========================================================================
# TestResponseShape
# ===========================================================================


class TestResponseShape:
    """Response envelope and field names (TDD §3.7)."""

    def _make_log_row(self, tenant_id: str) -> dict[str, Any]:
        return {
            "log_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "tenant_created",
            "actor_id": str(uuid.uuid4()),
            "actor_role": "platform_admin",
            "previous_data": None,
            "new_data": {"tenant_name": "Acme"},
            "occurred_at": datetime.now(tz=UTC),
            "reason": None,
        }

    def test_response_has_data_and_meta(self, client, admin_token):
        row = self._make_log_row(_TENANT_ID)
        with patch(_REPO_EXISTS, return_value=True), patch(_REPO_LIST, return_value=([row], 1)):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "meta" in body

    def test_log_object_has_nine_fields(self, client, admin_token):
        row = self._make_log_row(_TENANT_ID)
        with patch(_REPO_EXISTS, return_value=True), patch(_REPO_LIST, return_value=([row], 1)):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        log = resp.json()["data"][0]
        expected_fields = {
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
        assert set(log.keys()) == expected_fields

    def test_meta_has_four_fields(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        meta = resp.json()["meta"]
        assert set(meta.keys()) == {"total", "page", "page_size", "has_next"}

    def test_has_next_true_when_more_pages_exist(self, client, admin_token):
        row = self._make_log_row(_TENANT_ID)
        # page=1, page_size=1 (default 25 would give has_next False with total=1;
        # use page_size=1 and total=2 to force has_next=True)
        with patch(_REPO_EXISTS, return_value=True), patch(_REPO_LIST, return_value=([row], 2)):
            resp = client.get(
                _BASE_URL,
                params={"page_size": "1"},
                headers=_auth(admin_token),
            )
        assert resp.json()["meta"]["has_next"] is True

    def test_has_next_false_on_last_page(self, client, admin_token):
        row = self._make_log_row(_TENANT_ID)
        with patch(_REPO_EXISTS, return_value=True), patch(_REPO_LIST, return_value=([row], 1)):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        assert resp.json()["meta"]["has_next"] is False

    def test_previous_data_null_for_tenant_created(self, client, admin_token):
        row = self._make_log_row(_TENANT_ID)
        row["event_type"] = "tenant_created"
        row["previous_data"] = None
        with patch(_REPO_EXISTS, return_value=True), patch(_REPO_LIST, return_value=([row], 1)):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        log = resp.json()["data"][0]
        assert log["previous_data"] is None

    def test_occurred_at_is_iso_string(self, client, admin_token):
        row = self._make_log_row(_TENANT_ID)
        with patch(_REPO_EXISTS, return_value=True), patch(_REPO_LIST, return_value=([row], 1)):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        log = resp.json()["data"][0]
        # Should be a valid ISO 8601 string
        datetime.fromisoformat(log["occurred_at"].replace("Z", "+00:00"))


# ===========================================================================
# TestAccessControl
# ===========================================================================


class TestAccessControl:
    """Auth enforcement — 401/403/200."""

    def test_missing_token_returns_401(self, client):
        resp = client.get(_BASE_URL)
        assert resp.status_code == 401

    def test_customer_actor_returns_403(self, client):
        token = _make_token("customer_actor")
        resp = client.get(_BASE_URL, headers=_auth(token))
        assert resp.status_code == 403

    def test_platform_viewer_can_read(self, client, viewer_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(_BASE_URL, headers=_auth(viewer_token))
        assert resp.status_code == 200

    def test_platform_admin_can_read(self, client, admin_token):
        with (
            patch(_REPO_EXISTS, return_value=True),
            patch(_REPO_LIST, return_value=_empty_list_result()),
        ):
            resp = client.get(_BASE_URL, headers=_auth(admin_token))
        assert resp.status_code == 200


# ===========================================================================
# TestPathParameterValidation
# ===========================================================================


class TestPathParameterValidation:
    """Path parameter UUID v4 validation."""

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
        url = f"/api/v1/tenants/{bad_id}/audit-logs"
        resp = client.get(url, headers=_auth(admin_token))
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "invalid_path_parameter"
