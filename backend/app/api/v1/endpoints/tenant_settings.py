"""
Tenant Settings endpoints.

Exposes:
    GET   /api/v1/tenants/{tenant_id}/settings/smtp
    PUT   /api/v1/tenants/{tenant_id}/settings/smtp
    POST  /api/v1/tenants/{tenant_id}/settings/smtp/test

Authorization: platform_admin OR first-class tenant_admin whose JWT
``tenant_id`` matches the path.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
    validate_uuid_path_param,
)
from app.models.database import get_db
from app.services.tenant.settings_service import (
    SMTPSettingsResponse,
    TenantSettingsService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenants/{tenant_id}/settings", tags=["tenant-settings"])


def _require_tenant_scope(tenant_id: UUID, actor: ActorContext) -> None:
    if actor.actor_role == "platform_admin":
        return
    if (
        actor.actor_role == "tenant_admin"
        and actor.tenant_id is not None
        and str(actor.tenant_id) == str(tenant_id)
    ):
        return
    raise TenantAPIError(
        status_code=403,
        code="forbidden",
        message="Tenant admin privileges required for this tenant.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class SMTPSettingsRead(BaseModel):
    enabled: bool
    host: str | None = None
    port: int | None = None
    username: str | None = None
    has_password: bool = False
    use_tls: bool = True
    from_address: str | None = None
    last_tested_at: str | None = None
    last_test_ok: bool | None = None
    last_test_error: str | None = None


class SMTPSettingsUpdate(BaseModel):
    enabled: bool | None = None
    host: str | None = Field(default=None, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=512)
    clear_password: bool | None = False
    use_tls: bool | None = None
    from_address: str | None = Field(default=None, max_length=255)


class SMTPTestRequest(BaseModel):
    recipient: EmailStr | None = None


def _to_dto(r: SMTPSettingsResponse) -> dict:
    return {
        "enabled": r.enabled,
        "host": r.host,
        "port": r.port,
        "username": r.username,
        "has_password": r.has_password,
        "use_tls": r.use_tls,
        "from_address": r.from_address,
        "last_tested_at": r.last_tested_at.isoformat() if r.last_tested_at else None,
        "last_test_ok": r.last_test_ok,
        "last_test_error": r.last_test_error,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/smtp", status_code=200)
def get_smtp_settings(
    tenant_id: str,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_tenant_scope(validated, actor)

    service = TenantSettingsService()
    result = service.get_smtp_settings(db, validated)
    return JSONResponse(status_code=200, content={"data": _to_dto(result)})


@router.put("/smtp", status_code=200)
def update_smtp_settings(
    tenant_id: str,
    payload: SMTPSettingsUpdate,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_tenant_scope(validated, actor)

    service = TenantSettingsService()
    try:
        result = service.update_smtp_settings(
            db,
            validated,
            enabled=payload.enabled,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password,
            clear_password=bool(payload.clear_password),
            use_tls=payload.use_tls,
            from_address=payload.from_address,
            updated_by=actor.actor_id,
        )
    except ValueError as exc:
        raise TenantAPIError(status_code=400, code="invalid_input", message=str(exc))

    return JSONResponse(status_code=200, content={"data": _to_dto(result)})


@router.post("/smtp/test", status_code=200)
def test_smtp_settings(
    tenant_id: str,
    payload: SMTPTestRequest,
    actor: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> JSONResponse:
    validated = validate_uuid_path_param(tenant_id, "tenant_id")
    _require_tenant_scope(validated, actor)

    service = TenantSettingsService()
    result = service.test_smtp(db, validated, recipient=payload.recipient)
    status_code = 200 if result.get("success") else 400
    return JSONResponse(status_code=status_code, content={"data": result})
