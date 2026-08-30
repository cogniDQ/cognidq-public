"""
F001 — Field-level validators for Tenant create/update operations
==================================================================

Every function either returns the normalised value or raises
``TenantAPIError`` with the correct HTTP status code and error code
as specified in TDD §6.1–6.8.

These are pure-Python functions; they take no DB dependency.

Normalisation rules (TDD §4.2 step 2)
--------------------------------------
* tenant_name         → TRIM(input)
* tenant_slug         → TRIM(LOWER(input))
* region              → TRIM(LOWER(input))
* plan                → TRIM(LOWER(input))
* initial_status      → TRIM(LOWER(input)) or default "draft"
* status_reason       → TRIM(input); empty string → treat as absent
* tenant_notes        → TRIM(input); whitespace-only → coerce to None
"""

from __future__ import annotations

import re
from datetime import date

from app.api.v1.dependencies.tenant_auth import TenantAPIError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_REGIONS: frozenset[str] = frozenset({"eu-west", "eu-central", "us-east", "us-west"})
VALID_PLANS: frozenset[str] = frozenset({"starter", "growth", "enterprise"})
# Only draft and active are permitted on CREATE; suspended/archived are PATCH-only
VALID_CREATE_STATUSES: frozenset[str] = frozenset({"draft", "active"})

# Forbidden chars in tenant_name: < > & " ' ` and ASCII control codes 0x00–0x1F, 0x7F
_FORBIDDEN_NAME_CHARS_RE = re.compile(r'[<>&"\'\`\x00-\x1F\x7F]')

# tenant_slug: only lowercase alphanum and hyphens
_SLUG_VALID_CHARS_RE = re.compile(r"^[a-z0-9-]+$")

# Dates
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ASCII control characters (for notes / status_reason)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_tenant_name(raw: str | None) -> str:
    """Return trimmed tenant_name or raise TenantAPIError (422 validation_error)."""
    value: str = (raw or "").strip()

    if not value:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_name is required.",
            [{"field": "tenant_name", "reason": "required"}],
        )
    if len(value) < 2:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_name must be at least 2 characters.",
            [{"field": "tenant_name", "reason": "min_length"}],
        )
    if len(value) > 150:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_name must not exceed 150 characters.",
            [{"field": "tenant_name", "reason": "max_length"}],
        )
    if _FORBIDDEN_NAME_CHARS_RE.search(value):
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_name contains invalid characters.",
            [{"field": "tenant_name", "reason": "invalid_characters"}],
        )
    return value


def validate_tenant_slug(raw: str | None) -> str:
    """Return normalised (trimmed + lowercased) tenant_slug or raise TenantAPIError."""
    value: str = (raw or "").strip().lower()

    if not value:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_slug is required.",
            [{"field": "tenant_slug", "reason": "required"}],
        )
    if len(value) < 3 or len(value) > 80:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_slug must be between 3 and 80 characters.",
            [{"field": "tenant_slug", "reason": "invalid_length"}],
        )
    if not _SLUG_VALID_CHARS_RE.match(value):
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_slug may only contain lowercase letters, digits, and hyphens.",
            [{"field": "tenant_slug", "reason": "invalid_characters"}],
        )
    if value.startswith("-") or value.endswith("-"):
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_slug must not start or end with a hyphen.",
            [{"field": "tenant_slug", "reason": "invalid_format"}],
        )
    if "--" in value:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_slug must not contain consecutive hyphens.",
            [{"field": "tenant_slug", "reason": "invalid_format"}],
        )
    return value


def validate_region(raw: str | None) -> str:
    """Return normalised region string or raise TenantAPIError (422 invalid_region)."""
    value: str = (raw or "").strip().lower()

    if not value:
        raise TenantAPIError(
            422,
            "validation_error",
            "region is required.",
            [{"field": "region", "reason": "required"}],
        )
    if value not in VALID_REGIONS:
        raise TenantAPIError(
            422,
            "invalid_region",
            f"region must be one of: {', '.join(sorted(VALID_REGIONS))}.",
        )
    return value


def validate_plan(raw: str | None) -> str:
    """Return normalised plan string or raise TenantAPIError (422 invalid_plan)."""
    value: str = (raw or "").strip().lower()

    if not value:
        raise TenantAPIError(
            422,
            "validation_error",
            "plan is required.",
            [{"field": "plan", "reason": "required"}],
        )
    if value not in VALID_PLANS:
        raise TenantAPIError(
            422,
            "invalid_plan",
            f"plan must be one of: {', '.join(sorted(VALID_PLANS))}.",
        )
    return value


def validate_initial_status(raw: str | None) -> str:
    """Return normalised initial_status or raise TenantAPIError (422 invalid_status).

    Omitted or empty → defaults to "draft".
    Only "draft" and "active" are valid on CREATE.
    """
    if raw is None:
        return "draft"
    value: str = raw.strip().lower()
    if not value:
        return "draft"
    if value not in VALID_CREATE_STATUSES:
        raise TenantAPIError(
            422,
            "invalid_status",
            f"initial_status must be 'draft' or 'active' on create. Got: '{value}'.",
        )
    return value


def validate_service_start_date(raw: str | None) -> date | None:
    """Parse an ISO 8601 date string (YYYY-MM-DD) or return None.

    Raises TenantAPIError (422 validation_error) for invalid formats.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if not _DATE_RE.match(stripped):
        raise TenantAPIError(
            422,
            "validation_error",
            "service_start_date must be a date in YYYY-MM-DD format.",
            [{"field": "service_start_date", "reason": "invalid_date"}],
        )
    try:
        return date.fromisoformat(stripped)
    except ValueError:
        raise TenantAPIError(
            422,
            "validation_error",
            "service_start_date is not a valid calendar date.",
            [{"field": "service_start_date", "reason": "invalid_date"}],
        )


def validate_tenant_notes(raw: str | None) -> str | None:
    """Return trimmed notes string, None if blank, or raise on violations.

    Whitespace-only input is coerced to None (TDD §4.2 normalisation).
    """
    if raw is None:
        return None
    value: str = raw.strip()
    if not value:
        return None  # whitespace-only → treated as absent
    if len(value) > 5000:
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_notes must not exceed 5000 characters.",
            [{"field": "tenant_notes", "reason": "max_length"}],
        )
    if _CONTROL_CHARS_RE.search(value):
        raise TenantAPIError(
            422,
            "validation_error",
            "tenant_notes contains invalid control characters.",
            [{"field": "tenant_notes", "reason": "invalid_characters"}],
        )
    return value


def validate_status_reason(raw: str | None) -> str | None:
    """Return trimmed status_reason or None.

    On CREATE with draft/active status, status_reason is optional.
    If provided, validate max 500 chars and no control chars.
    """
    if raw is None:
        return None
    value: str = raw.strip()
    if not value:
        return None
    if len(value) > 500:
        raise TenantAPIError(
            422,
            "validation_error",
            "status_reason must not exceed 500 characters.",
            [{"field": "status_reason", "reason": "max_length"}],
        )
    if _CONTROL_CHARS_RE.search(value):
        raise TenantAPIError(
            422,
            "validation_error",
            "status_reason contains invalid control characters.",
            [{"field": "status_reason", "reason": "invalid_characters"}],
        )
    return value
