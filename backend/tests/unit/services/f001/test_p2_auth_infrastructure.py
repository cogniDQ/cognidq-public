"""
Unit tests — F001 Packet 2: Authentication and Authorization Infrastructure

Tests the three components introduced by this packet:
  1. JWT validation middleware (_extract_bearer_token, _decode_token, get_actor_context)
  2. Role-based authorization guards (require_write_access, require_read_access)
  3. UUID v4 path parameter validator (validate_uuid_path_param)

These are pure-unit tests: no database, no network, no FastAPI app startup.

Run:
    pytest backend/tests/unit/services/f001/test_p2_auth_infrastructure.py -v
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from jose import jwt

# ---------------------------------------------------------------------------
# Helpers shared across test cases
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-for-packet-2-unit-tests"
_TEST_ALGORITHM = "HS256"

_ADMIN_ID = str(uuid.uuid4())
_VIEWER_ID = str(uuid.uuid4())
_CUSTOMER_ID = str(uuid.uuid4())


def _make_token(
    actor_id: str | None = None,
    actor_role: str | None = None,
    exp_delta_seconds: int = 3600,
    secret: str = _TEST_SECRET,
    algorithm: str = _TEST_ALGORITHM,
    include_actor_id: bool = True,
    include_actor_role: bool = True,
) -> str:
    """Create a signed JWT for testing purposes."""
    now = datetime.now(tz=UTC)
    payload: dict = {
        "iat": now,
        "exp": now + timedelta(seconds=exp_delta_seconds),
    }
    if include_actor_id:
        payload["actor_id"] = actor_id or _ADMIN_ID
    if include_actor_role:
        payload["actor_role"] = actor_role or "platform_admin"
    return jwt.encode(payload, secret, algorithm=algorithm)


def _make_mock_request(authorization: str | None = None) -> MagicMock:
    """Return a mock Request with the given Authorization header value."""
    req = MagicMock()
    req.headers = {}
    if authorization is not None:
        req.headers = {"Authorization": authorization}
    req.state = MagicMock()
    return req


# ---------------------------------------------------------------------------
# Section 1: JWT validation middleware
# ---------------------------------------------------------------------------


class TestExtractBearerToken:
    """Tests for _extract_bearer_token (the header parsing layer)."""

    def _call(self, header: str | None):
        from app.api.v1.dependencies.tenant_auth import _extract_bearer_token

        return _extract_bearer_token(header)

    def test_missing_header_raises_401(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call(None)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    def test_empty_string_header_raises_401(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("")
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    def test_missing_bearer_prefix_raises_401(self):
        """Header present but uses wrong scheme (e.g., 'Token ...')."""
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("Token abc123")
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    def test_bearer_prefix_without_token_raises_401(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("Bearer ")
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    def test_valid_bearer_header_returns_token(self):
        raw_token = "some.jwt.token"
        result = self._call(f"Bearer {raw_token}")
        assert result == raw_token


class TestDecodeToken:
    """Tests for _decode_token (JWT signature/expiry/issuer validation)."""

    def _call(self, token: str):
        from app.api.v1.dependencies.tenant_auth import _decode_token

        return _decode_token(token)

    @patch("app.api.v1.dependencies.tenant_auth.settings")
    def test_expired_token_raises_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        token = _make_token(exp_delta_seconds=-1)  # already expired
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call(token)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @patch("app.api.v1.dependencies.tenant_auth.settings")
    def test_invalid_signature_raises_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        token = _make_token(secret="wrong-secret")
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call(token)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @patch("app.api.v1.dependencies.tenant_auth.settings")
    def test_malformed_token_string_raises_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("not.a.valid.jwt.at.all")
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @patch("app.api.v1.dependencies.tenant_auth.settings")
    def test_valid_token_returns_payload_dict(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        token = _make_token(actor_id=_ADMIN_ID, actor_role="platform_admin")
        payload = self._call(token)
        assert payload["actor_id"] == _ADMIN_ID
        assert payload["actor_role"] == "platform_admin"

    @patch("app.api.v1.dependencies.tenant_auth.settings")
    def test_issuer_mismatch_raises_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = "https://auth.expected.example.com"

        # Token issued by a different authority (no iss claim at all)
        token = _make_token()
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call(token)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"


class TestBuildActorContext:
    """Tests for _build_actor_context (claim extraction layer)."""

    def _call(self, payload: dict):
        from app.api.v1.dependencies.tenant_auth import _build_actor_context

        return _build_actor_context(payload)

    def test_missing_actor_id_claim_raises_401(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call({"actor_role": "platform_admin"})
        assert exc_info.value.status_code == 401

    def test_missing_actor_role_claim_raises_401(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call({"actor_id": str(uuid.uuid4())})
        assert exc_info.value.status_code == 401

    def test_invalid_uuid_actor_id_raises_401(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call({"actor_id": "not-a-uuid", "actor_role": "platform_admin"})
        assert exc_info.value.status_code == 401

    def test_valid_claims_return_actor_context(self):
        from app.api.v1.dependencies.tenant_auth import ActorContext

        actor_id_str = str(uuid.uuid4())
        actor = self._call({"actor_id": actor_id_str, "actor_role": "platform_viewer"})
        assert isinstance(actor, ActorContext)
        assert actor.actor_id == UUID(actor_id_str)
        assert actor.actor_role == "platform_viewer"


class TestGetActorContextDependency:
    """End-to-end tests for the get_actor_context FastAPI dependency."""

    @pytest.mark.asyncio
    @patch("app.api.v1.dependencies.tenant_auth.settings")
    async def test_missing_header_returns_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        from app.api.v1.dependencies.tenant_auth import TenantAPIError, get_actor_context

        req = _make_mock_request(authorization=None)
        with pytest.raises(TenantAPIError) as exc_info:
            await get_actor_context(req)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @pytest.mark.asyncio
    @patch("app.api.v1.dependencies.tenant_auth.settings")
    async def test_malformed_bearer_header_returns_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        from app.api.v1.dependencies.tenant_auth import TenantAPIError, get_actor_context

        req = _make_mock_request(authorization="NotBearer abc")
        with pytest.raises(TenantAPIError) as exc_info:
            await get_actor_context(req)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @pytest.mark.asyncio
    @patch("app.api.v1.dependencies.tenant_auth.settings")
    async def test_expired_token_returns_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        from app.api.v1.dependencies.tenant_auth import TenantAPIError, get_actor_context

        token = _make_token(exp_delta_seconds=-10)
        req = _make_mock_request(authorization=f"Bearer {token}")
        with pytest.raises(TenantAPIError) as exc_info:
            await get_actor_context(req)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @pytest.mark.asyncio
    @patch("app.api.v1.dependencies.tenant_auth.settings")
    async def test_invalid_signature_returns_401(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        from app.api.v1.dependencies.tenant_auth import TenantAPIError, get_actor_context

        token = _make_token(secret="wrong-secret-entirely")
        req = _make_mock_request(authorization=f"Bearer {token}")
        with pytest.raises(TenantAPIError) as exc_info:
            await get_actor_context(req)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "unauthorized"

    @pytest.mark.asyncio
    @patch("app.api.v1.dependencies.tenant_auth.settings")
    async def test_valid_token_populates_actor_context(self, mock_settings):
        mock_settings.JWT_SECRET_KEY = _TEST_SECRET
        mock_settings.JWT_ALGORITHM = _TEST_ALGORITHM
        mock_settings.JWT_ISSUER = None

        from app.api.v1.dependencies.tenant_auth import ActorContext, get_actor_context

        actor_id_str = str(uuid.uuid4())
        token = _make_token(actor_id=actor_id_str, actor_role="platform_admin")
        req = _make_mock_request(authorization=f"Bearer {token}")

        actor = await get_actor_context(req)

        assert isinstance(actor, ActorContext)
        assert actor.actor_id == UUID(actor_id_str)
        assert actor.actor_role == "platform_admin"
        # Verify request.state is populated
        assert req.state.actor is actor


# ---------------------------------------------------------------------------
# Section 2: Role-based authorization guards
# ---------------------------------------------------------------------------


class TestRequireWriteAccess:
    """
    require_write_access() guard — only platform_admin passes.

    The inner _guard function is called directly with a pre-built ActorContext
    to bypass FastAPI's dependency injection in unit tests.
    """

    async def _run_guard(self, actor_role: str):
        from app.api.v1.dependencies.tenant_auth import ActorContext, require_write_access

        actor = ActorContext(actor_id=uuid.uuid4(), actor_role=actor_role)
        guard = require_write_access()
        # Call the inner coroutine directly, supplying actor explicitly.
        return await guard(actor=actor)

    @pytest.mark.asyncio
    async def test_platform_admin_passes(self):
        actor = await self._run_guard("platform_admin")
        assert actor.actor_role == "platform_admin"

    @pytest.mark.asyncio
    async def test_platform_viewer_on_write_guard_raises_403(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            await self._run_guard("platform_viewer")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"

    @pytest.mark.asyncio
    async def test_customer_actor_raises_403(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            await self._run_guard("customer_actor")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"

    @pytest.mark.asyncio
    async def test_unrecognized_role_raises_403(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            await self._run_guard("some_future_role")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"


class TestRequireReadAccess:
    """
    require_read_access() guard — platform_admin and platform_viewer pass.
    """

    async def _run_guard(self, actor_role: str):
        from app.api.v1.dependencies.tenant_auth import ActorContext, require_read_access

        actor = ActorContext(actor_id=uuid.uuid4(), actor_role=actor_role)
        guard = require_read_access()
        return await guard(actor=actor)

    @pytest.mark.asyncio
    async def test_platform_admin_passes(self):
        actor = await self._run_guard("platform_admin")
        assert actor.actor_role == "platform_admin"

    @pytest.mark.asyncio
    async def test_platform_viewer_passes(self):
        actor = await self._run_guard("platform_viewer")
        assert actor.actor_role == "platform_viewer"

    @pytest.mark.asyncio
    async def test_customer_actor_raises_403(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            await self._run_guard("customer_actor")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"

    @pytest.mark.asyncio
    async def test_unrecognized_role_raises_403(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            await self._run_guard("analyst")
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "forbidden"


# ---------------------------------------------------------------------------
# Section 3: UUID v4 path parameter validator
# ---------------------------------------------------------------------------


class TestValidateUuidPathParam:
    """
    UUID decision: UUID v1/v3/v5 are rejected.  Only UUID v4 (version nibble = 4,
    variant bits = [89ab]) are accepted.
    """

    def _call(self, value: str) -> UUID:
        from app.api.v1.dependencies.tenant_auth import validate_uuid_path_param

        return validate_uuid_path_param(value, param_name="tenant_id")

    # ── Happy-path cases ────────────────────────────────────────────────────

    def test_lowercase_uuid_v4_passes(self):
        v = "550e8400-e29b-41d4-a716-446655440000"
        result = self._call(v)
        assert isinstance(result, UUID)
        assert str(result) == v

    def test_uppercase_uuid_v4_passes(self):
        v = "550E8400-E29B-41D4-A716-446655440000"
        result = self._call(v)
        assert isinstance(result, UUID)
        # UUID normalises to lowercase
        assert str(result) == v.lower()

    def test_freshly_generated_uuid4_passes(self):
        v = str(uuid.uuid4())
        result = self._call(v)
        assert isinstance(result, UUID)
        assert result == uuid.UUID(v)

    # ── Rejection cases ─────────────────────────────────────────────────────

    def test_plain_string_raises_400(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("not-a-uuid")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_path_parameter"

    def test_numeric_string_raises_400(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("123")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_path_parameter"

    def test_empty_string_raises_400(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_path_parameter"

    def test_uuid_v1_format_raises_400(self):
        """UUID v1: version nibble is 1, not 4 — must be rejected."""
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        uuid_v1 = str(uuid.uuid1())  # real UUID v1
        with pytest.raises(TenantAPIError) as exc_info:
            self._call(uuid_v1)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_path_parameter"

    def test_uuid_wrong_variant_bits_raises_400(self):
        """Variant nibble outside [89ab] — structurally invalid RFC 4122."""
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        # Replace the variant nibble with 'c' (invalid for RFC 4122 UUID)
        bad_variant = "550e8400-e29b-41d4-c716-446655440000"
        with pytest.raises(TenantAPIError) as exc_info:
            self._call(bad_variant)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_path_parameter"

    def test_almost_uuid_missing_segment_raises_400(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        with pytest.raises(TenantAPIError) as exc_info:
            self._call("550e8400-e29b-41d4-a716")  # truncated
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_path_parameter"


# ---------------------------------------------------------------------------
# Section 4: Error envelope shape
# ---------------------------------------------------------------------------


class TestTenantAPIError:
    """Verify the error envelope fields are correctly set on TenantAPIError."""

    def test_fields_are_stored(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        exc = TenantAPIError(422, "validation_error", "Bad input", [{"field": "x", "reason": "y"}])
        assert exc.status_code == 422
        assert exc.code == "validation_error"
        assert exc.message == "Bad input"
        assert exc.fields == [{"field": "x", "reason": "y"}]

    def test_fields_defaults_to_none(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError

        exc = TenantAPIError(401, "unauthorized", "Missing header")
        assert exc.fields is None

    @pytest.mark.asyncio
    async def test_handler_produces_correct_json_shape(self):
        from app.api.v1.dependencies.tenant_auth import TenantAPIError, tenant_api_error_handler

        exc = TenantAPIError(403, "forbidden", "Not allowed", None)
        req = _make_mock_request()
        response = await tenant_api_error_handler(req, exc)

        assert response.status_code == 403
        import json

        body = json.loads(response.body)
        assert body["error"]["code"] == "forbidden"
        assert body["error"]["message"] == "Not allowed"
        assert body["error"]["fields"] is None
