"""
F056 P02 — Model + Schema Tests (15 tests)
============================================

Covers: AccessToken ORM model (is_valid, repr), Pydantic schemas
        (CreateTokenRequest validation, TokenResponse, CreateTokenResponse,
        TokenListResponse).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.models.access_token import AccessToken
from app.schemas.token import (
    CreateTokenRequest,
    CreateTokenResponse,
    TokenListResponse,
    TokenResponse,
)

_NOW = datetime.now(UTC)
_USER_ID = uuid4()


# ── AccessToken ORM model tests ─────────────────────────────────────────────


class TestAccessTokenModel:
    def test_is_valid_when_active(self):
        token = AccessToken()
        token.revoked_at = None
        token.expires_at = None
        assert token.is_valid() is True

    def test_is_valid_false_when_revoked(self):
        token = AccessToken()
        token.revoked_at = _NOW
        token.expires_at = None
        assert token.is_valid() is False

    def test_is_valid_false_when_expired(self):
        token = AccessToken()
        token.revoked_at = None
        token.expires_at = _NOW - timedelta(hours=1)
        assert token.is_valid() is False

    def test_is_valid_true_when_not_yet_expired(self):
        token = AccessToken()
        token.revoked_at = None
        token.expires_at = _NOW + timedelta(days=30)
        assert token.is_valid() is True

    def test_repr(self):
        token = AccessToken()
        token.name = "my-token"
        token.prefix = "dqai_abc1"
        r = repr(token)
        assert "my-token" in r
        assert "dqai_abc1" in r


# ── CreateTokenRequest schema tests ─────────────────────────────────────────


class TestCreateTokenRequest:
    def test_minimal_valid(self):
        req = CreateTokenRequest(name="test")
        assert req.name == "test"
        assert req.expires_in_days is None
        assert req.scopes == []

    def test_full_fields(self):
        req = CreateTokenRequest(name="full", expires_in_days=90, scopes=["read", "write"])
        assert req.expires_in_days == 90
        assert req.scopes == ["read", "write"]

    def test_empty_name_rejected(self):
        with pytest.raises(Exception):
            CreateTokenRequest(name="")

    def test_expires_in_days_bounds(self):
        with pytest.raises(Exception):
            CreateTokenRequest(name="test", expires_in_days=0)
        with pytest.raises(Exception):
            CreateTokenRequest(name="test", expires_in_days=366)


# ── TokenResponse schema tests ──────────────────────────────────────────────


class TestTokenResponse:
    def test_all_fields(self):
        resp = TokenResponse(
            id=uuid4(),
            name="tok",
            prefix="dqai_abc1",
            scopes=["read"],
            expires_at=_NOW + timedelta(days=30),
            last_used_at=_NOW,
            created_at=_NOW,
            revoked_at=None,
            is_valid=True,
        )
        assert resp.is_valid is True
        assert resp.scopes == ["read"]

    def test_optional_fields_none(self):
        resp = TokenResponse(
            id=uuid4(),
            name="tok",
            prefix="dqai_abc1",
            scopes=[],
            expires_at=None,
            last_used_at=None,
            created_at=_NOW,
            revoked_at=None,
            is_valid=True,
        )
        assert resp.expires_at is None
        assert resp.last_used_at is None


class TestCreateTokenResponse:
    def test_includes_plain_token(self):
        resp = CreateTokenResponse(
            id=uuid4(),
            name="tok",
            prefix="dqai_abc1",
            scopes=[],
            expires_at=None,
            last_used_at=None,
            created_at=_NOW,
            revoked_at=None,
            is_valid=True,
            token="dqai_secretvalue",
        )
        assert resp.token == "dqai_secretvalue"


class TestTokenListResponse:
    def test_shape(self):
        resp = TokenListResponse(tokens=[], total=0)
        assert resp.total == 0
        assert resp.tokens == []
