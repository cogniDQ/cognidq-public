"""Password reset transactional email.

Sends a password-reset link using the tenant-scoped SMTP config (resolved via
``TenantSettingsService``). The email body is minimal and brand-neutral so it
works for any tenant out of the box. If no SMTP is configured this function
returns without raising so the request endpoint never leaks "user exists" via
a 500 error — the caller is expected to log the failure.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)


def _build_reset_url(token: str) -> str:
    base = os.getenv("APP_BASE_URL", "http://localhost:5173").rstrip("/")
    return f"{base}/auth/reset-password?token={token}"


def send_password_reset_email(
    db: Session,
    *,
    user: User,
    token: str,
) -> bool:
    """Send a password-reset email to ``user``. Returns True on success.

    Resolution order for SMTP credentials:
      1. Tenant settings (``control.tenant_settings``) when SMTP is enabled.
      2. Environment fallback (``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USERNAME``,
         ``SMTP_PASSWORD``, ``SMTP_FROM_ADDRESS``, ``SMTP_TLS``).
    """
    host: str | None = None
    port = 587
    username = ""
    password = ""
    use_tls = True
    from_addr: str | None = None

    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id is not None:
        try:
            from app.services.tenant.settings_service import TenantSettingsService

            cfg = TenantSettingsService().get_smtp_config_for_dispatch(db, tenant_id)
            if cfg is not None:
                host = cfg.host
                port = int(cfg.port or 587)
                username = cfg.username or ""
                password = cfg.password or ""
                use_tls = bool(cfg.use_tls)
                from_addr = cfg.from_address or username or None
        except Exception as exc:  # noqa: BLE001
            logger.debug("password_reset tenant SMTP lookup failed: %s", exc)

    if not host:
        host = os.getenv("SMTP_HOST")
        port = int(os.getenv("SMTP_PORT", "587"))
        username = os.getenv("SMTP_USERNAME", "")
        password = os.getenv("SMTP_PASSWORD", "")
        use_tls = os.getenv("SMTP_TLS", "true").lower() in ("1", "true", "yes")
        from_addr = os.getenv("SMTP_FROM_ADDRESS") or username or None

    if not host or not from_addr:
        logger.warning(
            "password_reset email skipped (no SMTP configured) user_id=%s token=%s",
            user.id,
            token,
        )
        return False

    reset_url = _build_reset_url(token)
    subject = "Reset your CogniDQ password"
    text_body = (
        f"Hi {user.full_name or user.email},\n\n"
        f"We received a request to reset your CogniDQ password.\n"
        f"Use the link below to choose a new password. This link expires shortly.\n\n"
        f"{reset_url}\n\n"
        f"If you did not request this change you can safely ignore this email — your "
        f"password will remain unchanged.\n\n"
        f"— The CogniDQ Team"
    )
    html_body = f"""
    <html><body style="font-family:Inter,Arial,sans-serif;color:#0F172A;line-height:1.5">
      <p>Hi {user.full_name or user.email},</p>
      <p>We received a request to reset your <strong>CogniDQ</strong> password.</p>
      <p>
        <a href="{reset_url}"
           style="display:inline-block;padding:10px 20px;background:#1E40AF;
                  color:#FFFFFF;text-decoration:none;border-radius:6px;font-weight:600">
          Reset password
        </a>
      </p>
      <p style="color:#475569;font-size:13px">
        Or copy this link into your browser:<br>
        <code style="font-size:12px">{reset_url}</code>
      </p>
      <p style="color:#475569;font-size:13px">
        If you did not request this change you can safely ignore this email.
      </p>
      <p style="color:#94A3B8;font-size:12px">— The CogniDQ Team</p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = user.email
    msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if use_tls:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls()
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, [user.email], msg.as_string())
        server.quit()
        logger.info("password_reset_email_sent user_id=%s", user.id)
        return True
    except smtplib.SMTPException as exc:
        logger.warning("password_reset_smtp_failed user_id=%s err=%s", user.id, exc)
        return False
