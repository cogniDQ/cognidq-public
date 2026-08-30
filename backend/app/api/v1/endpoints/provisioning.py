"""
Tenant Provisioning — API Endpoints
=====================================

Implements:
    POST  /api/v1/tenants/provision                     — Provision Tenant
    GET   /api/v1/tenants/{tenant_id}/provisioning-logs  — Provisioning Status

Auth guards:
    POST — Bearer JWT required; actor_role must be platform_admin
    GET  — Bearer JWT required; actor_role must be platform_admin or platform_viewer

Errors returned as ``{"error": {"code", "message", "fields"}}``
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    require_read_access,
    require_write_access,
    validate_uuid_path_param,
)
from app.models.database import get_db
from app.services.provisioning import (
    ProvisionExistingTenantCommand,
    ProvisionExistingTenantRequest,
    ProvisionTenantCommand,
    ProvisionTenantRequest,
    ProvisionTenantResult,
)
from app.services.provisioning.service import ProvisioningService
from app.services.provisioning.validators import (
    validate_admin_email,
    validate_admin_full_name,
    validate_workspace_name,
    validate_workspace_slug,
)
from app.services.tenants.validators import (
    validate_plan,
    validate_region,
    validate_service_start_date,
    validate_tenant_name,
    validate_tenant_notes,
    validate_tenant_slug,
)

router = APIRouter(prefix="/tenants", tags=["provisioning"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_dt(dt: Any) -> str | None:
    """Format a datetime as an ISO 8601 UTC string, handling naive datetimes."""
    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# POST /api/v1/tenants/provision — Provision Tenant
# ---------------------------------------------------------------------------


@router.post("/provision", status_code=201)
def provision_tenant(
    body: ProvisionTenantRequest,
    actor: ActorContext = Depends(require_write_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Provision a new tenant with default workspace and admin account.

    This is the main provisioning endpoint. It:
    1. Creates the tenant (status=active)
    2. Creates a default workspace
    3. Creates a tenant admin user
    4. Creates a password-reset invitation token
    5. Grants workspace_administrator role

    Returns HTTP 201 with full provisioning result including the invitation
    token (returned only once — must be captured by the caller).
    """
    # ------------------------------------------------------------------
    # Input validation — reuse existing tenant validators + new ones
    # ------------------------------------------------------------------
    tenant_name = validate_tenant_name(body.tenant_name)
    tenant_slug = validate_tenant_slug(body.tenant_slug)
    region = validate_region(body.region)
    plan = validate_plan(body.plan)
    service_start_date = validate_service_start_date(body.service_start_date)
    tenant_notes = validate_tenant_notes(body.tenant_notes)

    admin_email = validate_admin_email(body.admin_email)
    admin_full_name = validate_admin_full_name(body.admin_full_name)

    workspace_name = validate_workspace_name(body.workspace_name, tenant_name)
    workspace_slug = validate_workspace_slug(body.workspace_slug, tenant_slug)

    command = ProvisionTenantCommand(
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        region=region,
        plan=plan,
        service_start_date=service_start_date,
        tenant_notes=tenant_notes,
        admin_email=admin_email,
        admin_full_name=admin_full_name,
        workspace_name=workspace_name,
        workspace_slug=workspace_slug,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
    )

    result: ProvisionTenantResult = ProvisioningService.provision_tenant(db, command)

    # Build response — password_reset_token is returned ONCE
    return JSONResponse(
        status_code=201,
        content={
            "data": {
                "tenant": {
                    "tenant_id": result.tenant_id,
                    "tenant_name": result.tenant_name,
                    "tenant_slug": result.tenant_slug,
                    "status": result.status,
                    "region": result.region,
                    "plan": result.plan,
                    "provisioning_status": result.provisioning_status,
                    "created_at": _format_dt(result.created_at),
                },
                "workspace": {
                    "workspace_id": result.workspace_id,
                    "workspace_name": result.workspace_name,
                    "workspace_slug": result.workspace_slug,
                },
                "admin": {
                    "user_id": result.admin_user_id,
                    "email": result.admin_email,
                    "full_name": result.admin_full_name,
                    "status": "pending",
                },
                "invitation": {
                    "password_reset_token": result.password_reset_token,
                    "activation_url": f"/auth/set-password?token={result.password_reset_token}",
                    "expires_in_hours": 72,
                },
                "provisioning_steps": [
                    {
                        "step_name": s.step_name,
                        "step_order": s.step_order,
                        "status": s.status,
                    }
                    for s in result.steps
                ],
            },
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/tenants/{tenant_id}/provisioning-logs
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# POST /api/v1/tenants/{tenant_id}/provision — Provision *existing* tenant
# ---------------------------------------------------------------------------


@router.post("/{tenant_id}/provision", status_code=201)
def provision_existing_tenant(
    tenant_id: str,
    body: ProvisionExistingTenantRequest,
    actor: ActorContext = Depends(require_write_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Provision the default workspace + tenant admin against an
    already-created tenant (the row was inserted by ``POST /tenants``).

    Returns HTTP 201 with the same envelope as ``POST /tenants/provision``.
    Returns:
        404 ``tenant_not_found`` if the tenant does not exist.
        409 ``tenant_already_provisioned`` if it has already been provisioned.
        409 ``tenant_archived`` if the tenant is archived.
        422 for validation errors / duplicate admin email.
    """
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")

    # We need the existing tenant's name/slug to default workspace fields,
    # so resolve before validation.
    from app.services.provisioning.repository import ProvisioningRepository

    tenant_row = ProvisioningRepository.find_tenant_by_id(db, str(validated_id))
    if tenant_row is None:
        raise TenantAPIError(404, "tenant_not_found", "Tenant not found.")

    # ── Validate body fields ─────────────────────────────────────────
    admin_email = validate_admin_email(body.admin_email)
    admin_full_name = validate_admin_full_name(body.admin_full_name)
    workspace_name = validate_workspace_name(body.workspace_name, tenant_row.tenant_name)
    workspace_slug = validate_workspace_slug(body.workspace_slug, tenant_row.tenant_slug)

    command = ProvisionExistingTenantCommand(
        tenant_id=validated_id,
        admin_email=admin_email,
        admin_full_name=admin_full_name,
        workspace_name=workspace_name,
        workspace_slug=workspace_slug,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
    )

    result: ProvisionTenantResult = ProvisioningService.provision_existing_tenant(
        db,
        command,
    )

    return JSONResponse(
        status_code=201,
        content={
            "data": {
                "tenant": {
                    "tenant_id": result.tenant_id,
                    "tenant_name": result.tenant_name,
                    "tenant_slug": result.tenant_slug,
                    "status": result.status,
                    "region": result.region,
                    "plan": result.plan,
                    "provisioning_status": result.provisioning_status,
                    "created_at": _format_dt(result.created_at),
                },
                "workspace": {
                    "workspace_id": result.workspace_id,
                    "workspace_name": result.workspace_name,
                    "workspace_slug": result.workspace_slug,
                },
                "admin": {
                    "user_id": result.admin_user_id,
                    "email": result.admin_email,
                    "full_name": result.admin_full_name,
                    "status": "pending",
                },
                "invitation": {
                    "password_reset_token": result.password_reset_token,
                    "activation_url": f"/auth/set-password?token={result.password_reset_token}",
                    "expires_in_hours": 72,
                },
                "provisioning_steps": [
                    {
                        "step_name": s.step_name,
                        "step_order": s.step_order,
                        "status": s.status,
                    }
                    for s in result.steps
                ],
            },
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/tenants/{tenant_id}/provisioning-logs
# ---------------------------------------------------------------------------


@router.get("/{tenant_id}/provisioning-logs", status_code=200)
def get_provisioning_logs(
    tenant_id: str,
    actor: ActorContext = Depends(require_read_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Fetch provisioning step logs for a tenant.

    Returns HTTP 200 with ordered list of provisioning steps.
    """
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")

    logs = ProvisioningService.get_provisioning_status(db, str(validated_id))

    return JSONResponse(
        status_code=200,
        content={
            "data": [
                {
                    "log_id": log["log_id"],
                    "step_name": log["step_name"],
                    "step_order": log["step_order"],
                    "status": log["status"],
                    "started_at": _format_dt(log.get("started_at")),
                    "completed_at": _format_dt(log.get("completed_at")),
                    "error_message": log.get("error_message"),
                    "step_data": log.get("step_data"),
                }
                for log in logs
            ],
        },
    )
