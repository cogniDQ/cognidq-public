"""
F004 — Credential Service
==========================

Handles Fernet-based encryption/decryption of data source credentials.
All cryptographic operations are centralised here so that the rest of the
service layer never handles plaintext credential dicts directly.

Key management
--------------
* Key is read from the ``CREDENTIAL_ENCRYPTION_KEY`` environment variable.
* Key must be a URL-safe base64-encoded 32-byte value (Fernet requirement).
* If the env var is absent or not a valid Fernet key the module raises
  ``CredentialKeyError`` at import time — this fails the container startup
  fast rather than silently encrypting with a broken key.

Security notes
--------------
* ``sanitize_error_message`` is applied to all exception messages before
  they are propagated — preventing credential values from leaking into
  logs or API responses.
* The module NEVER logs plaintext credentials.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class CredentialKeyError(RuntimeError):
    """Raised when CREDENTIAL_ENCRYPTION_KEY is missing or invalid."""


class CredentialEncryptionError(RuntimeError):
    """Raised when encryption fails."""


class CredentialDecryptionError(RuntimeError):
    """Raised when decryption fails (wrong key, tampered token)."""


# ─────────────────────────────────────────────────────────────────────────────
# Key initialisation
# ─────────────────────────────────────────────────────────────────────────────

_ENV_KEY_NAME = "CREDENTIAL_ENCRYPTION_KEY"


def _load_fernet() -> Fernet:
    raw = os.environ.get(_ENV_KEY_NAME)
    if not raw:
        raise CredentialKeyError(
            f"Environment variable {_ENV_KEY_NAME!r} is not set. "
            "Data source credential encryption is unavailable."
        )
    try:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    except Exception as exc:
        raise CredentialKeyError(f"{_ENV_KEY_NAME!r} is not a valid Fernet key: {exc}") from exc


# Module-level Fernet instance — initialised lazily on first use so that
# tests can set the env var before importing this module without issue.
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = _load_fernet()
    return _fernet


def reset_fernet() -> None:
    """Force re-initialisation of the Fernet key (for testing only)."""
    global _fernet
    _fernet = None


# ─────────────────────────────────────────────────────────────────────────────
# Sanitisation helper
# ─────────────────────────────────────────────────────────────────────────────


def sanitize_error_message(message: str, credential_fields: list[str]) -> str:
    """
    Replace occurrences of any credential field value with ``[REDACTED]``.
    Accepts a list of raw credential string values as ``credential_fields``.
    """
    safe = message
    for value in credential_fields:
        if value and isinstance(value, str) and len(value) > 1:
            safe = safe.replace(value, "[REDACTED]")
    return safe


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def encrypt(credentials: dict[str, Any]) -> bytes:
    """
    Serialize ``credentials`` to JSON and encrypt with Fernet.

    Returns the ciphertext as ``bytes`` suitable for storing in BYTEA.
    Raises ``CredentialEncryptionError`` on failure.
    """
    try:
        plaintext = json.dumps(credentials, separators=(",", ":")).encode("utf-8")
        return _get_fernet().encrypt(plaintext)
    except CredentialKeyError:
        raise
    except Exception as exc:
        raise CredentialEncryptionError(
            f"Failed to encrypt credentials: {type(exc).__name__}"
        ) from exc


def decrypt(ciphertext: bytes) -> dict[str, Any]:
    """
    Decrypt ``ciphertext`` and deserialise the JSON credential dict.

    Raises ``CredentialDecryptionError`` if the token is invalid, expired,
    or was encrypted with a different key.
    """
    try:
        plaintext = _get_fernet().decrypt(ciphertext)
        return json.loads(plaintext.decode("utf-8"))
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "Credential decryption failed: token is invalid or key mismatch."
        ) from exc
    except CredentialKeyError:
        raise
    except Exception as exc:
        raise CredentialDecryptionError(
            f"Credential decryption failed: {type(exc).__name__}"
        ) from exc


def encrypt_string(value: str) -> str:
    """Encrypt a single string value and return a URL-safe base64 token string.

    Suitable for storing individual secrets (e.g. API keys) inside JSONB columns.
    """
    try:
        token = _get_fernet().encrypt(value.encode("utf-8"))
        return token.decode("utf-8")
    except CredentialKeyError:
        raise
    except Exception as exc:
        raise CredentialEncryptionError(f"Failed to encrypt string: {type(exc).__name__}") from exc


def decrypt_string(token: str) -> str:
    """Decrypt a Fernet token string back to the original plaintext string."""
    try:
        plaintext = _get_fernet().decrypt(token.encode("utf-8"))
        return plaintext.decode("utf-8")
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "String decryption failed: token is invalid or key mismatch."
        ) from exc
    except CredentialKeyError:
        raise
    except Exception as exc:
        raise CredentialDecryptionError(f"String decryption failed: {type(exc).__name__}") from exc
