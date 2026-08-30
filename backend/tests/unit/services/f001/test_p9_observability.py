"""
Packet 9 — Unit tests: Observability (Correlation ID, Structured Logging, Metrics)
====================================================================================

Tests cover (TDD §8.1 / §8.2):

    CorrelationIdMiddleware
        - X-Correlation-Id header present on every response (success + error)
        - Header value is a valid UUID v4
        - Header is server-generated — client-supplied header is NOT echoed
        - Different requests receive different correlation IDs
        - Middleware adds header to error responses (4xx / 5xx)
        - Structured log is emitted with all TDD §8.2 fields
        - Structured log failure does not affect HTTP response

    Metric Emission — fire-and-forget
        - emit_tenant_create_success failure does not change 201 response
        - emit_tenant_create_failure("invalid_input") fires on validator errors
        - emit_tenant_create_failure("unauthorized") fires on auth rejection (401/403)
        - emit_tenant_status_change called with correct from/to labels
        - emit_session_invalidation_sla_breach fires with tenant_id label

    Registry WARN log
        - WARN-level log emitted when workspace/user registry call fails
        - Log entry contains registry name, tenant_id, and exception message

All DB I/O is mocked — no Docker / live database required.

Run inside Docker::

    docker-compose exec backend python -m pytest \\
        tests/unit/services/f001/test_p9_observability.py -v
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# UUID v4 regex for header value assertions
# ---------------------------------------------------------------------------

_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ===========================================================================
# TestCorrelationIdMiddleware — test via a minimal in-process FastAPI app
# so that no real DB or JWT infrastructure is required.
# ===========================================================================


def _make_mini_app() -> FastAPI:
    """Return a minimal FastAPI app with CorrelationIdMiddleware attached."""
    from app.middleware.correlation import CorrelationIdMiddleware

    mini = FastAPI()
    mini.add_middleware(CorrelationIdMiddleware)

    @mini.get("/ok")
    def ok_endpoint():
        return {"status": "ok"}

    @mini.get("/error")
    def error_endpoint():
        return JSONResponse(status_code=400, content={"error": "bad_request"})

    @mini.get("/server-error")
    def server_error_endpoint():
        return JSONResponse(status_code=500, content={"error": "internal"})

    return mini


@pytest.fixture(scope="module")
def mini_client():
    """TestClient wrapping the minimal app — no DB dependency."""
    app = _make_mini_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestCorrelationIdHeader:
    """X-Correlation-Id header is present and valid on every response."""

    def test_header_present_on_200(self, mini_client):
        resp = mini_client.get("/ok")
        assert resp.status_code == 200
        assert "x-correlation-id" in resp.headers

    def test_header_present_on_400(self, mini_client):
        resp = mini_client.get("/error")
        assert resp.status_code == 400
        assert "x-correlation-id" in resp.headers

    def test_header_present_on_500(self, mini_client):
        resp = mini_client.get("/server-error")
        assert resp.status_code == 500
        assert "x-correlation-id" in resp.headers

    def test_header_is_uuid_v4(self, mini_client):
        resp = mini_client.get("/ok")
        cid = resp.headers["x-correlation-id"]
        assert _UUID_V4_RE.match(cid), f"Not a UUID v4: {cid!r}"

    def test_different_requests_get_different_ids(self, mini_client):
        r1 = mini_client.get("/ok")
        r2 = mini_client.get("/ok")
        assert r1.headers["x-correlation-id"] != r2.headers["x-correlation-id"]

    def test_client_supplied_id_is_not_echoed(self, mini_client):
        """Server must generate the ID; any request header must be ignored."""
        client_id = "00000000-0000-4000-8000-000000000000"
        resp = mini_client.get("/ok", headers={"X-Correlation-Id": client_id})
        server_cid = resp.headers["x-correlation-id"]
        # The server's generated ID must differ from the client-supplied one
        assert server_cid != client_id

    def test_header_value_not_empty(self, mini_client):
        resp = mini_client.get("/ok")
        assert resp.headers["x-correlation-id"].strip() != ""


class TestStructuredLogging:
    """Structured log is emitted with required TDD §8.2 fields."""

    def test_logger_called_on_success(self, mini_client):
        """Logger.info is called and contains the required field keys."""
        with patch("app.middleware.correlation.logger") as mock_log:
            resp = mini_client.get("/ok")
        assert resp.status_code == 200
        assert mock_log.info.called
        # Verify the log message format string contains all required field names
        call_args = mock_log.info.call_args
        fmt_str: str = call_args[0][0]  # first positional arg is the format string
        for field in (
            "correlation_id",
            "actor_id",
            "actor_role",
            "tenant_id",
            "operation",
            "outcome",
            "error_code",
        ):
            assert field in fmt_str, f"Field '{field}' missing from log format string"

    def test_logger_called_on_error(self, mini_client):
        """Logger.info is still called on 4xx responses."""
        with patch("app.middleware.correlation.logger") as mock_log:
            resp = mini_client.get("/error")
        assert resp.status_code == 400
        assert mock_log.info.called

    def test_structured_log_failure_does_not_affect_response(self, mini_client):
        """A crash in the structured log block must not change the response."""
        with patch("app.middleware.correlation.logger") as mock_log:
            mock_log.info.side_effect = RuntimeError("logging infrastructure down")
            resp = mini_client.get("/ok")
        # Response must still be 200 with X-Correlation-Id header
        assert resp.status_code == 200
        assert "x-correlation-id" in resp.headers

    def test_outcome_success_on_2xx(self, mini_client):
        """Outcome field uses 'success' string for 2xx responses."""
        logged_args = []
        with patch("app.middleware.correlation.logger") as mock_log:
            mock_log.info.side_effect = lambda fmt, *args, **kw: logged_args.extend(args)
            mini_client.get("/ok")
        # The 5th positional arg after format string is 'outcome'
        outcome_value = logged_args[
            5
        ]  # correlation_id, actor_id, actor_role, tenant_id, operation, outcome
        assert outcome_value == "success"

    def test_outcome_failure_on_4xx(self, mini_client):
        """Outcome field uses 'failure' string for 4xx responses."""
        logged_args = []
        with patch("app.middleware.correlation.logger") as mock_log:
            mock_log.info.side_effect = lambda fmt, *args, **kw: logged_args.extend(args)
            mini_client.get("/error")
        outcome_value = logged_args[5]
        assert outcome_value == "failure"


# ===========================================================================
# TestOperationInference — unit-level tests of the helper functions
# ===========================================================================


class TestOperationInference:
    """_infer_operation correctly maps method + path to operation names."""

    def setup_method(self):
        from app.middleware.correlation import _infer_operation

        self._fn = _infer_operation

    def test_create_tenant(self):
        assert self._fn("POST", "/api/v1/tenants") == "create_tenant"

    def test_list_tenants(self):
        assert self._fn("GET", "/api/v1/tenants") == "list_tenants"

    def test_get_tenant_detail(self):
        tid = "123e4567-e89b-42d3-a456-426614174000"
        assert self._fn("GET", f"/api/v1/tenants/{tid}") == "get_tenant_detail"

    def test_update_tenant(self):
        tid = "123e4567-e89b-42d3-a456-426614174000"
        assert self._fn("PATCH", f"/api/v1/tenants/{tid}") == "update_tenant"

    def test_change_status(self):
        tid = "123e4567-e89b-42d3-a456-426614174000"
        assert self._fn("POST", f"/api/v1/tenants/{tid}/status") == "change_status"

    def test_list_audit_logs(self):
        tid = "123e4567-e89b-42d3-a456-426614174000"
        assert self._fn("GET", f"/api/v1/tenants/{tid}/audit-logs") == "list_audit_logs"

    def test_unknown_path_returns_unknown(self):
        assert self._fn("GET", "/api/v1/other") == "unknown"

    def test_health_endpoint_returns_unknown(self):
        assert self._fn("GET", "/health") == "unknown"


class TestTenantIdExtraction:
    """_extract_tenant_id correctly extracts the UUID from known path shapes."""

    def setup_method(self):
        from app.middleware.correlation import _extract_tenant_id

        self._fn = _extract_tenant_id

    def test_extracts_from_detail_path(self):
        tid = "123e4567-e89b-42d3-a456-426614174000"
        assert self._fn(f"/api/v1/tenants/{tid}") == tid

    def test_extracts_from_status_path(self):
        tid = "123e4567-e89b-42d3-a456-426614174000"
        assert self._fn(f"/api/v1/tenants/{tid}/status") == tid

    def test_returns_none_for_list_path(self):
        assert self._fn("/api/v1/tenants") is None

    def test_returns_none_for_non_tenant_path(self):
        assert self._fn("/health") is None


# ===========================================================================
# TestMetricFireAndForget — using the full production app with mocked DB
# ===========================================================================


def _get_settings():
    from app.core.config import settings

    return settings


def _make_admin_token() -> str:
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    s = _get_settings()
    payload = {
        "actor_id": str(uuid.uuid4()),
        "actor_role": "platform_admin",
        "exp": datetime.now(tz=UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)


@pytest.fixture(scope="module")
def full_client():
    """Module-scoped TestClient for the full production app."""
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token() -> str:
    return _make_admin_token()


_VALID_CREATE_BODY: dict[str, Any] = {
    "tenant_name": "Metric Test Corp",
    "tenant_slug": "metric-test-corp",
    "region": "eu-west",
    "plan": "starter",
    "initial_status": "draft",
}


class TestMetricFireAndForget:
    """Metric emission failures must never alter the API response."""

    def test_create_success_metric_failure_still_returns_201(self, full_client, admin_token):
        """emit_tenant_create_success raising must not change 201 response."""
        tenant_id = str(uuid.uuid4())
        fake_row = {
            "tenant_id": uuid.UUID(tenant_id),
            "tenant_name": "Metric Test Corp",
            "tenant_slug": "metric-test-corp",
            "status": "draft",
            "status_reason": None,
            "region": "eu-west",
            "plan": "starter",
            "service_start_date": None,
            "tenant_notes": None,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
            "created_by": str(uuid.uuid4()),
            "updated_by": str(uuid.uuid4()),
        }

        with (
            patch(
                "app.services.tenants.repository.TenantRepository.check_name_exists",
                return_value=False,
            ),
            patch(
                "app.services.tenants.repository.TenantRepository.check_slug_exists",
                return_value=False,
            ),
            patch("app.services.tenants.repository.TenantRepository.insert", return_value=fake_row),
            patch("app.services.tenants.repository.AuditLogRepository.insert"),
            patch(
                "app.services.tenants.service.emit_tenant_create_success",
                side_effect=RuntimeError("prom down"),
            ),
        ):
            resp = full_client.post(
                "/api/v1/tenants",
                json=_VALID_CREATE_BODY,
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        # Even though the metric emitter exploded, the API must return 201
        assert resp.status_code == 201

    def test_create_failure_metric_failure_still_returns_422(self, full_client, admin_token):
        """emit_tenant_create_failure raising must not change 422 response."""
        with (
            patch(
                "app.services.tenants.repository.TenantRepository.check_name_exists",
                return_value=True,
            ),
            patch(
                "app.services.tenants.metrics.emit_tenant_create_failure",
                side_effect=RuntimeError("prom down"),
            ),
        ):
            resp = full_client.post(
                "/api/v1/tenants",
                json=_VALID_CREATE_BODY,
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert resp.status_code == 422

    def test_x_correlation_id_present_on_201(self, full_client, admin_token):
        """X-Correlation-Id must be present even on successful create."""
        tenant_id = str(uuid.uuid4())
        fake_row = {
            "tenant_id": uuid.UUID(tenant_id),
            "tenant_name": "Metric Test Corp",
            "tenant_slug": "metric-test-corp",
            "status": "draft",
            "status_reason": None,
            "region": "eu-west",
            "plan": "starter",
            "service_start_date": None,
            "tenant_notes": None,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
            "created_by": str(uuid.uuid4()),
            "updated_by": str(uuid.uuid4()),
        }

        with (
            patch(
                "app.services.tenants.repository.TenantRepository.check_name_exists",
                return_value=False,
            ),
            patch(
                "app.services.tenants.repository.TenantRepository.check_slug_exists",
                return_value=False,
            ),
            patch("app.services.tenants.repository.TenantRepository.insert", return_value=fake_row),
            patch("app.services.tenants.repository.AuditLogRepository.insert"),
            patch("app.services.tenants.service.emit_tenant_create_success"),
        ):
            resp = full_client.post(
                "/api/v1/tenants",
                json=_VALID_CREATE_BODY,
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert "x-correlation-id" in resp.headers
        assert _UUID_V4_RE.match(resp.headers["x-correlation-id"])


class TestInvalidInputMetric:
    """emit_tenant_create_failure("invalid_input") fires on validator rejections."""

    def test_invalid_region_emits_invalid_input(self, full_client, admin_token):
        emitted: list = []

        def capture(reason):
            emitted.append(reason)

        with patch("app.api.v1.endpoints.tenants.emit_tenant_create_failure", side_effect=capture):
            resp = full_client.post(
                "/api/v1/tenants",
                json={**_VALID_CREATE_BODY, "region": "not-a-region"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert resp.status_code == 422
        assert "invalid_input" in emitted

    def test_invalid_plan_emits_invalid_input(self, full_client, admin_token):
        emitted: list = []

        def capture(reason):
            emitted.append(reason)

        with patch("app.api.v1.endpoints.tenants.emit_tenant_create_failure", side_effect=capture):
            resp = full_client.post(
                "/api/v1/tenants",
                json={**_VALID_CREATE_BODY, "plan": "enterprise-gold-plus"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert resp.status_code == 422
        assert "invalid_input" in emitted

    def test_invalid_input_metric_failure_does_not_change_422(self, full_client, admin_token):
        """emit_tenant_create_failure raising during invalid_input must not
        affect the 422 response."""
        with patch(
            "app.api.v1.endpoints.tenants.emit_tenant_create_failure",
            side_effect=RuntimeError("metric down"),
        ):
            resp = full_client.post(
                "/api/v1/tenants",
                json={**_VALID_CREATE_BODY, "region": "badregion"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert resp.status_code == 422


class TestUnauthorizedMetric:
    """emit_tenant_create_failure("unauthorized") fires on auth rejections."""

    def test_missing_token_emits_unauthorized(self, full_client):
        emitted: list = []

        def capture(reason):
            emitted.append(reason)

        with patch("app.middleware.correlation.emit_tenant_create_failure", side_effect=capture):
            resp = full_client.post("/api/v1/tenants", json=_VALID_CREATE_BODY)

        assert resp.status_code == 401
        assert "unauthorized" in emitted

    def test_invalid_token_emits_unauthorized(self, full_client):
        emitted: list = []

        def capture(reason):
            emitted.append(reason)

        with patch("app.middleware.correlation.emit_tenant_create_failure", side_effect=capture):
            resp = full_client.post(
                "/api/v1/tenants",
                json=_VALID_CREATE_BODY,
                headers={"Authorization": "Bearer invalid.jwt.token"},
            )

        assert resp.status_code == 401
        assert "unauthorized" in emitted

    def test_unauthorized_metric_failure_does_not_affect_401(self, full_client):
        """A crash in the unauthorized metric emission must not change the 401."""
        with patch(
            "app.middleware.correlation.emit_tenant_create_failure",
            side_effect=RuntimeError("prom down"),
        ):
            resp = full_client.post("/api/v1/tenants", json=_VALID_CREATE_BODY)

        assert resp.status_code == 401


# ===========================================================================
# TestRegistryWarnLog — _safe_registry_call WARN on any failure
# ===========================================================================


class TestRegistryWarnLog:
    """_safe_registry_call emits a WARN log on registry call failure."""

    def test_warn_logged_on_registry_error(self):
        """When the registry client raises, a WARNING is logged with key fields."""
        from app.services.tenants.service import _safe_registry_call

        stub_err_client = MagicMock()
        stub_err_client.get_count.side_effect = RuntimeError("connection refused")

        with patch("app.services.tenants.service.logger") as mock_logger:
            count, available = _safe_registry_call(stub_err_client, "tenant-uuid-x", "workspace")

        assert count == 0
        assert available is False
        assert mock_logger.warning.called
        mock_logger.warning.call_args[0][0]
        # The WARN message format must include template markers for the key fields
        assert "workspace" in str(mock_logger.warning.call_args)
        assert "tenant-uuid-x" in str(mock_logger.warning.call_args)

    def test_warn_logged_on_user_registry_error(self):
        from app.services.tenants.service import _safe_registry_call

        stub_err_client = MagicMock()
        stub_err_client.get_count.side_effect = TimeoutError("timed out")

        with patch("app.services.tenants.service.logger") as mock_logger:
            count, available = _safe_registry_call(stub_err_client, "tenant-uuid-y", "user")

        assert count == 0
        assert available is False
        assert mock_logger.warning.called

    def test_no_warn_on_registry_success(self):
        """No warning must be logged when registry responds normally."""
        from app.services.tenants.service import _safe_registry_call

        stub_ok_client = MagicMock()
        stub_ok_client.get_count.return_value = 5

        with patch("app.services.tenants.service.logger") as mock_logger:
            count, available = _safe_registry_call(stub_ok_client, "tenant-uuid-z", "workspace")

        assert count == 5
        assert available is True
        assert not mock_logger.warning.called


# ===========================================================================
# TestSlaBreachMetric — emit_session_invalidation_sla_breach
# ===========================================================================


class TestSlaBreachMetric:
    """emit_session_invalidation_sla_breach fires with tenant_id label."""

    def test_sla_breach_logs_warning_with_tenant_id(self):
        from app.services.tenants.metrics import emit_session_invalidation_sla_breach

        with patch("app.services.tenants.metrics.logger") as mock_log:
            emit_session_invalidation_sla_breach("some-tenant-uuid")

        assert mock_log.warning.called
        warn_args = str(mock_log.warning.call_args)
        assert "some-tenant-uuid" in warn_args

    def test_sla_breach_is_fire_and_forget(self):
        """Even if the logger explodes, the function must not raise."""
        from app.services.tenants.metrics import emit_session_invalidation_sla_breach

        with patch("app.services.tenants.metrics.logger") as mock_log:
            mock_log.warning.side_effect = RuntimeError("logger is broken")
            # Must not raise
            emit_session_invalidation_sla_breach("any-tenant")

    def test_outbox_poller_delegates_to_metrics_module(self):
        """_emit_sla_breach in outbox.py delegates to emit_session_invalidation_sla_breach."""
        from app.services.tenants.outbox import _emit_sla_breach

        with patch(
            "app.services.tenants.outbox.emit_session_invalidation_sla_breach"
        ) as mock_metric:
            _emit_sla_breach("test-tenant-id-abc")

        mock_metric.assert_called_once_with("test-tenant-id-abc")


# ===========================================================================
# TestMetricLabels — verify correct label values in each scenario
# ===========================================================================


class TestMetricLabels:
    """All metric label values conform to TDD §8.1 specification."""

    def test_create_success_emits_correct_labels(self):
        """emit_tenant_create_success receives region, plan, initial_status."""
        from app.services.tenants.metrics import emit_tenant_create_success

        with patch("app.services.tenants.metrics.logger") as mock_log:
            emit_tenant_create_success(
                region="eu-west",
                plan="starter",
                initial_status="draft",
            )

        assert mock_log.debug.called
        debug_str = str(mock_log.debug.call_args)
        assert "eu-west" in debug_str
        assert "starter" in debug_str
        assert "draft" in debug_str

    def test_status_change_emits_from_and_to(self):
        from app.services.tenants.metrics import emit_tenant_status_change

        with patch("app.services.tenants.metrics.logger") as mock_log:
            emit_tenant_status_change(from_status="active", to_status="suspended")

        debug_str = str(mock_log.debug.call_args)
        assert "active" in debug_str
        assert "suspended" in debug_str

    @pytest.mark.parametrize(
        "reason",
        [
            "duplicate_name",
            "duplicate_slug",
            "invalid_input",
            "unauthorized",
            "internal_error",
        ],
    )
    def test_create_failure_accepts_all_tdd_reasons(self, reason):
        """All five TDD §8.1 failure_reason values must be accepted
        (i.e., the function does not raise for any of them)."""
        from app.services.tenants.metrics import emit_tenant_create_failure

        # Must not raise for any valid reason label
        emit_tenant_create_failure(reason)
