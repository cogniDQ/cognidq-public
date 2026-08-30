"""
Tenant Provisioning — Transfer Objects
========================================

Contains:
    ProvisionTenantRequest  — Pydantic model for POST /api/v1/tenants/provision
    ProvisionTenantCommand  — Immutable internal command after validation
    ProvisionTenantResult   — Full result returned after provisioning
    ProvisioningStepLog     — Individual step tracking record
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# HTTP request body
# ---------------------------------------------------------------------------


class ProvisionTenantRequest(BaseModel):
    """Request body for POST /api/v1/tenants/provision.

    All fields are Optional[str] so Pydantic performs only JSON-parsing;
    all semantic validation happens in the endpoint layer via validators.
    """

    model_config = ConfigDict(extra="ignore")

    # Tenant fields
    tenant_name: str | None = None
    tenant_slug: str | None = None
    region: str | None = None
    plan: str | None = None
    service_start_date: str | None = None
    tenant_notes: str | None = None

    # Admin account fields
    admin_email: str | None = None
    admin_full_name: str | None = None

    # Workspace fields (optional — defaults generated if omitted)
    workspace_name: str | None = None
    workspace_slug: str | None = None


class ProvisionExistingTenantRequest(BaseModel):
    """Request body for ``POST /api/v1/tenants/{tenant_id}/provision``.

    Used to provision the default workspace + admin account against an
    *existing* tenant (created via the Create Tenant flow). Tenant
    metadata is read from the existing row and is therefore not
    accepted here.
    """

    model_config = ConfigDict(extra="ignore")

    admin_email: str | None = None
    admin_full_name: str | None = None
    workspace_name: str | None = None
    workspace_slug: str | None = None


# ---------------------------------------------------------------------------
# Internal validated command
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvisionTenantCommand:
    """Validated + normalised parameters ready for the provisioning service."""

    # Tenant
    tenant_name: str
    tenant_slug: str
    region: str
    plan: str
    service_start_date: date | None
    tenant_notes: str | None

    # Admin account
    admin_email: str
    admin_full_name: str | None

    # Workspace
    workspace_name: str
    workspace_slug: str

    # Actor context
    actor_id: UUID
    actor_role: str


@dataclass(frozen=True)
class ProvisionExistingTenantCommand:
    """Validated parameters for provisioning an existing tenant."""

    tenant_id: UUID

    admin_email: str
    admin_full_name: str | None

    workspace_name: str
    workspace_slug: str

    actor_id: UUID
    actor_role: str


# ---------------------------------------------------------------------------
# Step tracking
# ---------------------------------------------------------------------------


@dataclass
class ProvisioningStepLog:
    """Tracks one step of the provisioning flow."""

    step_name: str
    step_order: int
    status: str = "pending"  # pending, success, failed, rolled_back
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    step_data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Result DTO
# ---------------------------------------------------------------------------


@dataclass
class ProvisionTenantResult:
    """Full result of a successful provisioning operation."""

    tenant_id: str
    tenant_name: str
    tenant_slug: str
    status: str
    region: str
    plan: str

    workspace_id: str
    workspace_name: str
    workspace_slug: str

    admin_user_id: str
    admin_email: str
    admin_full_name: str | None

    provisioning_status: str  # completed, failed, partially_failed
    steps: list[ProvisioningStepLog] = field(default_factory=list)

    created_at: datetime | None = None
    password_reset_token: str | None = None  # only returned once, for invitation
