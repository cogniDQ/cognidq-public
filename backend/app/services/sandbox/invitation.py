"""
F134 P07 — Invitation Token Signing

HMAC-SHA256 signed token for sandbox invitation emails.
Token payload: {user_id, email, expires_at (ISO-8601)}
Format: base64url(payload_json) + "." + base64url(hmac_sig)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# 7-day expiry for invitation tokens
INVITATION_TOKEN_TTL_DAYS = 7


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s.encode())


def generate_invitation_token(
    *,
    user_id: str,
    email: str,
    secret: str,
    now: datetime | None = None,
    ttl_days: int = INVITATION_TOKEN_TTL_DAYS,
) -> str:
    """
    Generate a signed invitation token.

    Returns an opaque string of the form ``payload.signature``.

    SECURITY: secret must not be logged or exposed in error messages.
    """
    if now is None:
        now = datetime.now(UTC)
    expires_at = now + timedelta(days=ttl_days)
    payload = {
        "user_id": user_id,
        "email": email,
        "expires_at": expires_at.isoformat(),
        "purpose": "sandbox_invitation",
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    payload_b64 = _b64url_encode(payload_bytes)
    sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{payload_b64}.{sig_b64}"


def verify_invitation_token(
    token: str,
    *,
    secret: str,
    now: datetime | None = None,
) -> dict | None:
    """
    Verify a signed invitation token.

    Returns the decoded payload dict on success, or ``None`` if the token is
    invalid, tampered with, or expired.

    SECURITY: constant-time comparison used; secret not logged.
    """
    try:
        payload_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None

    expected_sig = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    expected_b64 = _b64url_encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_b64):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return None

    if payload.get("purpose") != "sandbox_invitation":
        return None

    if now is None:
        now = datetime.now(UTC)
    expires_at_str = payload.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
    except ValueError:
        return None

    if now > expires_at:
        return None

    return payload
