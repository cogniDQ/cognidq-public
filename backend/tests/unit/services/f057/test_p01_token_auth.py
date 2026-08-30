"""
F057 P01 — API Token Auth Dependency & Scope Guard Tests
==========================================================

Tests for get_api_token, get_token_user, ScopeChecker, and VALID_SCOPES.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.models.access_token import AccessToken
from app.services.auth.api_token_auth import (
    VALID_SCOPES,
    ScopeChecker,
    get_api_token,
    get_token_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(scopes=None, user_id=None):
    tok = MagicMock(spec=AccessToken)
    tok.id = uuid.uuid4()
    tok.user_id = user_id or uuid.uuid4()
    tok.scopes = scopes or []
    tok.name = "test-token"
    tok.prefix = "dqai_abcd"
    tok.is_valid.return_value = True
    return tok


def _make_user(user_id=None, user_status="ACTIVE"):
    return SimpleNamespace(
        id=user_id or uuid.uuid4(),
        status=user_status,
        email="test@example.com",
        tenant_id=uuid.uuid4(),
        platform_role="admin",
    )


def _make_credentials(token_str="dqai_testtoken123"):
    return SimpleNamespace(credentials=token_str)


# ---------------------------------------------------------------------------
# VALID_SCOPES
# ---------------------------------------------------------------------------


class TestValidScopes:
    def test_contains_expected_scopes(self):
        expected = {
            "read:datasets",
            "read:rules",
            "read:executions",
            "read:issues",
            "read:incidents",
            "write:datasets",
            "write:rules",
            "write:executions",
            "write:issues",
        }
        assert expected == VALID_SCOPES

    def test_is_frozenset(self):
        assert isinstance(VALID_SCOPES, frozenset)

    def test_five_scopes(self):
        assert len(VALID_SCOPES) == 9


# ---------------------------------------------------------------------------
# get_api_token
# ---------------------------------------------------------------------------


class TestGetApiToken:
    @pytest.mark.asyncio
    @patch("app.services.auth.api_token_auth.AccessTokenService")
    async def test_valid_token_returns_access_token(self, mock_svc):
        token = _make_token()
        mock_svc.verify_token.return_value = token
        db = MagicMock()
        creds = _make_credentials()

        result = await get_api_token(credentials=creds, db=db)

        assert result is token
        mock_svc.verify_token.assert_called_once_with(db, "dqai_testtoken123")

    @pytest.mark.asyncio
    @patch("app.services.auth.api_token_auth.AccessTokenService")
    async def test_invalid_token_raises_401(self, mock_svc):
        mock_svc.verify_token.return_value = None
        db = MagicMock()
        creds = _make_credentials("bad_token")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_api_token(credentials=creds, db=db)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    @patch("app.services.auth.api_token_auth.AccessTokenService")
    async def test_expired_token_raises_401(self, mock_svc):
        mock_svc.verify_token.return_value = None  # service returns None for expired
        db = MagicMock()
        creds = _make_credentials()

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_api_token(credentials=creds, db=db)

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# get_token_user
# ---------------------------------------------------------------------------


class TestGetTokenUser:
    @pytest.mark.asyncio
    async def test_returns_user(self):
        uid = uuid.uuid4()
        token = _make_token(user_id=uid)
        user = _make_user(user_id=uid)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        result = await get_token_user(token=token, db=db)

        assert result is user

    @pytest.mark.asyncio
    async def test_missing_user_raises_401(self):
        token = _make_token()
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_token_user(token=token, db=db)

        assert exc_info.value.status_code == 401
        assert "Token owner not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_disabled_user_raises_403(self):
        uid = uuid.uuid4()
        token = _make_token(user_id=uid)
        user = _make_user(user_id=uid, user_status="DISABLED")

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_token_user(token=token, db=db)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_active_user_passes(self):
        uid = uuid.uuid4()
        token = _make_token(user_id=uid)
        user = _make_user(user_id=uid, user_status="ACTIVE")

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        result = await get_token_user(token=token, db=db)
        assert result.status == "ACTIVE"

    @pytest.mark.asyncio
    async def test_pending_user_passes(self):
        uid = uuid.uuid4()
        token = _make_token(user_id=uid)
        user = _make_user(user_id=uid, user_status="PENDING")

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = user

        result = await get_token_user(token=token, db=db)
        assert result.status == "PENDING"


# ---------------------------------------------------------------------------
# ScopeChecker
# ---------------------------------------------------------------------------


class TestScopeChecker:
    @pytest.mark.asyncio
    async def test_scope_present_passes(self):
        token = _make_token(scopes=["read:datasets", "read:rules"])
        checker = ScopeChecker("read:datasets")

        # Should not raise
        result = await checker(token=token)
        assert result is None

    @pytest.mark.asyncio
    async def test_scope_missing_raises_403(self):
        token = _make_token(scopes=["read:datasets"])
        checker = ScopeChecker("read:rules")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await checker(token=token)

        assert exc_info.value.status_code == 403
        assert "read:rules" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_empty_scopes_raises_403(self):
        token = _make_token(scopes=[])
        checker = ScopeChecker("read:datasets")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await checker(token=token)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_none_scopes_raises_403(self):
        token = _make_token(scopes=None)
        checker = ScopeChecker("read:datasets")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await checker(token=token)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_multiple_scopes_checked_individually(self):
        token = _make_token(scopes=["read:datasets", "read:rules", "read:issues"])

        for scope in ["read:datasets", "read:rules", "read:issues"]:
            checker = ScopeChecker(scope)
            result = await checker(token=token)
            assert result is None

    @pytest.mark.asyncio
    async def test_stores_required_scope(self):
        checker = ScopeChecker("read:executions")
        assert checker.required_scope == "read:executions"
