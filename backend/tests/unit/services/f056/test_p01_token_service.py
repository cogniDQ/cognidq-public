"""
F056 P01 — Token Service Tests (15 tests)
==========================================

Covers: AccessTokenService generate_token, create_token, verify_token,
        revoke_token, list_tokens, list_all_tokens, delete_token.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest
from app.services.auth.token_service import AccessTokenService


def _mock_db():
    db = MagicMock()
    return db


def _mock_token(**overrides):
    t = MagicMock()
    t.id = overrides.get("id", uuid4())
    t.user_id = overrides.get("user_id", uuid4())
    t.name = overrides.get("name", "test-token")
    t.token_hash = overrides.get("token_hash", "abc123hash")
    t.prefix = overrides.get("prefix", "dqai_abc1")
    t.scopes = overrides.get("scopes", [])
    t.expires_at = overrides.get("expires_at", None)
    t.last_used_at = overrides.get("last_used_at", None)
    t.created_at = overrides.get("created_at", datetime.now(UTC))
    t.revoked_at = overrides.get("revoked_at", None)
    t.is_valid = MagicMock(return_value=overrides.get("is_valid", True))
    return t


# ── generate_token tests ────────────────────────────────────────────────────


class TestGenerateToken:
    def test_returns_tuple_of_three(self):
        result = AccessTokenService.generate_token()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_full_token_has_prefix(self):
        full_token, _, _ = AccessTokenService.generate_token()
        assert full_token.startswith("dqai_")

    def test_hash_is_sha256_hex(self):
        full_token, token_hash, _ = AccessTokenService.generate_token()
        # Service hashes the raw part (without dqai_ prefix)
        raw = full_token[5:]  # strip "dqai_" prefix
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert token_hash == expected_hash

    def test_prefix_starts_with_dqai(self):
        _, _, prefix = AccessTokenService.generate_token()
        assert prefix.startswith("dqai_")

    def test_tokens_are_unique(self):
        t1 = AccessTokenService.generate_token()
        t2 = AccessTokenService.generate_token()
        assert t1[0] != t2[0]
        assert t1[1] != t2[1]


# ── create_token tests ──────────────────────────────────────────────────────


class TestCreateToken:
    def test_creates_and_returns_token(self):
        db = _mock_db()
        user_id = str(uuid4())
        token_model, plain_token = AccessTokenService.create_token(db, user_id, "my-token")
        db.add.assert_called_once()
        db.commit.assert_called_once()
        db.refresh.assert_called_once()
        assert plain_token.startswith("dqai_")

    def test_create_with_expiry(self):
        db = _mock_db()
        user_id = str(uuid4())
        token_model, _ = AccessTokenService.create_token(
            db, user_id, "expiring", expires_in_days=30
        )
        # The model passed to db.add should have expires_at set
        model_arg = db.add.call_args[0][0]
        assert model_arg.expires_at is not None

    def test_create_with_scopes(self):
        db = _mock_db()
        user_id = str(uuid4())
        token_model, _ = AccessTokenService.create_token(
            db, user_id, "scoped", scopes=["read", "write"]
        )
        model_arg = db.add.call_args[0][0]
        assert model_arg.scopes == ["read", "write"]

    def test_create_without_scopes_defaults_empty(self):
        db = _mock_db()
        user_id = str(uuid4())
        token_model, _ = AccessTokenService.create_token(db, user_id, "no-scopes")
        model_arg = db.add.call_args[0][0]
        assert model_arg.scopes == []


# ── verify_token tests ──────────────────────────────────────────────────────


class TestVerifyToken:
    def test_valid_token_returns_model(self):
        db = _mock_db()
        mock_token = _mock_token()
        db.query.return_value.filter.return_value.first.return_value = mock_token
        result = AccessTokenService.verify_token(db, "dqai_sometoken")
        assert result is not None

    def test_invalid_token_returns_none(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = AccessTokenService.verify_token(db, "dqai_badtoken")
        assert result is None

    def test_verify_updates_last_used(self):
        db = _mock_db()
        mock_token = _mock_token()
        db.query.return_value.filter.return_value.first.return_value = mock_token
        AccessTokenService.verify_token(db, "dqai_sometoken")
        assert mock_token.last_used_at is not None
        db.commit.assert_called()


# ── revoke_token tests ──────────────────────────────────────────────────────


class TestRevokeToken:
    def test_revoke_success(self):
        db = _mock_db()
        mock_token = _mock_token()
        db.query.return_value.filter.return_value.first.return_value = mock_token
        result = AccessTokenService.revoke_token(db, str(uuid4()), str(uuid4()))
        assert result is True
        assert mock_token.revoked_at is not None
        db.commit.assert_called()

    def test_revoke_not_found(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = AccessTokenService.revoke_token(db, str(uuid4()), str(uuid4()))
        assert result is False


# ── list_tokens / delete tests ───────────────────────────────────────────────


class TestListAndDelete:
    def test_list_tokens_returns_list(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            _mock_token(),
            _mock_token(),
        ]
        result = AccessTokenService.list_tokens(db, str(uuid4()))
        assert len(result) == 2

    def test_delete_success(self):
        db = _mock_db()
        mock_token = _mock_token()
        db.query.return_value.filter.return_value.first.return_value = mock_token
        result = AccessTokenService.delete_token(db, str(uuid4()), str(uuid4()))
        assert result is True
        db.delete.assert_called_once_with(mock_token)
        db.commit.assert_called()
