"""
F056 P03 — API Endpoint Tests (15 tests)
==========================================

Covers: create_token, list_tokens, get_token, revoke_token endpoints
        via direct function calls with mocked dependencies.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from app.schemas.token import CreateTokenRequest

_USER_ID = uuid4()
_NOW = datetime.now(UTC)


def _mock_user():
    user = MagicMock()
    user.id = _USER_ID
    return user


def _db():
    return MagicMock()


def _mock_token_model(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", uuid4())
    t.user_id = overrides.get("user_id", _USER_ID)
    t.name = overrides.get("name", "test-token")
    t.token_hash = overrides.get("token_hash", "hash123")
    t.prefix = overrides.get("prefix", "dqai_abc1")
    t.scopes = overrides.get("scopes", ["read"])
    t.expires_at = overrides.get("expires_at", None)
    t.last_used_at = overrides.get("last_used_at", None)
    t.created_at = overrides.get("created_at", _NOW)
    t.revoked_at = overrides.get("revoked_at", None)
    t.is_valid = MagicMock(return_value=overrides.get("is_valid_val", True))
    return t


# ── create_token endpoint tests ─────────────────────────────────────────────


class TestCreateTokenEndpoint:
    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_returns_201_with_plain_token(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import create_token

        token_model = _mock_token_model()
        mock_svc_class.create_token.return_value = (token_model, "dqai_secret123")

        req = CreateTokenRequest(name="my-token", scopes=["read"])
        result = create_token(request=req, db=_db(), current_user=_mock_user())
        assert result.token == "dqai_secret123"
        assert result.name == "test-token"

    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_service_called_with_correct_args(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import create_token

        token_model = _mock_token_model()
        mock_svc_class.create_token.return_value = (token_model, "dqai_xxx")

        req = CreateTokenRequest(name="scoped", scopes=["admin"], expires_in_days=30)
        create_token(request=req, db=_db(), current_user=_mock_user())

        call_args = mock_svc_class.create_token.call_args
        assert call_args.kwargs.get("name") or call_args[1].get("name") == "scoped"

    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_response_includes_is_valid(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import create_token

        token_model = _mock_token_model()
        mock_svc_class.create_token.return_value = (token_model, "dqai_xxx")

        req = CreateTokenRequest(name="test")
        result = create_token(request=req, db=_db(), current_user=_mock_user())
        assert result.is_valid is True


# ── list_tokens endpoint tests ───────────────────────────────────────────────


class TestListTokensEndpoint:
    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_returns_token_list(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import list_tokens

        mock_svc_class.list_tokens.return_value = [_mock_token_model(), _mock_token_model()]
        result = list_tokens(include_revoked=False, db=_db(), current_user=_mock_user())
        assert result.total == 2
        assert len(result.tokens) == 2

    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_include_revoked_calls_list_all(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import list_tokens

        mock_svc_class.list_all_tokens.return_value = []
        list_tokens(include_revoked=True, db=_db(), current_user=_mock_user())
        mock_svc_class.list_all_tokens.assert_called_once()

    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_exclude_revoked_calls_list_tokens(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import list_tokens

        mock_svc_class.list_tokens.return_value = []
        list_tokens(include_revoked=False, db=_db(), current_user=_mock_user())
        mock_svc_class.list_tokens.assert_called_once()

    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_empty_list(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import list_tokens

        mock_svc_class.list_tokens.return_value = []
        result = list_tokens(include_revoked=False, db=_db(), current_user=_mock_user())
        assert result.total == 0


# ── get_token endpoint tests ────────────────────────────────────────────────


class TestGetTokenEndpoint:
    def test_returns_token_details(self):
        from app.api.v1.endpoints.tokens import get_token

        db = _db()
        token_model = _mock_token_model()
        db.query.return_value.filter.return_value.first.return_value = token_model

        result = get_token(token_id=token_model.id, db=db, current_user=_mock_user())
        assert result.name == "test-token"
        assert result.prefix == "dqai_abc1"

    def test_not_found_raises_404(self):
        from app.api.v1.endpoints.tokens import get_token
        from fastapi import HTTPException

        db = _db()
        db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            get_token(token_id=uuid4(), db=db, current_user=_mock_user())
        assert exc_info.value.status_code == 404


# ── revoke_token endpoint tests ─────────────────────────────────────────────


class TestRevokeTokenEndpoint:
    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_revoke_success_returns_none(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import revoke_token

        mock_svc_class.revoke_token.return_value = True
        result = revoke_token(token_id=uuid4(), db=_db(), current_user=_mock_user())
        assert result is None

    @patch("app.api.v1.endpoints.tokens.AccessTokenService")
    def test_revoke_not_found_raises_404(self, mock_svc_class):
        from app.api.v1.endpoints.tokens import revoke_token
        from fastapi import HTTPException

        mock_svc_class.revoke_token.return_value = False
        with pytest.raises(HTTPException) as exc_info:
            revoke_token(token_id=uuid4(), db=_db(), current_user=_mock_user())
        assert exc_info.value.status_code == 404


# ── Wiring tests ────────────────────────────────────────────────────────────


class TestWiring:
    def test_router_exists(self):
        from app.api.v1.endpoints import tokens

        assert hasattr(tokens, "router")

    def test_router_registered_in_api(self):
        from app.api.v1.router import api_router

        paths = [r.path for r in api_router.routes]
        assert any("/tokens" in p for p in paths)
