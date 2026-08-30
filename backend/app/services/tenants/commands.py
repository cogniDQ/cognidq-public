"""
F001 — Tenant lifecycle transfer objects
=========================================

Contains:
    CreateTenantRequest  — Pydantic model for the POST /api/v1/tenants request body.
                           All fields are Optional[str] so that Pydantic performs
                           only JSON-parsing; all semantic validation happens in
                           the service layer via validators.py.

    CreateTenantCommand  — Immutable internal command produced after normalisation
                           and validation; carries the actor context too.

    TenantDTO            — Immutable data record returned from the service layer,
                           serialised into the HTTP 201 response.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# HTTP request body — Create Tenant  (Packet 3)
# ---------------------------------------------------------------------------


class CreateTenantRequest(BaseModel):
    """Loose request body model — only JSON parsing, no field-level validation."""

    model_config = ConfigDict(extra="ignore")  # silently discard unknown fields (POST)

    tenant_name: str | None = None
    tenant_slug: str | None = None
    region: str | None = None
    plan: str | None = None
    initial_status: str | None = None
    service_start_date: str | None = None  # kept as string; validated manually
    tenant_notes: str | None = None
    status_reason: str | None = None


# ---------------------------------------------------------------------------
# Internal command DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateTenantCommand:
    """Validated + normalised parameters ready for the repository layer."""

    tenant_name: str
    tenant_slug: str
    region: str
    plan: str
    initial_status: str
    status_reason: str | None
    service_start_date: date | None
    tenant_notes: str | None
    actor_id: UUID
    actor_role: str


# ---------------------------------------------------------------------------
# Response DTO
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenantDTO:
    """Full tenant record returned after a successful create."""

    tenant_id: str  # UUID as string
    tenant_name: str
    tenant_slug: str
    status: str
    status_reason: str | None
    region: str
    plan: str
    service_start_date: date | None
    tenant_notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str  # UUID as string
    updated_by: str  # UUID as string


# ---------------------------------------------------------------------------
# HTTP request body — Patch Tenant  (Packet 6)
# ---------------------------------------------------------------------------


class PatchTenantRequest(BaseModel):
    """Request body for PATCH /api/v1/tenants/{tenant_id}.

    ``extra="allow"`` captures keys that are not model fields (e.g.,
    ``tenant_slug``, ``region``, ``tenant_id``, ``status``) in
    ``model_extra`` so the endpoint can detect and reject them explicitly.

    ``model_fields_set`` identifies which of the 5 mutable fields were
    explicitly included in the body (distinguishing absent from null).
    """

    model_config = ConfigDict(extra="allow")

    tenant_name: str | None = None
    plan: str | None = None
    status_reason: str | None = None
    service_start_date: str | None = None
    tenant_notes: str | None = None


# ---------------------------------------------------------------------------
# Internal command DTO — Update Tenant  (Packet 6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpdateTenantCommand:
    """Validated + normalised PATCH parameters ready for the service layer.

    ``fields`` contains only the keys that were explicitly present in the
    request body and passed format validation.  Presence of a key means
    “this field should be updated”; the value may be ``None`` (clear the
    field) or a typed value.  Keys absent from ``fields`` are never touched.
    """

    tenant_id: str  # UUID string — already validated by the endpoint
    actor_id: UUID
    actor_role: str
    fields: dict[str, Any]  # e.g. {"tenant_name": "New Corp", "status_reason": None}


@dataclass(frozen=True)
class TenantDetailDTO:
    """Full tenant detail record returned by GET /api/v1/tenants/{tenant_id}.

    Contains all 13 DB columns plus four registry-sourced fields and the
    statically-computed ``audit_summary_link`` (TDD §3.4).
    """

    tenant_id: str  # UUID as string
    tenant_name: str
    tenant_slug: str
    status: str
    status_reason: str | None
    region: str
    plan: str
    service_start_date: date | None
    tenant_notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by: str  # UUID as string
    updated_by: str  # UUID as string
    workspace_count: int
    workspace_count_available: bool
    user_count: int
    user_count_available: bool
    audit_summary_link: str


# ---------------------------------------------------------------------------
# HTTP request body — Change Tenant Status  (Packet 7)
# ---------------------------------------------------------------------------


class ChangeStatusRequest(BaseModel):
    """Request body for POST /api/v1/tenants/{tenant_id}/status.

    Both fields are Optional so that Pydantic only parses JSON without
    raising its own validation errors; all semantic checks happen in the
    service layer.
    """

    model_config = ConfigDict(extra="ignore")

    target_status: str | None = None
    status_reason: str | None = None


# ---------------------------------------------------------------------------
# Internal command DTO — Change Tenant Status  (Packet 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangeStatusCommand:
    """Validated + normalised parameters for the change-status flow.

    ``target_status`` is already TRIM-LOWER normalised and validated as a
    known enum value.  ``status_reason`` has been trimmed; None means absent.
    """

    tenant_id: str  # UUID string — already validated by the endpoint
    actor_id: UUID
    actor_role: str
    target_status: str  # validated enum value
    status_reason: str | None


# ---------------------------------------------------------------------------
# Response DTO — Change Tenant Status  (Packet 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChangeStatusDTO:
    """Status-change summary returned by POST /api/v1/tenants/{tenant_id}/status.

    TDD §3.6 mandates exactly 6 fields.
    """

    tenant_id: str
    previous_status: str
    current_status: str
    status_reason: str | None
    updated_at: datetime
    updated_by: str  # UUID as string


# ---------------------------------------------------------------------------
# Query object — List Audit Logs  (Packet 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ListAuditLogsQuery:
    """Validated + normalised query parameters for GET /audit-logs.

    All optional filter fields are ``None`` when not supplied.
    ``from_dt`` / ``to_dt`` are timezone-aware UTC datetimes.
    """

    tenant_id: str  # UUID string — already validated by the endpoint
    event_type: str | None  # None or one of the three valid values
    actor_id: str | None  # None or validated UUID string
    from_dt: datetime | None  # None or timezone-aware UTC datetime
    to_dt: datetime | None  # None or timezone-aware UTC datetime
    page: int  # ≥ 1
    page_size: int  # 1–100


# ---------------------------------------------------------------------------
# Response DTO — Single Audit Log Entry  (Packet 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditLogDTO:
    """Single audit log record returned by GET /api/v1/tenants/{id}/audit-logs.

    Maps directly to the 9 columns of ``control.tenant_audit_logs`` (TDD §2.4).
    """

    log_id: str  # UUID as string
    tenant_id: str  # UUID as string
    event_type: str
    actor_id: str  # UUID as string
    actor_role: str
    previous_data: dict[str, Any] | None
    new_data: dict[str, Any]
    occurred_at: datetime
    reason: str | None
