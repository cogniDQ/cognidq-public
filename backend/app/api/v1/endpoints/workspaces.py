"""
F002 — /api/v1/workspaces endpoints
====================================

Implements:
    POST   /api/v1/workspaces                                   (TDD §4.1 — Create Workspace)           [Packet 4]
    PATCH  /api/v1/workspaces/{workspace_id}                    (TDD §4.3 — Update Workspace)            [Packet 5]
    POST   /api/v1/workspaces/{workspace_id}/archive            (TDD §4.4 — Archive Workspace)           [Packet 6]
    POST   /api/v1/workspaces/{workspace_id}/restore            (TDD §4.5 — Restore Workspace)           [Packet 6]
    GET    /api/v1/workspaces                                   (TDD §4.6 — List Workspaces)            [Packet 7]
    GET    /api/v1/workspaces/{workspace_id}                    (TDD §4.7 — Get Workspace Detail)       [Packet 7]
    GET    /api/v1/workspaces/{workspace_id}/audit-logs         (TDD §4.8 — List Audit Logs)            [Packet 8]

Auth guards:
    POST/PATCH/archive/restore — Bearer JWT; actor_role must be workspace_administrator
    GET (list/detail)          — Bearer JWT; any authenticated role accepted
    GET audit-logs             — Bearer JWT; workspace_administrator OR platform_admin/platform_viewer

Errors returned as {"error": {"code", "message", "fields"}}
(registered globally in app.main via workspace_api_error_handler).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID as PythonUUID

from fastapi import APIRouter, Body, Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies.request_context import (
    extract_source_ip,
    get_request_id,
)
from app.api.v1.dependencies.workspace_auth import (
    PLATFORM_OPERATOR_ROLES,
    WorkspaceActorContext,
    require_workspace_permission,
    verify_any_authenticated_actor,
    verify_workspace_create_admin,
)
from app.models.database import get_db
from app.services.workspaces.errors import (
    WorkspaceAPIError,
    format_validation_errors,
    map_service_exception_to_http,
)
from app.services.workspaces.metrics import (
    emit_workspace_create_failure,
    emit_workspace_create_success,
    emit_workspace_settings_read_success,
    emit_workspace_settings_update_failure,
    emit_workspace_status_change_failure,
    emit_workspace_status_change_success,
    emit_workspace_update_failure,
    emit_workspace_update_success,
)
from app.services.workspaces.models import Workspace, WorkspaceAuditLog
from app.services.workspaces.rbac import WorkspaceRBACService
from app.services.workspaces.registry import (
    WorkspaceDatasetRegistry,
    WorkspaceMemberRegistry,
)
from app.services.workspaces.repository import (
    VALID_AUDIT_ACTION_TYPES,
    AuditLogRepository,
    AuditLogWriter,
    TenantRepository,
    WorkspaceRepository,
)
from app.services.workspaces.service import WorkspaceService
from app.services.workspaces.validation import (
    ARCHIVE_ALLOWED_FIELDS,
    CREATE_ALLOWED_FIELDS,
    FORBIDDEN_FIELDS,
    IMMUTABLE_FIELDS,
    UPDATE_ALLOWED_FIELDS,
    validate_create_payload,
    validate_update_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# ---------------------------------------------------------------------------
# OpenAPI body schemas (BUG-008 — POST /workspaces was previously untyped)
# ---------------------------------------------------------------------------


class CreateWorkspaceRequest(BaseModel):
    """Request body for POST /api/v1/workspaces.

    ``extra='allow'`` preserves forwarded fields so the downstream
    forbidden/unknown-field detector (``_detect_forbidden_unknown_fields``)
    can still reject them.
    """

    model_config = ConfigDict(extra="allow")

    workspace_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Display name (unique per tenant, case-insensitive).",
    )
    workspace_slug: str = Field(
        ..., min_length=1, max_length=100, description="URL-safe identifier (unique per tenant)."
    )
    description: str | None = Field(default=None, max_length=2000)
    default_timezone: str | None = Field(
        default=None, max_length=50, description="IANA timezone string; defaults to UTC."
    )


class UpdateWorkspaceRequest(BaseModel):
    """Request body for PATCH /api/v1/workspaces/{workspace_id}."""

    model_config = ConfigDict(extra="allow")

    workspace_name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    default_timezone: str | None = Field(default=None, max_length=50)


# ---------------------------------------------------------------------------
# Dependency factories
# ---------------------------------------------------------------------------


def get_workspace_service(db: Session = Depends(get_db)) -> WorkspaceService:
    """
    Dependency factory for WorkspaceService.

    Sprint 4.7 — DatasetRegistryStub/MemberRegistryStub replaced with real
    DB-backed registries (`WorkspaceDatasetRegistry` / `WorkspaceMemberRegistry`)
    so workspace detail returns accurate counts.
    """
    workspace_repo = WorkspaceRepository()
    tenant_repo = TenantRepository()
    audit_writer = AuditLogWriter()
    rbac_service = WorkspaceRBACService()
    dataset_registry = WorkspaceDatasetRegistry(db)
    member_registry = WorkspaceMemberRegistry(db)
    audit_log_repo = AuditLogRepository()

    return WorkspaceService(
        workspace_repo=workspace_repo,
        tenant_repo=tenant_repo,
        audit_writer=audit_writer,
        rbac_service=rbac_service,
        dataset_registry=dataset_registry,
        member_registry=member_registry,
        audit_log_repo=audit_log_repo,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _serialize_workspace(workspace: Workspace) -> dict[str, Any]:
    """
    Convert Workspace domain model to JSON-safe dict.

    Excludes internal fields (workspace_name_lower, version) per TDD §4.1.
    Formats datetimes as ISO 8601 UTC strings.
    """
    return {
        "workspace_id": str(workspace.workspace_id),
        "tenant_id": str(workspace.tenant_id),
        "workspace_name": workspace.workspace_name,
        "workspace_slug": workspace.workspace_slug,
        "description": workspace.description,
        "default_timezone": workspace.default_timezone,
        "status": workspace.status.value,
        "status_reason": workspace.status_reason,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
        "created_by": str(workspace.created_by),
        "updated_by": str(workspace.updated_by),
    }


def _fetch_tenant_names(db: Session, tenant_ids: list[Any]) -> dict[str, str]:
    """Bulk fetch ``{tenant_id: tenant_name}`` for the given tenant ids.

    Used to enrich workspace list/detail responses with the parent tenant's
    display name without forcing the caller to hit the tenants endpoint
    (which is gated by tenant-admin roles).
    """
    from sqlalchemy import text as _sql_text

    unique_ids = {str(t) for t in tenant_ids if t is not None}
    if not unique_ids:
        return {}
    rows = db.execute(
        _sql_text(
            "SELECT tenant_id::text, tenant_name FROM control.tenants "
            "WHERE tenant_id = ANY(CAST(:ids AS UUID[]))"
        ),
        {"ids": list(unique_ids)},
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _serialize_workspace_list_item(
    workspace: Workspace, tenant_name: str | None = None
) -> dict[str, Any]:
    """
    Serialize a workspace for the list endpoint response (TDD §4.6).

    Returns the reduced shape defined in §4.6 — trimmed to only the fields
    explicitly required by the list contract.  ``workspace_name_lower`` and
    ``version`` are always excluded.  ``tenant_id`` is excluded from list items
    (not in the §4.6 response schema).
    """
    return {
        "workspace_id": str(workspace.workspace_id),
        "tenant_id": str(workspace.tenant_id),
        "tenant_name": tenant_name,
        "workspace_name": workspace.workspace_name,
        "workspace_slug": workspace.workspace_slug,
        "status": workspace.status.value,
        "default_timezone": workspace.default_timezone,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
    }


def _serialize_workspace_detail(
    workspace: Workspace,
    dataset_count: int | None,
    member_count: int | None,
    warnings: list[dict[str, Any]],
    tenant_name: str | None = None,
) -> dict[str, Any]:
    """
    Serialize a workspace for the detail endpoint response (TDD §4.7).

    Includes all core fields plus the aggregate/enrichment fields:
    ``audit_log_link``, ``dataset_count``, ``member_count``, ``warnings``.

    ``workspace_name_lower`` and ``version`` are always excluded.
    ``audit_log_link`` is a relative path (not an absolute URL) per TDD §4.7.
    ``warnings`` is ``null`` when the list is empty (not an empty array).
    """
    return {
        "workspace_id": str(workspace.workspace_id),
        "tenant_id": str(workspace.tenant_id),
        "tenant_name": tenant_name,
        "workspace_name": workspace.workspace_name,
        "workspace_slug": workspace.workspace_slug,
        "description": workspace.description,
        "default_timezone": workspace.default_timezone,
        "status": workspace.status.value,
        "status_reason": workspace.status_reason,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
        "created_by": str(workspace.created_by),
        "updated_by": str(workspace.updated_by),
        "audit_log_link": f"/api/v1/workspaces/{workspace.workspace_id}/audit-logs",
        "dataset_count": dataset_count,
        "member_count": member_count,
        "warnings": warnings if warnings else None,
    }


def _detect_forbidden_unknown_fields(raw_payload: dict[str, Any]) -> None:
    """
    Detect forbidden/unknown fields and raise HTTP 400 error.

    Per TDD §4.3: Forbidden/unknown fields → HTTP 400 (not 422).
    Must detect BEFORE calling validation layer.

    Raises:
        WorkspaceAPIError: HTTP 400 if forbidden/unknown fields detected
    """
    forbidden = [f for f in raw_payload.keys() if f in FORBIDDEN_FIELDS]
    unknown = [f for f in raw_payload.keys() if f not in CREATE_ALLOWED_FIELDS]

    errors = []
    for field in forbidden:
        errors.append(
            {
                "field": field,
                "error_code": "forbidden_field",
                "message": f"Field '{field}' is system-managed and cannot be set",
            }
        )

    for field in unknown:
        errors.append(
            {
                "field": field,
                "error_code": "unknown_field",
                "message": f"Field '{field}' is not recognized",
            }
        )

    if errors:
        raise WorkspaceAPIError(
            status_code=400,
            code="invalid_fields",
            message="Request contains forbidden or unknown fields",
            fields=errors,
        )


def _detect_forbidden_unknown_immutable_fields_update(raw_payload: dict[str, Any]) -> None:
    """
    Detect forbidden/unknown/immutable fields in PATCH request.

    Per TDD §4.3:
    - Immutable fields (workspace_slug) → HTTP 422 immutable_field
    - Forbidden fields (workspace_id, tenant_id) → HTTP 400 forbidden_field
    - Unknown fields → HTTP 400 unknown_field

    Must detect BEFORE calling validation layer.

    Raises:
        WorkspaceAPIError: HTTP 400 or HTTP 422 depending on field type
    """
    # Check immutable fields (HTTP 422)
    immutable = [f for f in raw_payload.keys() if f in IMMUTABLE_FIELDS]
    if immutable:
        errors = []
        for field in immutable:
            errors.append(
                {
                    "field": field,
                    "error_code": "immutable_field",
                    "message": f"Field '{field}' cannot be modified after creation",
                }
            )
        raise WorkspaceAPIError(
            status_code=422,
            code="immutable_field",
            message="Request contains immutable fields that cannot be updated",
            fields=errors,
        )

    # Check forbidden/unknown fields (HTTP 400)
    forbidden = [f for f in raw_payload.keys() if f in FORBIDDEN_FIELDS]
    allowed_or_immutable = UPDATE_ALLOWED_FIELDS | IMMUTABLE_FIELDS
    unknown = [f for f in raw_payload.keys() if f not in allowed_or_immutable]

    errors = []
    for field in forbidden:
        errors.append(
            {
                "field": field,
                "error_code": "forbidden_field",
                "message": f"Field '{field}' is system-managed and cannot be set",
            }
        )

    for field in unknown:
        errors.append(
            {
                "field": field,
                "error_code": "unknown_field",
                "message": f"Field '{field}' is not recognized",
            }
        )

    if errors:
        raise WorkspaceAPIError(
            status_code=400,
            code="invalid_fields",
            message="Request contains forbidden or unknown fields",
            fields=errors,
        )


# ---------------------------------------------------------------------------
# Metric failure_reason canonicalization helpers (TDD §12.1)
# ---------------------------------------------------------------------------

# Valid failure_reason values for workspace_create_failure_count
_CREATE_FAILURE_REASONS: frozenset = frozenset(
    {
        "duplicate_name",
        "duplicate_slug",
        "invalid_input",
        "tenant_not_active",
        "unauthorized",
        "internal_error",
    }
)

# Codes that map to "invalid_input"
_CREATE_INVALID_INPUT_CODES: frozenset = frozenset(
    {
        "validation_error",
        "unknown_field",
        "invalid_field_type",
        "forbidden_field",
        "immutable_field",
        "invalid_fields",
        "missing_required_field",
    }
)


def _canon_create_failure(code: str) -> str:
    """Canonicalize HTTP error code to a valid workspace_create_failure_count label."""
    if code in _CREATE_FAILURE_REASONS:
        return code
    if code in _CREATE_INVALID_INPUT_CODES:
        return "invalid_input"
    if code in ("insufficient_permissions",):
        return "unauthorized"
    return "internal_error"


# Valid failure_reason values for workspace_status_change_failure_count
_STATUS_FAILURE_REASONS: frozenset = frozenset(
    {
        "forbidden_transition",
        "missing_reason",
        "tenant_not_active",
        "unauthorized",
        "no_op",
        "last_active_workspace",
        "internal_error",
    }
)


def _canon_status_failure(code: str) -> str:
    """Canonicalize HTTP error code to a valid workspace_status_change_failure_count label."""
    if code in _STATUS_FAILURE_REASONS:
        return code
    if code in _CREATE_INVALID_INPUT_CODES:
        return "invalid_input"
    if code in ("insufficient_permissions",):
        return "unauthorized"
    return "internal_error"


# ---------------------------------------------------------------------------
# POST /api/v1/workspaces — Create Workspace (Packet 4)
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_workspace(
    request: Request,
    body: CreateWorkspaceRequest = Body(...),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(verify_workspace_create_admin),
    request_id: str = Depends(get_request_id),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    Create a new workspace.

    Authorization:
        - Bearer JWT required with valid tenant_id
        - Actor must have workspace_administrator role in tenant
        - Actor must be active in authentication framework

    Request body:
        {
            "workspace_name": str (required),
            "workspace_slug": str (required),
            "description": str | null (optional),
            "default_timezone": str (optional, defaults to UTC)
        }

    Returns:
        HTTP 201 with {"data": {<workspace fields>}} on success

    Errors:
        400 - Forbidden/unknown fields
        401 - Actor not active
        403 - Insufficient permissions
        422 - Validation errors, tenant not active, duplicate name/slug
        500 - Internal errors (role grant failed, audit write failed)
    """
    logger.info(
        "POST /workspaces called: tenant_id=%s actor_id=%s request_id=%s",
        actor.tenant_id,
        actor.actor_id,
        request_id,
    )

    try:
        # Parse request body — prefer the raw JSON so forbidden-field
        # detection still works for fields outside the Pydantic schema
        # (``extra='allow'`` carries them through, but raw is source of truth).
        try:
            raw_payload: dict[str, Any] = await request.json()
        except Exception:
            raw_payload = body.model_dump(exclude_unset=True)

        # Platform operators (platform_admin / platform_viewer) have no
        # tenant_id in their JWT but may legitimately create workspaces in
        # any tenant. Accept an explicit ``tenant_id`` in the body for them
        # and pop it from the raw payload before the forbidden-field check
        # so it isn't treated as unknown for tenant-admin callers either.
        body_tenant_id_raw = raw_payload.pop("tenant_id", None)
        target_tenant_id = actor.tenant_id
        if body_tenant_id_raw is not None:
            if actor.actor_role != "platform_admin":
                raise WorkspaceAPIError(
                    status_code=403,
                    code="insufficient_permissions",
                    message="Only platform_admin may specify tenant_id when creating a workspace.",
                    fields=None,
                )
            try:
                target_tenant_id = PythonUUID(str(body_tenant_id_raw))
            except (ValueError, TypeError):
                raise WorkspaceAPIError(
                    status_code=422,
                    code="invalid_input",
                    message="tenant_id must be a valid UUID.",
                    fields=[
                        {
                            "field": "tenant_id",
                            "error_code": "invalid_uuid",
                            "message": "Not a valid UUID",
                        }
                    ],
                )
        if target_tenant_id is None:
            raise WorkspaceAPIError(
                status_code=422,
                code="invalid_input",
                message="A tenant_id is required to create a workspace.",
                fields=[
                    {
                        "field": "tenant_id",
                        "error_code": "required",
                        "message": "Missing tenant context",
                    }
                ],
            )

        # Step 1: Detect forbidden/unknown fields (HTTP 400)
        # Must happen BEFORE validation layer
        _detect_forbidden_unknown_fields(raw_payload)

        # Step 2: Validate payload (pure validation)
        validation_result = validate_create_payload(raw_payload)

        if not validation_result.is_valid:
            # HTTP 422 for validation errors
            raise format_validation_errors(validation_result.errors)

        # Step 3: Extract source IP from X-Forwarded-For
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        source_ip = extract_source_ip(x_forwarded_for=x_forwarded_for)

        # Step 4: Call service layer (3-write atomic transaction)
        # Service will:
        # - Check tenant status (active)
        # - INSERT workspace
        # - Grant workspace_administrator role
        # - Write audit log entry
        workspace = service.create_workspace(
            db=db,
            tenant_id=target_tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            raw_payload=validation_result.normalized_payload,
            request_id=request_id,
            source_ip=source_ip,
        )

        # Commit transaction
        db.commit()

        # Emit success metric AFTER commit (TDD §12.1: post-commit only)
        emit_workspace_create_success(str(actor.tenant_id))

        logger.info(
            "POST /workspaces success: workspace_id=%s tenant_id=%s",
            workspace.workspace_id,
            actor.tenant_id,
        )

        # Return HTTP 201 with data envelope
        return JSONResponse(status_code=201, content={"data": _serialize_workspace(workspace)})

    except WorkspaceAPIError as wapi_err:
        # Already formatted error - re-raise after emitting metric
        db.rollback()
        emit_workspace_create_failure(_canon_create_failure(wapi_err.code))
        raise

    except Exception as exc:
        # Map service layer exceptions to HTTP errors
        db.rollback()
        logger.error(
            "POST /workspaces failed: tenant_id=%s error=%s",
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        http_error = map_service_exception_to_http(exc)
        emit_workspace_create_failure(_canon_create_failure(http_error.code))
        raise http_error


# ---------------------------------------------------------------------------
# PATCH /api/v1/workspaces/{workspace_id} — Update Workspace (Packet 5)
# ---------------------------------------------------------------------------


@router.patch("/{workspace_id}", status_code=200)
async def update_workspace(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("workspaces:write")),
    request_id: str = Depends(get_request_id),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    Update workspace metadata (name, description, timezone).

    Authorization:
        - Bearer JWT required with valid tenant_id
        - Actor must have workspace_administrator role in tenant
        - Actor must be active in authentication framework

    Request body:
        {
            "workspace_name": str (optional),
            "description": str | null (optional),
            "default_timezone": str (optional)
        }

    Returns:
        HTTP 200 with {"data": {<workspace fields>}} on success
        HTTP 200 with {"data": null} if no-op detected (empty {} or all values identical)

    Errors:
        400 - Forbidden/unknown fields
        401 - Actor not active
        403 - Insufficient permissions
        422 - Validation errors, immutable field, workspace archived, tenant not active, duplicate name
        500 - Internal errors (audit write failed)
    """
    logger.info(
        "PATCH /workspaces/%s called: tenant_id=%s actor_id=%s request_id=%s",
        workspace_id,
        actor.tenant_id,
        actor.actor_id,
        request_id,
    )

    try:
        # Parse request body
        raw_payload: dict[str, Any] = await request.json()

        # Step 1: Detect forbidden/unknown/immutable fields
        # Must happen BEFORE validation layer
        _detect_forbidden_unknown_immutable_fields_update(raw_payload)

        # Step 2: Validate payload (pure validation)
        validation_result = validate_update_payload(raw_payload)

        if not validation_result.is_valid:
            # HTTP 422 for validation errors
            raise format_validation_errors(validation_result.errors)

        # Step 3: Extract source IP from X-Forwarded-For
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        source_ip = extract_source_ip(x_forwarded_for=x_forwarded_for)

        # Step 4: Call service layer (16-step Flow B atomic transaction)
        # Service will:
        # - SELECT FOR UPDATE with tenant isolation
        # - Check workspace status (not archived)
        # - Check tenant status (active)
        # - Normalize incoming values
        # - Detect no-op (empty {} or all values identical)
        # - Validate payload
        # - Check duplicate workspace_name (only if name changed)
        # - Increment version
        # - Write audit log (only changed fields)
        workspace = service.update_workspace(
            db=db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            raw_payload=validation_result.normalized_payload,
            request_id=request_id,
            source_ip=source_ip,
        )

        # Handle no-op case (None returned from service)
        if workspace is None:
            db.commit()
            logger.info("PATCH /workspaces/%s no-op: empty payload or no changes", workspace_id)
            return JSONResponse(status_code=200, content={"data": None})

        # Commit transaction
        db.commit()

        # Emit success metric AFTER commit (TDD §12.1: post-commit only)
        _updated_fields = ",".join(sorted(validation_result.normalized_payload.keys()))
        emit_workspace_update_success(_updated_fields)

        logger.info("PATCH /workspaces/%s success: tenant_id=%s", workspace_id, actor.tenant_id)

        # Return HTTP 200 with data envelope
        return JSONResponse(status_code=200, content={"data": _serialize_workspace(workspace)})

    except WorkspaceAPIError as wapi_err:
        # Already formatted error - re-raise after emitting metric
        db.rollback()
        emit_workspace_update_failure(wapi_err.code)
        raise

    except Exception as exc:
        # Map service layer exceptions to HTTP errors
        db.rollback()
        logger.error(
            "PATCH /workspaces/%s failed: tenant_id=%s error=%s",
            workspace_id,
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        http_error = map_service_exception_to_http(exc)
        emit_workspace_update_failure(http_error.code)
        raise http_error


# ---------------------------------------------------------------------------
# POST /api/v1/workspaces/{workspace_id}/archive — Archive Workspace (Packet 6)
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/archive", status_code=200)
async def archive_workspace(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("workspaces:write")),
    request_id: str = Depends(get_request_id),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    Archive an active workspace (Flow C, TDD §4.4).

    Request body:
        {
            "status_reason": str (required, 10–500 chars after trim),
            "confirm_last_workspace": bool (conditional — required as true
                when this is the last active workspace in the Tenant)
        }

    Returns:
        HTTP 200 with {"data": {<workspace fields>}} on success

    Errors:
        400 - Unknown field; confirm_last_workspace is not a JSON boolean
        401 - Actor not active
        403 - Insufficient permissions
        404 - Workspace not found
        409 - Last-workspace confirmation absent
        422 - Invalid transition (not active); missing/invalid status_reason
        500 - Internal error
    """
    logger.info(
        "POST /workspaces/%s/archive called: tenant_id=%s actor_id=%s request_id=%s",
        workspace_id,
        actor.tenant_id,
        actor.actor_id,
        request_id,
    )

    try:
        # Parse request body (treat empty/absent body as empty dict)
        try:
            raw_payload: dict[str, Any] = await request.json()
            if not isinstance(raw_payload, dict):
                raw_payload = {}
        except Exception:
            raw_payload = {}

        # Step 1a: detect unknown fields → HTTP 400
        unknown = [f for f in raw_payload if f not in ARCHIVE_ALLOWED_FIELDS]
        if unknown:
            fields = [
                {
                    "field": f,
                    "error_code": "unknown_field",
                    "message": f"Field '{f}' is not recognised",
                }
                for f in unknown
            ]
            raise WorkspaceAPIError(
                status_code=400,
                code="unknown_field",
                message="Request contains unknown fields",
                fields=fields,
            )

        # Step 1b: validate confirm_last_workspace type at controller level (TDD tasks §3)
        # String "true" / "false" must be rejected as HTTP 400 invalid_field_type
        if "confirm_last_workspace" in raw_payload:
            if not isinstance(raw_payload["confirm_last_workspace"], bool):
                raise WorkspaceAPIError(
                    status_code=400,
                    code="invalid_field_type",
                    message=(
                        "Field 'confirm_last_workspace' must be a JSON boolean "
                        "(true or false), not a string or other type."
                    ),
                    fields=[
                        {
                            "field": "confirm_last_workspace",
                            "error_code": "invalid_field_type",
                            "message": "Must be a JSON boolean (true or false)",
                        }
                    ],
                )

        # Step 2: auth guard (already applied via Depends)
        # Step 3: call service (status_reason validation happens inside service
        #         AFTER the workspace-status check, per ordering rule A-8)
        source_ip = extract_source_ip(x_forwarded_for=request.headers.get("X-Forwarded-For"))

        workspace = service.archive_workspace(
            db=db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            raw_payload=raw_payload,
            request_id=request_id,
            source_ip=source_ip,
        )

        db.commit()

        # Emit success metric AFTER commit (TDD §12.1: post-commit only)
        emit_workspace_status_change_success("active", "archived")

        logger.info(
            "POST /workspaces/%s/archive success: tenant_id=%s",
            workspace_id,
            actor.tenant_id,
        )

        return JSONResponse(
            status_code=200,
            content={"data": _serialize_workspace(workspace)},
        )

    except WorkspaceAPIError as wapi_err:
        db.rollback()
        emit_workspace_status_change_failure(_canon_status_failure(wapi_err.code))
        raise

    except Exception as exc:
        db.rollback()
        logger.error(
            "POST /workspaces/%s/archive failed: tenant_id=%s error=%s",
            workspace_id,
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        http_error = map_service_exception_to_http(exc)
        # workspace_not_found (404) is not a status-change failure per TDD §12.1
        if http_error.status_code != 404:
            emit_workspace_status_change_failure(_canon_status_failure(http_error.code))
        raise http_error


# ---------------------------------------------------------------------------
# POST /api/v1/workspaces/{workspace_id}/restore — Restore Workspace (Packet 6)
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/restore", status_code=200)
async def restore_workspace(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("workspaces:write")),
    request_id: str = Depends(get_request_id),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    Restore an archived workspace (Flow D, TDD §4.5).

    No required body fields.  Accepts empty body or no body at all.

    Returns:
        HTTP 200 with {"data": {<workspace fields>}} on success
        (status = "active", status_reason = null)

    Errors:
        401 - Actor not active
        403 - Insufficient permissions
        404 - Workspace not found
        422 - Invalid transition (not archived); Tenant not active
        500 - Internal error
    """
    logger.info(
        "POST /workspaces/%s/restore called: tenant_id=%s actor_id=%s request_id=%s",
        workspace_id,
        actor.tenant_id,
        actor.actor_id,
        request_id,
    )

    try:
        source_ip = extract_source_ip(x_forwarded_for=request.headers.get("X-Forwarded-For"))

        workspace = service.restore_workspace(
            db=db,
            workspace_id=workspace_id,
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            request_id=request_id,
            source_ip=source_ip,
        )

        db.commit()

        # Emit success metric AFTER commit (TDD §12.1: post-commit only)
        emit_workspace_status_change_success("archived", "active")

        logger.info(
            "POST /workspaces/%s/restore success: tenant_id=%s",
            workspace_id,
            actor.tenant_id,
        )

        return JSONResponse(
            status_code=200,
            content={"data": _serialize_workspace(workspace)},
        )

    except WorkspaceAPIError as wapi_err:
        db.rollback()
        emit_workspace_status_change_failure(_canon_status_failure(wapi_err.code))
        raise

    except Exception as exc:
        db.rollback()
        logger.error(
            "POST /workspaces/%s/restore failed: tenant_id=%s error=%s",
            workspace_id,
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        http_error = map_service_exception_to_http(exc)
        # workspace_not_found (404) is not a status-change failure per TDD §12.1
        if http_error.status_code != 404:
            emit_workspace_status_change_failure(_canon_status_failure(http_error.code))
        raise http_error


# ---------------------------------------------------------------------------
# Validation helpers for query parameters (list endpoint)
# ---------------------------------------------------------------------------

_VALID_SORT_BY = frozenset({"created_at", "updated_at"})
_VALID_SORT_DIR = frozenset({"asc", "desc"})


def _validate_list_params(
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
    tenant_id_param: str | None,
    actor_role: str,
) -> None:
    """
    Validate all query parameters for GET /workspaces.

    Raises ``WorkspaceAPIError`` on the first category of error (per TDD §4.6):
    - sort_by not in allowlist → 422 invalid_sort_field
    - sort_dir not in allowlist → 422 invalid_sort_direction
    - page < 1               → 422 validation_error
    - page_size outside 1–100 → 422 validation_error
    - tenant_id by non-Platform-Operator → 422 forbidden_parameter
    """
    if sort_by not in _VALID_SORT_BY:
        raise WorkspaceAPIError(
            status_code=422,
            code="invalid_sort_field",
            message=(
                f"Invalid sort_by value '{sort_by}'. Allowed values: {sorted(_VALID_SORT_BY)}"
            ),
        )

    if sort_dir not in _VALID_SORT_DIR:
        raise WorkspaceAPIError(
            status_code=422,
            code="invalid_sort_direction",
            message=(f"Invalid sort_dir value '{sort_dir}'. Allowed values: 'asc', 'desc'"),
        )

    if page < 1:
        raise WorkspaceAPIError(
            status_code=422,
            code="validation_error",
            message="Query parameter 'page' must be >= 1.",
            fields=[
                {
                    "field": "page",
                    "error_code": "validation_error",
                    "message": "Must be >= 1",
                }
            ],
        )

    if page_size < 1 or page_size > 100:
        raise WorkspaceAPIError(
            status_code=422,
            code="validation_error",
            message="Query parameter 'page_size' must be between 1 and 100 inclusive.",
            fields=[
                {
                    "field": "page_size",
                    "error_code": "validation_error",
                    "message": "Must be between 1 and 100 inclusive",
                }
            ],
        )

    if tenant_id_param is not None and actor_role not in PLATFORM_OPERATOR_ROLES:
        raise WorkspaceAPIError(
            status_code=422,
            code="forbidden_parameter",
            message=(
                "Query parameter 'tenant_id' is only available to "
                "Platform Admin and Platform Viewer roles."
            ),
        )


# ---------------------------------------------------------------------------
# GET /api/v1/workspaces — List Workspaces (Packet 7)
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
async def list_workspaces(
    request: Request,
    include_archived: bool = Query(default=False),
    q: str | None = Query(default=None),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1),
    page_size: int = Query(default=25),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(verify_any_authenticated_actor),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    List workspaces with filtering, sorting, and pagination (TDD §4.6).

    Authorization:
        - Bearer JWT required; any authenticated role accepted (A-10)
        - Results are always scoped to the actor's tenant_id from the JWT
        - Platform Admin/Viewer may supply `tenant_id` query param to scope
          results to a specific Tenant

    Query Parameters:
        include_archived (bool): Include archived workspaces (default: false)
        q (str): ILIKE search against workspace_name and workspace_slug
        sort_by (str): 'created_at' or 'updated_at' (default: 'created_at')
        sort_dir (str): 'asc' or 'desc' (default: 'desc')
        page (int): 1-based page number (default: 1)
        page_size (int): Results per page, 1-100 (default: 25)
        tenant_id (UUID): Platform Admin/Viewer only; scope to specific Tenant

    Returns:
        HTTP 200 with {"data": [...], "meta": {"total", "page", "page_size", "has_next"}}

    Errors:
        401 - Missing/invalid token
        422 - Invalid query parameter value or forbidden_parameter
    """
    logger.info(
        "GET /workspaces called: tenant_id=%s actor_id=%s role=%s",
        actor.tenant_id,
        actor.actor_id,
        actor.actor_role,
    )

    try:
        # Read tenant_id query param as raw string (not typed UUID) so we
        # can return forbidden_parameter before any UUID parse error fires.
        tenant_id_param: str | None = request.query_params.get("tenant_id")

        # Validate all query parameters
        _validate_list_params(
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
            tenant_id_param=tenant_id_param,
            actor_role=actor.actor_role,
        )

        # BUG-010: a user authenticated without a tenant_id claim (fresh
        # signup, pre-provisioning) has no workspaces to list.  Return an
        # empty page with HTTP 200 rather than failing.
        if actor.tenant_id is None and actor.actor_role not in PLATFORM_OPERATOR_ROLES:
            return JSONResponse(
                status_code=200,
                content={
                    "data": [],
                    "meta": {
                        "total": 0,
                        "page": page,
                        "page_size": page_size,
                        "has_next": False,
                    },
                },
            )

        # Resolve effective tenant_id (A-10)
        effective_tenant_id = actor.tenant_id
        if actor.actor_role in PLATFORM_OPERATOR_ROLES and tenant_id_param is not None:
            try:
                effective_tenant_id = PythonUUID(tenant_id_param)
            except ValueError:
                raise WorkspaceAPIError(
                    status_code=422,
                    code="validation_error",
                    message="Query parameter 'tenant_id' must be a valid UUID.",
                    fields=[
                        {
                            "field": "tenant_id",
                            "error_code": "validation_error",
                            "message": "Must be a valid UUID",
                        }
                    ],
                )

        workspaces, total = service.list_workspaces(
            db=db,
            tenant_id=effective_tenant_id,
            include_archived=include_archived,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
            # Non-operators (plus non-tenant-admin) only see workspaces where
            # they have a role assignment — prevents leaking workspace names
            # they cannot access and avoids dead links in the picker.
            restrict_to_user_id=(
                None
                if actor.actor_role in PLATFORM_OPERATOR_ROLES or actor.actor_role == "tenant_admin"
                else actor.actor_id
            ),
        )

        has_next = (page * page_size) < total

        logger.info(
            "GET /workspaces success: tenant_id=%s total=%s page=%s page_size=%s",
            effective_tenant_id,
            total,
            page,
            page_size,
        )

        tenant_name_map = _fetch_tenant_names(db, [ws.tenant_id for ws in workspaces])

        return JSONResponse(
            status_code=200,
            content={
                "data": [
                    _serialize_workspace_list_item(
                        ws, tenant_name=tenant_name_map.get(str(ws.tenant_id))
                    )
                    for ws in workspaces
                ],
                "meta": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "has_next": has_next,
                },
            },
        )

    except WorkspaceAPIError:
        raise

    except Exception as exc:
        logger.error(
            "GET /workspaces failed: tenant_id=%s error=%s",
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        raise map_service_exception_to_http(exc)


# ---------------------------------------------------------------------------
# GET /api/v1/workspaces/{workspace_id} — Get Workspace Detail (Packet 7)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}", status_code=200)
async def get_workspace_detail(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(verify_any_authenticated_actor),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    Get full workspace detail including aggregate counts (TDD §4.7).

    Authorization:
        - Bearer JWT required; any role that holds membership in the workspace
        - Platform Admin/Viewer may access all workspaces across all Tenants
        - Cross-tenant requests return HTTP 404 (information disclosure prevention)

    Returns:
        HTTP 200 with {"data": {full workspace fields + audit_log_link,
                                dataset_count, member_count, warnings}}

    Errors:
        401 - Missing/invalid token
        404 - Not found, cross-tenant, or non-member access
        500 - Internal server error
    """
    logger.info(
        "GET /workspaces/%s called: tenant_id=%s actor_id=%s role=%s",
        workspace_id,
        actor.tenant_id,
        actor.actor_id,
        actor.actor_role,
    )

    try:
        # Platform operators may access workspaces across all tenants; pass None
        # so the repository uses the any-tenant query instead of scoping by tenant_id.
        effective_tenant_id = (
            None if actor.actor_role in PLATFORM_OPERATOR_ROLES else actor.tenant_id
        )
        workspace, dataset_count, member_count, warnings = service.get_workspace_detail(
            db=db,
            workspace_id=workspace_id,
            tenant_id=effective_tenant_id,
        )

        # BUG-004: non-operator callers MUST hold a workspace_role_assignments
        # row for this workspace.  Return 404 (not 403) to avoid leaking the
        # existence of workspaces the caller has no right to see.
        # tenant_admin is exempt: they have implicit access to every workspace
        # within their own tenant (the effective_tenant_id scoping above already
        # ensures the workspace belongs to that tenant — cross-tenant lookups
        # surface as 404 from the repository).
        if actor.actor_role not in PLATFORM_OPERATOR_ROLES and actor.actor_role != "tenant_admin":
            from sqlalchemy import text as _sql_text

            is_member = db.execute(
                _sql_text(
                    "SELECT 1 FROM control.workspace_role_assignments "
                    "WHERE workspace_id = :ws AND user_id = :uid LIMIT 1"
                ),
                {"ws": str(workspace_id), "uid": str(actor.actor_id)},
            ).fetchone()
            if is_member is None:
                raise WorkspaceAPIError(
                    status_code=404,
                    code="not_found",
                    message="Workspace not found.",
                )

        logger.info(
            "GET /workspaces/%s success: tenant_id=%s status=%s",
            workspace_id,
            actor.tenant_id,
            workspace.status.value,
        )

        return JSONResponse(
            status_code=200,
            content={
                "data": _serialize_workspace_detail(
                    workspace=workspace,
                    dataset_count=dataset_count,
                    member_count=member_count,
                    warnings=warnings,
                    tenant_name=_fetch_tenant_names(db, [workspace.tenant_id]).get(
                        str(workspace.tenant_id)
                    ),
                )
            },
        )

    except WorkspaceAPIError:
        raise

    except Exception as exc:
        logger.error(
            "GET /workspaces/%s failed: tenant_id=%s error=%s",
            workspace_id,
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        raise map_service_exception_to_http(exc)


# ---------------------------------------------------------------------------
# Serializer for audit log entries (Packet 8)
# ---------------------------------------------------------------------------


def _serialize_audit_log_entry(entry: WorkspaceAuditLog) -> dict[str, Any]:
    """
    Convert ``WorkspaceAuditLog`` to a JSON-safe dict for the API response.

    All ``workspace_audit_logs`` columns are exposed except FK redundancy is
    retained as readable UUIDs (``workspace_id``, ``tenant_id``, ``actor_id``).
    ``previous_data`` and ``new_data`` are already dicts (JSONB decoded by
    psycopg2); they are included as-is.  NULL ``request_id`` → ``null``.
    """
    return {
        "log_id": str(entry.log_id),
        "workspace_id": str(entry.workspace_id),
        "tenant_id": str(entry.tenant_id),
        "action_type": entry.action_type,
        "actor_id": str(entry.actor_id),
        "actor_role": entry.actor_role,
        "previous_data": entry.previous_data,
        "new_data": entry.new_data,
        "occurred_at": entry.occurred_at.isoformat(),
        "request_id": str(entry.request_id) if entry.request_id else None,
        "source_ip": entry.source_ip,
    }


# ---------------------------------------------------------------------------
# Validation helpers for audit log query parameters (Packet 8)
# ---------------------------------------------------------------------------


def _validate_audit_log_params(
    action_type: str | None,
    actor_id_raw: str | None,
    from_date_raw: str | None,
    to_date_raw: str | None,
    page: int,
    page_size: int,
) -> tuple[str | None, PythonUUID | None, Any | None, Any | None]:
    """
    Validate all query parameters for GET /workspaces/{id}/audit-logs.

    Returns
    -------
    (action_type, actor_id, from_date, to_date) — all validated/parsed values.

    Raises ``WorkspaceAPIError`` on validation failure:
    - action_type not in known values      → 422 invalid_filter_value
    - actor_id malformed UUID              → 400 invalid_parameter
    - from_date / to_date not ISO 8601 UTC → 422 invalid_parameter
    - from_date > to_date                  → 422 invalid_date_range
    - page < 1                             → 422 validation_error
    - page_size outside 1–100             → 422 validation_error
    """
    from datetime import datetime

    # --- action_type ---
    if action_type is not None and action_type not in VALID_AUDIT_ACTION_TYPES:
        raise WorkspaceAPIError(
            status_code=422,
            code="invalid_filter_value",
            message=(
                f"Unrecognized action_type '{action_type}'. "
                f"Valid values: {sorted(VALID_AUDIT_ACTION_TYPES)}"
            ),
            fields=[
                {
                    "field": "action_type",
                    "error_code": "invalid_filter_value",
                    "message": f"Must be one of {sorted(VALID_AUDIT_ACTION_TYPES)}",
                }
            ],
        )

    # --- actor_id ---
    parsed_actor_id: PythonUUID | None = None
    if actor_id_raw is not None:
        try:
            parsed_actor_id = PythonUUID(actor_id_raw)
        except (ValueError, AttributeError):
            raise WorkspaceAPIError(
                status_code=400,
                code="invalid_parameter",
                message=f"'actor_id' must be a valid UUID v4, got: '{actor_id_raw}'",
                fields=[
                    {
                        "field": "actor_id",
                        "error_code": "invalid_parameter",
                        "message": "Must be a valid UUID v4",
                    }
                ],
            )

    # --- from_date / to_date ---
    def _parse_iso_date(raw: str, field_name: str):
        """Parse ISO 8601 UTC string; raise WorkspaceAPIError on failure."""
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt
        except (ValueError, AttributeError):
            raise WorkspaceAPIError(
                status_code=422,
                code="invalid_parameter",
                message=f"'{field_name}' must be a valid ISO 8601 UTC timestamp, got: '{raw}'",
                fields=[
                    {
                        "field": field_name,
                        "error_code": "invalid_parameter",
                        "message": "Must be a valid ISO 8601 UTC timestamp",
                    }
                ],
            )

    parsed_from_date = _parse_iso_date(from_date_raw, "from_date") if from_date_raw else None
    parsed_to_date = _parse_iso_date(to_date_raw, "to_date") if to_date_raw else None

    if parsed_from_date is not None and parsed_to_date is not None:
        if parsed_from_date > parsed_to_date:
            raise WorkspaceAPIError(
                status_code=422,
                code="invalid_date_range",
                message="'from_date' must not be later than 'to_date'.",
                fields=[
                    {
                        "field": "from_date",
                        "error_code": "invalid_date_range",
                        "message": "Must be before or equal to to_date",
                    },
                    {
                        "field": "to_date",
                        "error_code": "invalid_date_range",
                        "message": "Must be after or equal to from_date",
                    },
                ],
            )

    # --- page ---
    if page < 1:
        raise WorkspaceAPIError(
            status_code=422,
            code="validation_error",
            message="Query parameter 'page' must be >= 1.",
            fields=[{"field": "page", "error_code": "validation_error", "message": "Must be >= 1"}],
        )

    # --- page_size ---
    if page_size < 1 or page_size > 100:
        raise WorkspaceAPIError(
            status_code=422,
            code="validation_error",
            message="Query parameter 'page_size' must be between 1 and 100 inclusive.",
            fields=[
                {
                    "field": "page_size",
                    "error_code": "validation_error",
                    "message": "Must be between 1 and 100 inclusive",
                }
            ],
        )

    return action_type, parsed_actor_id, parsed_from_date, parsed_to_date


# ---------------------------------------------------------------------------
# GET /api/v1/workspaces/{workspace_id}/settings — Get Settings (F003 P04)
# ---------------------------------------------------------------------------


def _serialize_naming_constraint(nc) -> dict:
    """Serialise a NamingConstraint to a plain dict for the API response."""
    return {
        "required_prefix": nc.required_prefix,
        "required_suffix": nc.required_suffix,
        "pattern": nc.pattern,
        "max_length": nc.max_length,
        "allow_special_characters": nc.allow_special_characters,
    }


def _serialize_incident_policy(ip) -> dict:
    """Serialise an IncidentPolicy to a plain dict for the API response."""
    return {
        "enabled": ip.enabled,
        "min_severity": ip.min_severity,
        "recurrence_threshold": ip.recurrence_threshold,
        "auto_priority": ip.auto_priority,
        "auto_owner_user_id": str(ip.auto_owner_user_id) if ip.auto_owner_user_id else None,
    }


def _serialize_llm_config(lc) -> dict:
    """Serialise LLMConfig to a dict for the API response.

    The API key is masked — only the last 4 characters are shown.
    """
    masked_key = ""
    if lc.api_key_encrypted:
        # Show a masked placeholder; the real key is encrypted in DB
        masked_key = "••••••••"
    return {
        "provider": lc.provider,
        "api_key_masked": masked_key,
        "model": lc.model,
        "temperature": lc.temperature,
        "max_tokens": lc.max_tokens,
        "configured": bool(lc.api_key_encrypted),
    }


def _serialize_workspace_settings(s) -> dict:
    """Serialise WorkspaceSettings to the F003 TDD §4.1 response shape."""
    ns = s.naming_standards
    result = {
        "workspace_id": str(s.workspace_id),
        "tenant_id": str(s.tenant_id),
        "timezone_policy": {
            "default_timezone": s.default_timezone,
        },
        "severity_policy": {
            "critical_label": s.severity_policy.critical_label,
            "major_label": s.severity_policy.major_label,
            "minor_label": s.severity_policy.minor_label,
            "informational_label": s.severity_policy.informational_label,
        },
        "sla_policy": {
            "critical_hours": s.sla_policy.critical_hours,
            "major_hours": s.sla_policy.major_hours,
            "minor_hours": s.sla_policy.minor_hours,
            "informational_hours": s.sla_policy.informational_hours,
        },
        "issue_grouping_policy": s.issue_grouping_policy,
        "naming_standards": {
            "datasets": _serialize_naming_constraint(ns.datasets),
            "rules": _serialize_naming_constraint(ns.rules),
        },
        "incident_policy": _serialize_incident_policy(s.incident_policy)
        if s.incident_policy
        else None,
        "llm_config": _serialize_llm_config(s.llm_config) if s.llm_config else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "updated_by": str(s.updated_by) if s.updated_by else None,
    }
    return result


@router.get("/{workspace_id}/settings", status_code=200)
async def get_workspace_settings(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:read")),
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    """
    Return the effective workspace settings, applying built-in defaults for
    any policy fields that are NULL in the database (F003 TDD §4.1).

    Authorization:
        - Bearer JWT required
        - Allowed roles: workspace_administrator, data_engineer, data_steward,
          platform_admin, platform_viewer
        - All other roles → HTTP 403
        - Platform Operators may access any workspace cross-tenant

    Returns:
        HTTP 200 with the full settings object per TDD §4.1 response shape.

    Errors:
        401 — missing or invalid JWT
        403 — role not in allowed set
        404 — workspace not found or cross-tenant access (for WA/DE/DS)
        500 — internal server error
    """
    from app.services.workspaces.exceptions import WorkspaceNotFoundError
    from app.services.workspaces.settings_service import get_settings

    logger.debug(
        "GET /workspaces/%s/settings: actor_id=%s role=%s request_id=%s",
        workspace_id,
        actor.actor_id,
        actor.actor_role,
        request_id,
    )

    try:
        settings = get_settings(db=db, workspace_id=workspace_id, actor=actor)
    except WorkspaceNotFoundError:
        raise WorkspaceAPIError(
            status_code=404,
            code="workspace_not_found",
            message="Workspace not found or you do not have access.",
        )
    except Exception as exc:
        logger.exception(
            "GET /workspaces/%s/settings unexpected error: %s",
            workspace_id,
            exc,
        )
        raise WorkspaceAPIError(
            status_code=500,
            code="internal_server_error",
            message="An unexpected error occurred.",
        )

    logger.debug(
        "GET /workspaces/%s/settings success: actor_id=%s role=%s",
        workspace_id,
        actor.actor_id,
        actor.actor_role,
    )

    emit_workspace_settings_read_success()

    return JSONResponse(
        status_code=200,
        content={"data": _serialize_workspace_settings(settings)},
    )


# ---------------------------------------------------------------------------
# PATCH /api/v1/workspaces/{workspace_id}/settings — Update Settings (F003 P05)
# ---------------------------------------------------------------------------


@router.patch("/{workspace_id}/settings", status_code=200)
async def patch_workspace_settings(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace UUID"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("settings:write")),
    request_id: str = Depends(get_request_id),
) -> JSONResponse:
    """
    Partially update workspace settings policies (F003 TDD §4.2).

    Authorization:
        - Bearer JWT required
        - Allowed roles: workspace_administrator ONLY
        - Platform Operators → HTTP 403 (no cross-tenant write)

    Request body (all keys optional, at least one required):
        {
            "timezone_policy": {"default_timezone": str},
            "severity_policy": {critical_label, major_label, minor_label, informational_label},
            "sla_policy": {critical_hours, major_hours, minor_hours, informational_hours?},
            "issue_grouping_policy": str,
            "naming_standards": {"datasets": {...}, "rules": {...}}
        }

    Returns:
        HTTP 200 with {"data": {<full settings shape>}} — updated values
        HTTP 200 with {"data": <full settings shape>} also for no-op (unchanged)

    Errors:
        401 — missing or invalid JWT
        403 — role not in allowed set (including platform operators)
        404 — workspace not found
        422 — validation errors, unknown fields, empty body, workspace archived
        500 — internal server error
    """
    from app.services.workspaces.exceptions import (
        WorkspaceArchivedError,
        WorkspaceNotFoundError,
    )
    from app.services.workspaces.settings_service import (
        EmptyRequestError,
        UnknownFieldError,
        update_settings,
    )

    logger.debug(
        "PATCH /workspaces/%s/settings: actor_id=%s role=%s request_id=%s",
        workspace_id,
        actor.actor_id,
        actor.actor_role,
        request_id,
    )

    try:
        body: dict[str, Any] = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}

    source_ip = extract_source_ip(x_forwarded_for=request.headers.get("X-Forwarded-For"))

    try:
        updated = update_settings(
            db=db,
            workspace_id=workspace_id,
            body=body,
            actor=actor,
            request_id=request_id,
            source_ip=source_ip,
        )
        db.commit()
    except UnknownFieldError as exc:
        db.rollback()
        emit_workspace_settings_update_failure("validation_error")
        raise WorkspaceAPIError(
            status_code=422,
            code="unknown_fields",
            message="Request body contains unrecognised fields.",
            fields=[
                {"field": f, "error_code": "unknown_field", "message": f"Unknown field: {f}"}
                for f in exc.unknown
            ],
        )
    except EmptyRequestError:
        db.rollback()
        emit_workspace_settings_update_failure("missing_required_field")
        raise WorkspaceAPIError(
            status_code=422,
            code="empty_request",
            message="Request body must contain at least one settings field.",
        )
    except WorkspaceNotFoundError:
        db.rollback()
        emit_workspace_settings_update_failure("workspace_not_found")
        raise WorkspaceAPIError(
            status_code=404,
            code="workspace_not_found",
            message="Workspace not found or you do not have access.",
        )
    except WorkspaceArchivedError:
        db.rollback()
        emit_workspace_settings_update_failure("workspace_not_active")
        raise WorkspaceAPIError(
            status_code=422,
            code="workspace_not_active",
            message="Cannot update settings for an archived workspace.",
        )
    except WorkspaceAPIError:
        db.rollback()
        emit_workspace_settings_update_failure("validation_error")
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(
            "PATCH /workspaces/%s/settings unexpected error: %s",
            workspace_id,
            exc,
        )
        emit_workspace_settings_update_failure("internal_error")
        raise WorkspaceAPIError(
            status_code=500,
            code="internal_server_error",
            message="An unexpected error occurred.",
        )

    logger.debug(
        "PATCH /workspaces/%s/settings success: actor_id=%s role=%s",
        workspace_id,
        actor.actor_id,
        actor.actor_role,
    )

    return JSONResponse(
        status_code=200,
        content={"data": _serialize_workspace_settings(updated)},
    )


# ---------------------------------------------------------------------------
# GET /api/v1/workspaces/{workspace_id}/audit-logs — List Audit Logs (Packet 8)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/audit-logs", status_code=200)
async def list_audit_logs(
    request: Request,
    workspace_id: PythonUUID = Path(..., description="Workspace ID"),
    action_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    page: int = Query(default=1),
    page_size: int = Query(default=25),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("view_audit_logs")),
    service: WorkspaceService = Depends(get_workspace_service),
) -> JSONResponse:
    """
    List audit log entries for a workspace in reverse chronological order (TDD §4.8).

    Authorization:
        - Bearer JWT required
        - workspace_administrator: own workspace only; cross-tenant → 404
        - platform_admin / platform_viewer: any workspace in any Tenant
        - All other roles → HTTP 403

    Query Parameters:
        action_type (str): Filter by action_type; unrecognized → 422 invalid_filter_value
        actor_id (UUID): Filter by actor UUID; malformed → 400 invalid_parameter
        from_date (ISO 8601): Lower bound on occurred_at (inclusive); half-open range allowed
        to_date (ISO 8601): Upper bound on occurred_at (inclusive)
        from_date > to_date → 422 invalid_date_range
        page (int): 1-based (default: 1); < 1 → 422 validation_error
        page_size (int): 1–100 (default: 25); outside range → 422 validation_error

    Returns:
        HTTP 200 with {"data": [...], "meta": {"total", "page", "page_size", "has_next"}}

    Errors:
        401 - Missing/expired token
        403 - Role not permitted (not WA or Platform Operator)
        404 - Workspace not found or cross-tenant access attempt by WA
        422 / 400 - Invalid query parameter value
    """
    logger.info(
        "GET /workspaces/%s/audit-logs called: tenant_id=%s actor_id=%s role=%s",
        workspace_id,
        actor.tenant_id,
        actor.actor_id,
        actor.actor_role,
    )

    try:
        # Validate all query parameters
        validated_action_type, parsed_actor_id, parsed_from_date, parsed_to_date = (
            _validate_audit_log_params(
                action_type=action_type,
                actor_id_raw=actor_id,
                from_date_raw=from_date,
                to_date_raw=to_date,
                page=page,
                page_size=page_size,
            )
        )

        # Determine tenant scoping:
        # - WA: use actor's tenant_id for cross-tenant isolation
        # - Platform Operator: pass None (find_by_id_any_tenant + no tenant filter on audit logs)
        effective_tenant_id: PythonUUID | None = (
            None if actor.actor_role in PLATFORM_OPERATOR_ROLES else actor.tenant_id
        )

        entries, total = service.list_audit_logs(
            db=db,
            workspace_id=workspace_id,
            tenant_id=effective_tenant_id,
            action_type=validated_action_type,
            actor_id=parsed_actor_id,
            from_date=parsed_from_date,
            to_date=parsed_to_date,
            page=page,
            page_size=page_size,
        )

        has_next = (page * page_size) < total

        logger.info(
            "GET /workspaces/%s/audit-logs success: tenant_id=%s total=%s has_next=%s",
            workspace_id,
            actor.tenant_id,
            total,
            has_next,
        )

        return JSONResponse(
            status_code=200,
            content={
                "data": [_serialize_audit_log_entry(e) for e in entries],
                "meta": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "has_next": has_next,
                },
            },
        )

    except WorkspaceAPIError:
        raise

    except Exception as exc:
        logger.error(
            "GET /workspaces/%s/audit-logs failed: tenant_id=%s error=%s",
            workspace_id,
            actor.tenant_id,
            str(exc),
            exc_info=True,
        )
        raise map_service_exception_to_http(exc)


# ---------------------------------------------------------------------------
# F114 — Workspace Stats (Live Hub Dashboard)
# ---------------------------------------------------------------------------


@router.get("/{workspace_id}/stats")
async def get_workspace_stats(
    workspace_id: PythonUUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(verify_any_authenticated_actor),
):
    """Return entity counts for the workspace dashboard."""
    from sqlalchemy import text

    row = db.execute(
        text("""
            SELECT
                (SELECT COUNT(DISTINCT ds.data_source_id)
                 FROM control.data_sources ds
                 LEFT JOIN control.workspace_connection_assignments wca
                   ON wca.connection_id = ds.data_source_id
                 WHERE ds.status = 'active'
                   AND (ds.workspace_id = :wid OR wca.workspace_id = :wid)
                ) AS datasource_count,
                (SELECT COUNT(*) FROM control.metadata_term_index
                 WHERE workspace_id = :wid) AS glossary_count,
                (SELECT COUNT(*) FROM dq_flows
                 WHERE workspace_id = :wid) AS flow_count,
                (SELECT COUNT(*) FROM dq_rules
                 WHERE workspace_id = :wid) AS rule_count,
                (SELECT COUNT(*) FROM issues
                 WHERE workspace_id = :wid) AS issue_count,
                (SELECT COUNT(*) FROM control.datasets
                 WHERE workspace_id = :wid) AS dataset_count
        """),
        {"wid": str(workspace_id)},
    ).fetchone()

    return {
        "datasource_count": row.datasource_count if row else 0,
        "glossary_count": row.glossary_count if row else 0,
        "flow_count": row.flow_count if row else 0,
        "rule_count": row.rule_count if row else 0,
        "issue_count": row.issue_count if row else 0,
        "dataset_count": row.dataset_count if row else 0,
    }
