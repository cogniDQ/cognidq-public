"""
Tenant Settings Service

Handles read/update of tenant-scoped configuration. Currently exposes the
SMTP block (host/port/credentials) used by the notification dispatcher when
an AlertChannel does not embed its own SMTP config.

External-service credentials must be configured by the tenant admin rather
than baked into env vars (see project mandate). Secrets are encrypted at
rest using the project's Fernet key (CREDENTIAL_ENCRYPTION_KEY) and decrypted
on demand by trusted backend services.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from app.models.tenant_settings import TenantSettings
from app.services.data_sources.credential_service import (
    CredentialEncryptionError,
    _get_fernet,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DTOs
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SMTPConfig:
    """Decrypted SMTP configuration ready for use by the dispatcher."""

    enabled: bool
    host: str | None
    port: int | None
    username: str | None
    password: str | None  # plaintext, only constructed in-memory
    use_tls: bool
    from_address: str | None


@dataclass
class SMTPSettingsResponse:
    """Public-facing SMTP settings (password redacted)."""

    enabled: bool
    host: str | None
    port: int | None
    username: str | None
    has_password: bool
    use_tls: bool
    from_address: str | None
    last_tested_at: datetime | None
    last_test_ok: bool | None
    last_test_error: str | None


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _encrypt_secret(plaintext: str) -> bytes:
    """Encrypt a single string secret with the project Fernet key."""
    try:
        return _get_fernet().encrypt(plaintext.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CredentialEncryptionError(
            f"Failed to encrypt SMTP password: {type(exc).__name__}"
        ) from exc


def _decrypt_secret(ciphertext: bytes) -> str | None:
    """Decrypt a single string secret. Returns None if decryption fails."""
    if not ciphertext:
        return None
    try:
        return _get_fernet().decrypt(bytes(ciphertext)).decode("utf-8")
    except (InvalidToken, Exception) as exc:  # noqa: BLE001
        logger.warning("tenant SMTP password decrypt failed: %s", type(exc).__name__)
        return None


def _ensure_row(db: Session, tenant_id: UUID) -> TenantSettings:
    row = db.query(TenantSettings).filter(TenantSettings.tenant_id == tenant_id).first()
    if row is None:
        row = TenantSettings(tenant_id=tenant_id)
        db.add(row)
        db.flush()
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class TenantSettingsService:
    """Read/update tenant-scoped settings (currently SMTP)."""

    # ----- SMTP read -----

    def get_smtp_settings(self, db: Session, tenant_id: UUID) -> SMTPSettingsResponse:
        row = _ensure_row(db, tenant_id)
        return SMTPSettingsResponse(
            enabled=bool(row.smtp_enabled),
            host=row.smtp_host,
            port=row.smtp_port,
            username=row.smtp_username,
            has_password=row.smtp_password_enc is not None,
            use_tls=bool(row.smtp_use_tls),
            from_address=row.smtp_from_address,
            last_tested_at=row.smtp_last_tested_at,
            last_test_ok=row.smtp_last_test_ok,
            last_test_error=row.smtp_last_test_error,
        )

    def get_smtp_config_for_dispatch(self, db: Session, tenant_id: UUID) -> SMTPConfig | None:
        """Return decrypted SMTPConfig for the dispatcher.

        Returns None if SMTP is not enabled or required fields are missing.
        Secrets are returned in plaintext for in-memory use only.
        """
        row = db.query(TenantSettings).filter(TenantSettings.tenant_id == tenant_id).first()
        if row is None or not row.smtp_enabled or not row.smtp_host:
            return None
        password = _decrypt_secret(row.smtp_password_enc) if row.smtp_password_enc else None
        return SMTPConfig(
            enabled=True,
            host=row.smtp_host,
            port=row.smtp_port or 587,
            username=row.smtp_username,
            password=password,
            use_tls=bool(row.smtp_use_tls),
            from_address=row.smtp_from_address or row.smtp_username,
        )

    # ----- SMTP update -----

    def update_smtp_settings(
        self,
        db: Session,
        tenant_id: UUID,
        *,
        enabled: bool | None = None,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        clear_password: bool = False,
        use_tls: bool | None = None,
        from_address: str | None = None,
        updated_by: UUID | None = None,
    ) -> SMTPSettingsResponse:
        row = _ensure_row(db, tenant_id)

        if enabled is not None:
            row.smtp_enabled = bool(enabled)
        if host is not None:
            row.smtp_host = (host.strip() or None) if isinstance(host, str) else None
        if port is not None:
            if not (1 <= int(port) <= 65535):
                raise ValueError("smtp_port must be between 1 and 65535")
            row.smtp_port = int(port)
        if username is not None:
            row.smtp_username = (username.strip() or None) if isinstance(username, str) else None
        if clear_password:
            row.smtp_password_enc = None
        elif password is not None and password != "":
            row.smtp_password_enc = _encrypt_secret(password)
        if use_tls is not None:
            row.smtp_use_tls = bool(use_tls)
        if from_address is not None:
            row.smtp_from_address = (
                (from_address.strip() or None) if isinstance(from_address, str) else None
            )
        if updated_by is not None:
            row.updated_by = updated_by

        # Validation: if enabled, host must be set
        if row.smtp_enabled and not row.smtp_host:
            raise ValueError("smtp_host is required when smtp_enabled is true")

        db.commit()
        db.refresh(row)
        return self.get_smtp_settings(db, tenant_id)

    # ----- SMTP test -----

    def test_smtp(self, db: Session, tenant_id: UUID, *, recipient: str | None = None) -> dict:
        """Attempt an SMTP login (and optional test send) using stored config."""
        cfg = self.get_smtp_config_for_dispatch(db, tenant_id)
        if cfg is None:
            return {"success": False, "error": "SMTP not configured or not enabled"}

        ok = False
        error: str | None = None
        try:
            server = smtplib.SMTP(cfg.host, cfg.port or 587, timeout=15)
            try:
                server.ehlo()
                if cfg.use_tls:
                    server.starttls()
                    server.ehlo()
                if cfg.username and cfg.password:
                    server.login(cfg.username, cfg.password)
                if recipient:
                    from email.mime.text import MIMEText

                    msg = MIMEText("DQ Hub SMTP test message")
                    msg["From"] = cfg.from_address or cfg.username or "noreply@example.com"
                    msg["To"] = recipient
                    msg["Subject"] = "DQ Hub SMTP test"
                    server.sendmail(msg["From"], [recipient], msg.as_string())
                ok = True
            finally:
                try:
                    server.quit()
                except Exception:
                    pass
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"

        # Persist test result
        try:
            row = _ensure_row(db, tenant_id)
            row.smtp_last_tested_at = datetime.now(UTC)
            row.smtp_last_test_ok = ok
            row.smtp_last_test_error = error[:2000] if error else None
            db.commit()
        except Exception:
            db.rollback()

        return {"success": ok, "error": error}
