"""
F001 — /api/v1/tenants endpoints
=================================

Implements:
    POST   /api/v1/tenants             (TDD §3.2 — Create Tenant)          [Packet 3]
    GET    /api/v1/tenants             (TDD §3.3 — List Tenants)            [Packet 4]
    GET    /api/v1/tenants/{tenant_id} (TDD §3.4 — Get Tenant Detail)       [Packet 5]
    PATCH  /api/v1/tenants/{tenant_id} (TDD §3.5 — Update Tenant Metadata)  [Packet 6]

Auth guards:
    POST/PATCH — Bearer JWT required; actor_role must be platform_admin
    GET        — Bearer JWT required; actor_role must be platform_admin or platform_viewer

Errors returned as ``{"error": {"code", "message", "fields"}}``
(registered globally in app.main via ``tenant_api_error_handler``).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    _UUID_V4_RE,
    ActorContext,
    TenantAPIError,
    require_read_access,
    require_tenant_read_access,
    require_write_access,
    validate_uuid_path_param,
)
from app.models.database import get_db
from app.services.tenants.commands import (
    ChangeStatusCommand,
    ChangeStatusDTO,
    ChangeStatusRequest,
    CreateTenantCommand,
    CreateTenantRequest,
    PatchTenantRequest,
    TenantDetailDTO,
    TenantDTO,
    UpdateTenantCommand,
)
from app.services.tenants.metrics import emit_tenant_create_failure
from app.services.tenants.queries import parse_list_tenants_query
from app.services.tenants.registry import get_user_registry_client, get_workspace_registry_client
from app.services.tenants.repository import AuditLogRepository, TenantRepository
from app.services.tenants.service import TenantService
from app.services.tenants.validators import (
    validate_initial_status,
    validate_plan,
    validate_region,
    validate_service_start_date,
    validate_status_reason,
    validate_tenant_name,
    validate_tenant_notes,
    validate_tenant_slug,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _format_dt(dt: Any) -> str | None:
    """Format a datetime as an ISO 8601 UTC string, handling naive datetimes."""
    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _serialise_tenant_dto(dto: TenantDTO) -> dict[str, Any]:
    """Convert TenantDTO to a JSON-safe dict matching TDD §3.2 response shape."""
    ssd: str | None = (
        dto.service_start_date.isoformat() if dto.service_start_date is not None else None
    )
    return {
        "tenant_id": dto.tenant_id,
        "tenant_name": dto.tenant_name,
        "tenant_slug": dto.tenant_slug,
        "status": dto.status,
        "status_reason": dto.status_reason,
        "region": dto.region,
        "plan": dto.plan,
        "service_start_date": ssd,
        "tenant_notes": dto.tenant_notes,
        "created_at": _format_dt(dto.created_at),
        "updated_at": _format_dt(dto.updated_at),
        "created_by": dto.created_by,
        "updated_by": dto.updated_by,
    }


# ---------------------------------------------------------------------------
# POST /api/v1/tenants — Create Tenant  (Packet 3)
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
def create_tenant(
    body: CreateTenantRequest,
    actor: ActorContext = Depends(require_write_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Create a new tenant.

    Returns HTTP 201 with ``{"data": {<tenant fields>}}`` on success.
    """
    # ------------------------------------------------------------------
    # Input validation — emit "invalid_input" metric on any validator
    # rejection so the metric reflects real input quality signals.
    # ------------------------------------------------------------------
    try:
        tenant_name = validate_tenant_name(body.tenant_name)
        tenant_slug = validate_tenant_slug(body.tenant_slug)
        region = validate_region(body.region)
        plan = validate_plan(body.plan)
        initial_status = validate_initial_status(body.initial_status)
        service_start_date = validate_service_start_date(body.service_start_date)
        tenant_notes = validate_tenant_notes(body.tenant_notes)
        status_reason = validate_status_reason(body.status_reason)
    except TenantAPIError:
        try:
            emit_tenant_create_failure("invalid_input")
        except Exception:  # pragma: no cover
            pass
        raise

    command = CreateTenantCommand(
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        region=region,
        plan=plan,
        initial_status=initial_status,
        status_reason=status_reason,
        service_start_date=service_start_date,
        tenant_notes=tenant_notes,
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
    )

    dto: TenantDTO = TenantService.create_tenant(db, command)

    return JSONResponse(
        status_code=201,
        content={"data": _serialise_tenant_dto(dto)},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/tenants — List Tenants  (Packet 4)
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
def list_tenants(
    # Query parameters — declared as Optional[str] so that FastAPI passes raw
    # strings and our own validator controls the 422 error envelope format.
    # Multi-value: FastAPI with Optional[str] silently uses the first value only.
    status: str | None = Query(default=None),
    region: str | None = Query(default=None),
    plan: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str | None = Query(default=None),
    include_archived: str | None = Query(default=None),
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    actor: ActorContext = Depends(require_read_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """List tenants with filtering, sorting, and pagination.

    Authorization:
        platform_admin or platform_viewer → 200
        customer_actor / unrecognised role → 403
        missing / invalid token → 401

    Returns HTTP 200 with ``{"data": [...], "meta": {...}}`` on success.
    """
    list_query = parse_list_tenants_query(
        status=status,
        region=region,
        plan=plan,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        include_archived_str=include_archived,
        page_str=page,
        page_size_str=page_size,
    )

    rows, total = TenantRepository.list(db, list_query)

    data = [
        {
            "tenant_id": row["tenant_id"],
            "tenant_name": row["tenant_name"],
            "tenant_slug": row["tenant_slug"],
            "status": str(row["status"]),
            "region": str(row["region"]),
            "plan": str(row["plan"]),
            "created_at": _format_dt(row["created_at"]),
            "updated_at": _format_dt(row["updated_at"]),
        }
        for row in rows
    ]

    has_next = (list_query.page * list_query.page_size) < total

    return JSONResponse(
        status_code=200,
        content={
            "data": data,
            "meta": {
                "total": total,
                "page": list_query.page,
                "page_size": list_query.page_size,
                "has_next": has_next,
            },
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/tenants/{tenant_id} — Get Tenant Detail  (Packet 5)
# ---------------------------------------------------------------------------


def _serialise_detail_dto(dto: TenantDetailDTO) -> dict[str, Any]:
    """Convert TenantDetailDTO to a JSON-safe dict matching TDD §3.4 response shape."""
    ssd: str | None = (
        dto.service_start_date.isoformat() if dto.service_start_date is not None else None
    )
    return {
        "tenant_id": dto.tenant_id,
        "tenant_name": dto.tenant_name,
        "tenant_slug": dto.tenant_slug,
        "status": dto.status,
        "status_reason": dto.status_reason,
        "region": dto.region,
        "plan": dto.plan,
        "service_start_date": ssd,
        "tenant_notes": dto.tenant_notes,
        "created_at": _format_dt(dto.created_at),
        "updated_at": _format_dt(dto.updated_at),
        "created_by": dto.created_by,
        "updated_by": dto.updated_by,
        "workspace_count": dto.workspace_count,
        "workspace_count_available": dto.workspace_count_available,
        "user_count": dto.user_count,
        "user_count_available": dto.user_count_available,
        "audit_summary_link": dto.audit_summary_link,
    }


@router.get("/{tenant_id}", status_code=200)
def get_tenant_detail(
    tenant_id: str,
    actor: ActorContext = Depends(require_tenant_read_access()),
    db: Session = Depends(get_db),
    workspace_client=Depends(get_workspace_registry_client),
    user_client=Depends(get_user_registry_client),
) -> JSONResponse:
    """Return full tenant detail including registry-sourced aggregate counts.

    Authorization:
        platform_admin or platform_viewer → 200
        customer_actor / unrecognised role → 403
        missing / invalid token → 401

    Path parameter validation:
        Valid UUID v4 → proceed
        Malformed / wrong-version UUID → 400 invalid_path_parameter

    Returns HTTP 200 with ``{"data": {<18 fields>}}`` on success.
    Returns HTTP 404 ``not_found`` when the tenant does not exist.
    """
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")

    dto: TenantDetailDTO = TenantService.get_tenant_detail(
        db, str(validated_id), workspace_client, user_client
    )

    return JSONResponse(
        status_code=200,
        content={"data": _serialise_detail_dto(dto)},
    )


# ---------------------------------------------------------------------------
# PATCH /api/v1/tenants/{tenant_id} — Update Tenant Metadata  (Packet 6)
# ---------------------------------------------------------------------------

# Mutable and immutable field sets (used for body-key detection before DB access)
_PATCH_IMMUTABLE_FIELDS: frozenset = frozenset({"tenant_slug", "region", "tenant_id"})
_PATCH_MUTABLE_FIELDS: frozenset = frozenset(
    {"tenant_name", "plan", "status_reason", "service_start_date", "tenant_notes"}
)


@router.patch("/{tenant_id}", status_code=200)
def update_tenant_metadata(
    tenant_id: str,
    body: PatchTenantRequest,
    actor: ActorContext = Depends(require_write_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Update mutable tenant metadata fields.

    Authorization:
        platform_admin → 200
        platform_viewer / customer_actor / unrecognised role → 403
        missing / invalid token → 401

    Path parameter validation:
        Valid UUID v4 → proceed
        Malformed / wrong-version UUID → 400 invalid_path_parameter

    Body validation (all before DB access):
        Immutable field present (tenant_slug / region / tenant_id) → 422 immutable_field
        status field present → 422 use_status_endpoint
        No mutable fields present → 422 no_mutable_fields

    Returns HTTP 200 with the full updated tenant DTO (13 fields) on success.
    """
    # ------------------------------------------------------------------
    # 1. Path parameter validation
    # ------------------------------------------------------------------
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")

    # ------------------------------------------------------------------
    # 2. Immutable-field and status-field detection (no DB access yet)
    # ------------------------------------------------------------------
    extra_keys = set(body.model_extra or {})

    for field in _PATCH_IMMUTABLE_FIELDS:
        if field in extra_keys:
            raise TenantAPIError(
                422,
                "immutable_field",
                f"'{field}' is immutable and cannot be modified.",
                [{"field": field, "reason": "immutable_field"}],
            )

    if "status" in extra_keys:
        raise TenantAPIError(
            422,
            "use_status_endpoint",
            "Use POST /api/v1/tenants/{tenant_id}/status to change tenant lifecycle status.",
        )

    # ------------------------------------------------------------------
    # 3. At least one mutable field must be present
    # ------------------------------------------------------------------
    provided_keys = body.model_fields_set & _PATCH_MUTABLE_FIELDS
    if not provided_keys:
        raise TenantAPIError(
            422,
            "no_mutable_fields",
            "Request body must contain at least one mutable field: "
            + ", ".join(sorted(_PATCH_MUTABLE_FIELDS))
            + ".",
        )

    # ------------------------------------------------------------------
    # 4. Normalize and validate each provided mutable field
    # ------------------------------------------------------------------
    fields: dict[str, Any] = {}

    if "tenant_name" in provided_keys:
        fields["tenant_name"] = validate_tenant_name(body.tenant_name)

    if "plan" in provided_keys:
        fields["plan"] = validate_plan(body.plan)

    if "status_reason" in provided_keys:
        # Basic format validation only; context-sensitive guards (clear on
        # suspended/archived, min-10-char rule) happen in the service after
        # the FOR UPDATE lock is acquired and the current status is known.
        fields["status_reason"] = validate_status_reason(body.status_reason)

    if "service_start_date" in provided_keys:
        fields["service_start_date"] = validate_service_start_date(body.service_start_date)

    if "tenant_notes" in provided_keys:
        fields["tenant_notes"] = validate_tenant_notes(body.tenant_notes)

    # ------------------------------------------------------------------
    # 5. Build command and delegate to service
    # ------------------------------------------------------------------
    command = UpdateTenantCommand(
        tenant_id=str(validated_id),
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        fields=fields,
    )

    dto: TenantDTO = TenantService.update_tenant(db, command)

    return JSONResponse(
        status_code=200,
        content={"data": _serialise_tenant_dto(dto)},
    )


# ---------------------------------------------------------------------------
# POST /api/v1/tenants/{tenant_id}/status — Change Tenant Status  (Packet 7)
# ---------------------------------------------------------------------------

# Valid audit event type values (TDD §2.4)
_VALID_AUDIT_EVENT_TYPES: frozenset = frozenset(
    {"tenant_created", "tenant_updated", "tenant_status_changed"}
)

# Valid target status values (TDD §2.6 + §6.5)
_VALID_TARGET_STATUSES: frozenset = frozenset({"draft", "active", "suspended", "archived"})


def _serialise_change_status_dto(dto: ChangeStatusDTO) -> dict[str, Any]:
    """Convert ChangeStatusDTO to a JSON-safe dict matching TDD §3.6 response shape."""
    return {
        "tenant_id": dto.tenant_id,
        "previous_status": dto.previous_status,
        "current_status": dto.current_status,
        "status_reason": dto.status_reason,
        "updated_at": _format_dt(dto.updated_at),
        "updated_by": dto.updated_by,
    }


@router.get("/{tenant_id}/status", status_code=200)
def get_tenant_status(
    tenant_id: str,
    actor: ActorContext = Depends(require_tenant_read_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Return the current lifecycle + provisioning status of a tenant (BUG-011).

    Authorization:
        platform_admin, platform_viewer, or tenant admin of ``tenant_id`` → 200
        Other roles → 403
        Missing / invalid token → 401

    Returns HTTP 200 with::

        {"data": {"tenant_id": ..., "status": ...,
                  "provisioning_status": ...,
                  "updated_at": ISO-8601}}
    """
    from sqlalchemy import text as _sql_text

    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")
    row = db.execute(
        _sql_text(
            """
            SELECT tenant_id, status, provisioning_status, updated_at
            FROM control.tenants
            WHERE tenant_id = :tid
            LIMIT 1
            """
        ),
        {"tid": str(validated_id)},
    ).fetchone()
    if row is None:
        raise TenantAPIError(404, "not_found", "Tenant not found.")

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "tenant_id": str(row.tenant_id),
                "status": row.status,
                "provisioning_status": row.provisioning_status,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
        },
    )


@router.post("/{tenant_id}/status", status_code=200)
def change_tenant_status(
    tenant_id: str,
    body: ChangeStatusRequest | None = Body(default=None),
    actor: ActorContext = Depends(require_write_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Change tenant lifecycle status.

    Authorization:
        platform_admin → 200
        platform_viewer / customer_actor / unrecognised role → 403
        missing / invalid token → 401

    Path parameter validation:
        Valid UUID v4 → proceed
        Malformed / wrong-version UUID → 400 invalid_path_parameter

    Returns HTTP 200 with status change summary DTO (6 fields) on success.
    """
    # ------------------------------------------------------------------
    # 1. Path parameter validation
    # ------------------------------------------------------------------
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")

    # ------------------------------------------------------------------
    # 2. Missing request body detection (TDD §3.6)
    # ------------------------------------------------------------------
    if body is None:
        raise TenantAPIError(
            400,
            "missing_request_body",
            "Request body is required.",
        )

    # ------------------------------------------------------------------
    # 3. Normalize and validate target_status
    # ------------------------------------------------------------------
    raw_target = body.target_status
    if raw_target is None:
        raise TenantAPIError(
            422,
            "validation_error",
            "target_status is required.",
            [{"field": "target_status", "reason": "required"}],
        )

    target_status = raw_target.strip().lower()
    if not target_status:
        raise TenantAPIError(
            422,
            "validation_error",
            "target_status is required.",
            [{"field": "target_status", "reason": "required"}],
        )

    if target_status not in _VALID_TARGET_STATUSES:
        raise TenantAPIError(
            422,
            "invalid_target_status",
            f"target_status must be one of: {', '.join(sorted(_VALID_TARGET_STATUSES))}.",
        )

    # ------------------------------------------------------------------
    # 4. Normalize status_reason (trimmed; empty → None)
    # ------------------------------------------------------------------
    raw_reason = body.status_reason
    if raw_reason is not None:
        status_reason: str | None = raw_reason.strip() or None
    else:
        status_reason = None

    # ------------------------------------------------------------------
    # 5. Build command and delegate to service
    # ------------------------------------------------------------------
    command = ChangeStatusCommand(
        tenant_id=str(validated_id),
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        target_status=target_status,
        status_reason=status_reason,
    )

    dto: ChangeStatusDTO = TenantService.change_status(db, command)

    return JSONResponse(
        status_code=200,
        content={"data": _serialise_change_status_dto(dto)},
    )


# ---------------------------------------------------------------------------
# DELETE /api/v1/tenants/{tenant_id} — Hard delete (Platform Admin only)
# ---------------------------------------------------------------------------


@router.delete("/{tenant_id}", status_code=204)
def hard_delete_tenant(
    tenant_id: str,
    actor: ActorContext = Depends(require_write_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Permanently delete a tenant and every dependent row.

    Authorization:
        platform_admin → 204
        any other role → 403
        missing / invalid token → 401

    Path parameter validation:
        Valid UUID v4 → proceed
        Malformed / wrong-version UUID → 400 invalid_path_parameter

    This is destructive and irreversible.  It removes the tenant row and
    every workspace, audit log, dataset, data source and other tenant-scoped
    record across the ``control`` schema.
    """
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")
    TenantService.hard_delete(db, str(validated_id), actor.actor_id)
    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# GET /api/v1/tenants/{tenant_id}/audit-logs — Audit Logs  (Packet 8)
# ---------------------------------------------------------------------------

_ISO_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _parse_iso_datetime(value: str, field_name: str) -> datetime:
    """Parse an ISO 8601 UTC datetime string; raise 422 validation_error on failure."""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise TenantAPIError(
            422,
            "validation_error",
            f"'{field_name}' must be a valid ISO 8601 UTC datetime string.",
            [{"field": field_name, "reason": "invalid_datetime_format"}],
        )
    # Normalise to UTC-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _serialise_audit_log(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw audit log DB row to a JSON-safe dict (TDD §3.7 response shape)."""
    return {
        "log_id": row["log_id"],
        "tenant_id": row["tenant_id"],
        "event_type": row["event_type"],
        "actor_id": row["actor_id"],
        "actor_role": row["actor_role"],
        "previous_data": row["previous_data"],
        "new_data": row["new_data"],
        "occurred_at": _format_dt(row["occurred_at"]),
        "reason": row["reason"],
    }


@router.get("/{tenant_id}/audit-logs", status_code=200)
def list_audit_logs(
    tenant_id: str,
    event_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to_: str | None = Query(default=None, alias="to"),
    page: str | None = Query(default=None),
    page_size: str | None = Query(default=None),
    actor: ActorContext = Depends(require_read_access()),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Return paginated audit log entries for a single tenant.

    Authorization:
        platform_admin or platform_viewer → 200
        customer_actor / unrecognised role → 403
        missing / invalid token → 401

    Path parameter validation:
        Valid UUID v4 → proceed
        Malformed / wrong-version UUID → 400 invalid_path_parameter

    Returns HTTP 200 with ``{"data": [...], "meta": {...}}`` on success.
    Returns HTTP 404 ``not_found`` when the tenant does not exist.
    """
    # ------------------------------------------------------------------
    # 1. Path parameter validation
    # ------------------------------------------------------------------
    validated_id = validate_uuid_path_param(tenant_id, "tenant_id")
    tenant_id_str = str(validated_id)

    # ------------------------------------------------------------------
    # 2. Tenant existence check
    # ------------------------------------------------------------------
    if not TenantRepository.exists(db, tenant_id_str):
        raise TenantAPIError(404, "not_found", "Tenant not found.")

    # ------------------------------------------------------------------
    # 3. Query parameter validation
    # ------------------------------------------------------------------

    # event_type
    validated_event_type: str | None = None
    if event_type is not None:
        et = event_type.strip()
        if et not in _VALID_AUDIT_EVENT_TYPES:
            raise TenantAPIError(
                422,
                "validation_error",
                f"event_type must be one of: {', '.join(sorted(_VALID_AUDIT_EVENT_TYPES))}.",
                [{"field": "event_type", "reason": "invalid_value"}],
            )
        validated_event_type = et

    # actor_id
    validated_actor_id: str | None = None
    if actor_id is not None:
        aid = actor_id.strip()
        if not _UUID_V4_RE.match(aid):
            raise TenantAPIError(
                422,
                "invalid_uuid_format",
                "actor_id must be a valid UUID v4.",
                [{"field": "actor_id", "reason": "invalid_uuid_format"}],
            )
        validated_actor_id = aid

    # from / to datetime
    from_dt: datetime | None = None
    to_dt: datetime | None = None

    if from_ is not None:
        from_dt = _parse_iso_datetime(from_, "from")

    if to_ is not None:
        to_dt = _parse_iso_datetime(to_, "to")

    if from_dt is not None and to_dt is not None and from_dt > to_dt:
        raise TenantAPIError(
            422,
            "invalid_date_range",
            "'from' must not be later than 'to'.",
            [{"field": "from", "reason": "invalid_date_range"}],
        )

    # page
    validated_page = 1
    if page is not None:
        try:
            validated_page = int(page)
        except ValueError:
            raise TenantAPIError(
                422,
                "validation_error",
                "page must be a positive integer.",
                [{"field": "page", "reason": "invalid_integer"}],
            )
        if validated_page < 1:
            raise TenantAPIError(
                422,
                "validation_error",
                "page must be >= 1.",
                [{"field": "page", "reason": "out_of_range"}],
            )

    # page_size
    validated_page_size = 25
    if page_size is not None:
        try:
            validated_page_size = int(page_size)
        except ValueError:
            raise TenantAPIError(
                422,
                "validation_error",
                "page_size must be a positive integer.",
                [{"field": "page_size", "reason": "invalid_integer"}],
            )
        if not (1 <= validated_page_size <= 100):
            raise TenantAPIError(
                422,
                "validation_error",
                "page_size must be between 1 and 100.",
                [{"field": "page_size", "reason": "out_of_range"}],
            )

    # ------------------------------------------------------------------
    # 4. Query repository
    # ------------------------------------------------------------------
    rows, total = AuditLogRepository.list_by_tenant(
        db,
        tenant_id_str=tenant_id_str,
        event_type=validated_event_type,
        actor_id_str=validated_actor_id,
        from_dt=from_dt,
        to_dt=to_dt,
        page=validated_page,
        page_size=validated_page_size,
    )

    data: list[dict[str, Any]] = [_serialise_audit_log(row) for row in rows]
    has_next = (validated_page * validated_page_size) < total

    return JSONResponse(
        status_code=200,
        content={
            "data": data,
            "meta": {
                "total": total,
                "page": validated_page,
                "page_size": validated_page_size,
                "has_next": has_next,
            },
        },
    )
