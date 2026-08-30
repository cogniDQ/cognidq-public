"""
Unit tests — F004 P02: Credential Service (Fernet encryption)

Tests encrypt/decrypt round-trip, key validation, and error sanitisation.

Test IDs: CRED-01 through CRED-07
"""

import json
import os

import pytest

# Set the env var BEFORE importing the service so the lazy init picks it up
TEST_KEY = (
    "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="  # gitleaks:allow - test-fixture Fernet key only
)
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = TEST_KEY


from app.services.data_sources.credential_service import (
    CredentialDecryptionError,
    CredentialKeyError,
    decrypt,
    encrypt,
    reset_fernet,
    sanitize_error_message,
)


@pytest.fixture(autouse=True)
def reset_key_cache():
    """Reset the cached Fernet instance before each test."""
    os.environ["CREDENTIAL_ENCRYPTION_KEY"] = TEST_KEY
    reset_fernet()
    yield
    os.environ["CREDENTIAL_ENCRYPTION_KEY"] = TEST_KEY
    reset_fernet()


# ─────────────────────────────────────────────────────────────────────────────
# CRED-01: encrypt returns bytes
# ─────────────────────────────────────────────────────────────────────────────


class TestEncrypt:
    """CRED-01"""

    def test_encrypt_returns_bytes(self):
        creds = {"host": "db.example.com", "port": 5432, "password": "s3cr3t"}
        result = encrypt(creds)
        assert isinstance(result, bytes)

    def test_two_encryptions_produce_different_ciphertext(self):
        """Fernet uses a random IV per encryption call."""
        creds = {"password": "abc"}
        assert encrypt(creds) != encrypt(creds)


# ─────────────────────────────────────────────────────────────────────────────
# CRED-02: Round-trip encrypt/decrypt
# ─────────────────────────────────────────────────────────────────────────────


class TestRoundTrip:
    """CRED-02"""

    def test_round_trip_postgresql_credentials(self):
        creds = {
            "host": "db.example.com",
            "port": 5432,
            "database": "prod",
            "username": "admin",
            "password": "my$ecretP@ssw0rd",
        }
        ciphertext = encrypt(creds)
        decrypted = decrypt(ciphertext)
        assert decrypted == creds

    def test_round_trip_bigquery_service_account(self):
        creds = {"service_account_json": '{"type": "service_account"}'}
        ciphertext = encrypt(creds)
        assert decrypt(ciphertext) == creds


# ─────────────────────────────────────────────────────────────────────────────
# CRED-03: decrypt with wrong key raises CredentialDecryptionError
# ─────────────────────────────────────────────────────────────────────────────


class TestDecryptWrongKey:
    """CRED-03"""

    def test_wrong_key_raises_decryption_error(self):
        creds = {"password": "secret"}
        ciphertext = encrypt(creds)

        # Switch to a different valid key
        from cryptography.fernet import Fernet

        wrong_key = Fernet.generate_key().decode()
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = wrong_key
        reset_fernet()

        with pytest.raises(CredentialDecryptionError):
            decrypt(ciphertext)


# ─────────────────────────────────────────────────────────────────────────────
# CRED-04: missing key raises CredentialKeyError
# ─────────────────────────────────────────────────────────────────────────────


class TestMissingKey:
    """CRED-04"""

    def test_missing_env_var_raises_key_error(self):
        del os.environ["CREDENTIAL_ENCRYPTION_KEY"]
        reset_fernet()
        with pytest.raises(CredentialKeyError):
            encrypt({"password": "x"})


# ─────────────────────────────────────────────────────────────────────────────
# CRED-05: invalid key raises CredentialKeyError
# ─────────────────────────────────────────────────────────────────────────────


class TestInvalidKey:
    """CRED-05"""

    def test_invalid_key_raises_key_error(self):
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = "not-a-valid-fernet-key"
        reset_fernet()
        with pytest.raises(CredentialKeyError):
            encrypt({"password": "x"})


# ─────────────────────────────────────────────────────────────────────────────
# CRED-06: sanitize_error_message redacts credential values
# ─────────────────────────────────────────────────────────────────────────────


class TestSanitizeErrorMessage:
    """CRED-06"""

    def test_password_redacted(self):
        msg = "Connection refused for user admin@db.example.com with password MyS3cr3t"
        result = sanitize_error_message(msg, ["MyS3cr3t"])
        assert "MyS3cr3t" not in result
        assert "[REDACTED]" in result

    def test_empty_value_not_redacted(self):
        msg = "some error"
        result = sanitize_error_message(msg, [""])
        assert result == msg

    def test_message_unchanged_if_no_match(self):
        msg = "generic error"
        result = sanitize_error_message(msg, ["not-in-message"])
        assert result == msg


# ─────────────────────────────────────────────────────────────────────────────
# CRED-07: decrypt rejects tampered ciphertext
# ─────────────────────────────────────────────────────────────────────────────


class TestTamperedCiphertext:
    """CRED-07"""

    def test_tampered_ciphertext_rejected(self):
        creds = {"secret": "value"}
        ciphertext = bytearray(encrypt(creds))
        # Flip a byte in the middle
        ciphertext[len(ciphertext) // 2] ^= 0xFF
        with pytest.raises(CredentialDecryptionError):
            decrypt(bytes(ciphertext))
