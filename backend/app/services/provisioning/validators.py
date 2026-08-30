"""
Tenant Provisioning — Input Validators
========================================

Reuses existing tenant validators where applicable and adds
provisioning-specific validators (admin email, admin name, workspace fields).
"""

from __future__ import annotations

import re

from app.api.v1.dependencies.tenant_auth import TenantAPIError

# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_admin_email(value: str | None) -> str:
    """Validate and normalise the admin email address."""
    if value is None or not isinstance(value, str) or not value.strip():
        raise TenantAPIError(
            422,
            "invalid_input",
            "Admin email is required.",
            fields=[{"field": "admin_email", "reason": "Required field"}],
        )
    email = value.strip().lower()
    if len(email) > 255:
        raise TenantAPIError(
            422,
            "invalid_input",
            "Admin email must be at most 255 characters.",
            fields=[{"field": "admin_email", "reason": "Must be at most 255 characters"}],
        )
    if not _EMAIL_RE.match(email):
        raise TenantAPIError(
            422,
            "invalid_input",
            "Admin email is not a valid email address.",
            fields=[{"field": "admin_email", "reason": "Invalid email format"}],
        )
    return email


# ---------------------------------------------------------------------------
# Admin full name validation
# ---------------------------------------------------------------------------


def validate_admin_full_name(value: str | None) -> str | None:
    """Validate and normalise the admin full name (optional)."""
    if value is None or not isinstance(value, str) or not value.strip():
        return None
    name = value.strip()
    if len(name) > 255:
        raise TenantAPIError(
            422,
            "invalid_input",
            "Admin name must be at most 255 characters.",
            fields=[{"field": "admin_full_name", "reason": "Must be at most 255 characters"}],
        )
    return name


# ---------------------------------------------------------------------------
# Workspace name / slug validation
# ---------------------------------------------------------------------------

_WORKSPACE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")


def validate_workspace_name(value: str | None, tenant_name: str) -> str:
    """Validate workspace name; defaults to 'Default Workspace' if omitted."""
    if value is None or not isinstance(value, str) or not value.strip():
        return "Default Workspace"
    name = value.strip()
    if len(name) < 1 or len(name) > 100:
        raise TenantAPIError(
            422,
            "invalid_input",
            "Workspace name must be between 1 and 100 characters.",
            fields=[{"field": "workspace_name", "reason": "Must be 1-100 characters"}],
        )
    return name


def validate_workspace_slug(value: str | None, tenant_slug: str) -> str:
    """Validate workspace slug; defaults to 'default' if omitted."""
    if value is None or not isinstance(value, str) or not value.strip():
        return "default"
    slug = value.strip().lower()
    if len(slug) < 1 or len(slug) > 50:
        raise TenantAPIError(
            422,
            "invalid_input",
            "Workspace slug must be between 1 and 50 characters.",
            fields=[{"field": "workspace_slug", "reason": "Must be 1-50 characters"}],
        )
    if not _WORKSPACE_SLUG_RE.match(slug):
        raise TenantAPIError(
            422,
            "invalid_input",
            "Workspace slug must contain only lowercase letters, digits, and hyphens.",
            fields=[
                {"field": "workspace_slug", "reason": "Must be lowercase alphanumeric with hyphens"}
            ],
        )
    return slug
