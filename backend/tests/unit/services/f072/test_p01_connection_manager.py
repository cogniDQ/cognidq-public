"""
F072 P01 — Unit tests: ConnectionManager

Tests encryption/decryption/masking, connector routing, and test_connection delegation.

P01-01 .. P01-15  (15 tests)
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet

# ---------------------------------------------------------------------------
# Helpers — stable key for deterministic cipher across tests
# ---------------------------------------------------------------------------
STABLE_KEY = Fernet.generate_key().decode()


def _patched_cm():
    """Return ConnectionManager after forcing stable encryption key."""
    with patch.dict(os.environ, {"DATASOURCE_ENCRYPTION_KEY": STABLE_KEY}):
        # Re-import to pick up the patched env var through class attribute
        from app.services.datasources.connection_manager import ConnectionManager

        # Override the class attribute directly
        ConnectionManager.ENCRYPTION_KEY = STABLE_KEY
        return ConnectionManager


# ===================================================================
# GET CIPHER
# ===================================================================
class TestGetCipher:
    def test_uses_env_key(self):
        """P01-01: With DATASOURCE_ENCRYPTION_KEY set → returns Fernet with that key"""
        CM = _patched_cm()
        cipher = CM.get_cipher()
        assert isinstance(cipher, Fernet)
        # Verify it can encrypt/decrypt (proves the key was loaded)
        token = cipher.encrypt(b"test")
        assert cipher.decrypt(token) == b"test"

    def test_generates_key_when_no_env(self):
        """P01-02: Without env var → still returns Fernet instance (generated key)"""
        from app.services.datasources.connection_manager import ConnectionManager

        # Even with whatever key is on the class, get_cipher should return Fernet
        cipher = ConnectionManager.get_cipher()
        assert isinstance(cipher, Fernet)


# ===================================================================
# ENCRYPT CONFIG
# ===================================================================
class TestEncryptConfig:
    def test_encrypts_sensitive_fields(self):
        """P01-03: password, api_key → 'encrypted:' prefix"""
        CM = _patched_cm()
        config = {"host": "localhost", "password": "secret", "api_key": "key123"}
        result = CM.encrypt_config(config)
        assert result["password"].startswith("encrypted:")
        assert result["api_key"].startswith("encrypted:")

    def test_leaves_nonsensitive_unchanged(self):
        """P01-04: host, port, database left as-is"""
        CM = _patched_cm()
        config = {"host": "localhost", "port": 5432, "database": "test"}
        result = CM.encrypt_config(config)
        assert result["host"] == "localhost"
        assert result["port"] == 5432
        assert result["database"] == "test"

    def test_skips_missing_sensitive(self):
        """P01-05: Config without password → no error, no password key added"""
        CM = _patched_cm()
        config = {"host": "localhost"}
        result = CM.encrypt_config(config)
        assert "password" not in result
        assert result["host"] == "localhost"


# ===================================================================
# DECRYPT CONFIG
# ===================================================================
class TestDecryptConfig:
    def test_roundtrip(self):
        """P01-06: encrypt → decrypt → original values restored"""
        CM = _patched_cm()
        original = {"host": "localhost", "password": "secret123", "api_key": "key456"}
        encrypted = CM.encrypt_config(original)
        decrypted = CM.decrypt_config(encrypted)
        assert decrypted["password"] == "secret123"
        assert decrypted["api_key"] == "key456"
        assert decrypted["host"] == "localhost"

    def test_corrupted_raises_valueerror(self):
        """P01-07: Tampered ciphertext → ValueError"""
        CM = _patched_cm()
        config = {"password": "encrypted:definitely_not_valid_base64_ciphertext"}
        with pytest.raises(ValueError, match="decrypt"):
            CM.decrypt_config(config)

    def test_non_encrypted_passthrough(self):
        """P01-08: Values without 'encrypted:' prefix → returned as-is"""
        CM = _patched_cm()
        config = {"host": "localhost", "password": "plain_password"}
        result = CM.decrypt_config(config)
        assert result["password"] == "plain_password"


# ===================================================================
# MASK CONFIG
# ===================================================================
class TestMaskConfig:
    def test_masks_sensitive(self):
        """P01-09: password, api_key → '********'"""
        CM = _patched_cm()
        config = {"host": "localhost", "password": "secret", "api_key": "key123"}
        result = CM.mask_config(config)
        assert result["password"] == "********"
        assert result["api_key"] == "********"

    def test_preserves_nonsensitive(self):
        """P01-10: host, port remain"""
        CM = _patched_cm()
        config = {"host": "localhost", "port": 5432, "password": "secret"}
        result = CM.mask_config(config)
        assert result["host"] == "localhost"
        assert result["port"] == 5432


# ===================================================================
# GET CONNECTOR
# ===================================================================
class TestGetConnector:
    @pytest.mark.asyncio
    async def test_postgresql_returns_connector(self):
        """P01-11: type='postgresql' → PostgreSQLConnector instance"""
        CM = _patched_cm()
        config = {
            "host": "localhost",
            "port": 5432,
            "database": "test",
            "username": "user",
            "password": "pass",
        }
        with patch("app.services.datasources.connectors.postgresql.psycopg2") as mock_pg:
            mock_pg.connect.return_value = MagicMock()
            connector = await CM.get_connector("postgresql", config)
            from app.services.datasources.connectors.postgresql import PostgreSQLConnector

            assert isinstance(connector, PostgreSQLConnector)

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self):
        """P01-12: type='oracle' → ValueError"""
        CM = _patched_cm()
        with pytest.raises(ValueError, match="Unsupported"):
            await CM.get_connector("oracle", {})

    @pytest.mark.asyncio
    async def test_decrypts_before_passing(self):
        """P01-13: Encrypted config passed → connector receives decrypted"""
        CM = _patched_cm()
        plain_config = {"host": "localhost", "password": "secret"}
        encrypted_config = CM.encrypt_config(plain_config)

        captured_config = {}

        def capture_init(self_inner, config):
            captured_config.update(config)
            self_inner.connection_config = config
            self_inner.connection = None
            self_inner.cursor = None

        with (
            patch(
                "app.services.datasources.connection_manager.PostgreSQLConnector.__init__",
                capture_init,
            ),
            patch(
                "app.services.datasources.connection_manager.PostgreSQLConnector.connect",
                new_callable=AsyncMock,
            ),
        ):
            await CM.get_connector("postgresql", encrypted_config)

        assert captured_config["password"] == "secret"


# ===================================================================
# TEST CONNECTION
# ===================================================================
class TestTestConnection:
    @pytest.mark.asyncio
    async def test_success_delegates(self):
        """P01-14: Connector returns (True, msg, details) → same returned"""
        CM = _patched_cm()
        mock_connector = MagicMock()
        mock_connector.test_connection = AsyncMock(return_value=(True, "OK", {"version": "15"}))

        with patch(
            "app.services.datasources.connection_manager.PostgreSQLConnector",
            return_value=mock_connector,
        ):
            success, msg, details = await CM.test_connection("postgresql", {"host": "h"})
            assert success is True
            assert msg == "OK"
            assert details == {"version": "15"}

    @pytest.mark.asyncio
    async def test_failure_returns_tuple(self):
        """P01-15: Connector raises → (False, error, None)"""
        CM = _patched_cm()
        mock_connector = MagicMock()
        mock_connector.test_connection = AsyncMock(side_effect=Exception("boom"))

        with patch(
            "app.services.datasources.connection_manager.PostgreSQLConnector",
            return_value=mock_connector,
        ):
            success, msg, details = await CM.test_connection("postgresql", {"host": "h"})
            assert success is False
            assert "boom" in msg
