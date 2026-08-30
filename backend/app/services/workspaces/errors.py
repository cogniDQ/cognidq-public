"""
Workspace Error Formatting — F002 P04

Maps workspace service exceptions to HTTP error responses.
Error shape per TDD §4.9: {"error": {"code": str, "message": str, "fields": list | null}}
"""

import logging
from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse

from app.api.v1.dependencies.workspace_auth import (
    ActorNotActiveError,
    InsufficientPermissionsError,
)
from app.services.workspaces.exceptions import (
    AuditWriteFailedError,
    DuplicateNameError,
    DuplicateSlugError,
    ForbiddenTransitionError,
    LastActiveWorkspaceError,
    RoleGrantFailedError,
    TenantNotActiveError,
    TenantNotFoundError,
    WorkspaceArchivedError,
    WorkspaceError,
    WorkspaceNotFoundError,
    WorkspaceValidationError,
)

logger = logging.getLogger(__name__)


class WorkspaceAPIError(Exception):
    """
    Structured error for workspace endpoints.

    Follows TDD §4.9 error envelope:
        {"error": {"code": str, "message": str, "fields": list | null}}
    """

    def __init__(
        self, status_code: int, code: str, message: str, fields: list[dict[str, Any]] | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


async def workspace_api_error_handler(request, exc: WorkspaceAPIError) -> JSONResponse:
    """
    FastAPI exception handler for WorkspaceAPIError.

    Formats error response per TDD §4.9.
    Stores error_code on request.state for structured logging.
    """
    try:
        request.state.error_code = exc.code
    except Exception:
        pass

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "fields": exc.fields}},
    )


def map_service_exception_to_http(exc: Exception) -> WorkspaceAPIError:
    """
    Map service layer exceptions to HTTP error responses.

    Per TDD §4.2 status codes table and §4.9 error shape.

    Args:
        exc: Exception from service layer

    Returns:
        WorkspaceAPIError: Structured error ready for HTTP response
    """
    # Authorization errors → HTTP 401/403
    if isinstance(exc, ActorNotActiveError):
        return WorkspaceAPIError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="actor_not_active",
            message="Actor is not active in the authentication framework",
        )

    if isinstance(exc, InsufficientPermissionsError):
        return WorkspaceAPIError(
            status_code=status.HTTP_403_FORBIDDEN, code="insufficient_permissions", message=str(exc)
        )

    # Not found → HTTP 404
    if isinstance(exc, WorkspaceNotFoundError):
        return WorkspaceAPIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="workspace_not_found",
            message="Workspace not found or you do not have access",
        )

    if isinstance(exc, TenantNotFoundError):
        # Should not happen in normal flow (JWT has valid tenant_id)
        # But handle defensively
        return WorkspaceAPIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="tenant_not_found",
            message="Tenant not found",
        )

    # Validation errors → HTTP 422
    if isinstance(exc, TenantNotActiveError):
        return WorkspaceAPIError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="tenant_not_active",
            message="Tenant is not active. Only active tenants can create workspaces.",
        )

    if isinstance(exc, DuplicateNameError):
        return WorkspaceAPIError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="duplicate_name",
            message="A workspace with this name already exists in your tenant",
            fields=[
                {
                    "field": "workspace_name",
                    "error_code": "duplicate_name",
                    "message": "Workspace name must be unique within tenant",
                }
            ],
        )

    if isinstance(exc, DuplicateSlugError):
        return WorkspaceAPIError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="duplicate_slug",
            message="A workspace with this slug already exists in your tenant",
            fields=[
                {
                    "field": "workspace_slug",
                    "error_code": "duplicate_slug",
                    "message": "Workspace slug must be unique within tenant",
                }
            ],
        )

    if isinstance(exc, WorkspaceArchivedError):
        return WorkspaceAPIError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="workspace_archived",
            message="Cannot update an archived workspace. Restore it first.",
        )

    if isinstance(exc, ForbiddenTransitionError):
        return WorkspaceAPIError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="forbidden_transition",
            message=str(exc)
            or "This status transition is not permitted in the current workspace state.",
        )

    if isinstance(exc, LastActiveWorkspaceError):
        return WorkspaceAPIError(
            status_code=status.HTTP_409_CONFLICT,
            code="last_active_workspace",
            message=(
                "This is the last active workspace in the tenant. "
                "To archive it, resend the request with confirm_last_workspace: true."
            ),
        )

    if isinstance(exc, WorkspaceValidationError):
        return format_validation_errors(exc.validation_errors)

    # Internal errors → HTTP 500
    if isinstance(exc, RoleGrantFailedError):
        logger.error(f"Role grant failed: {exc}", exc_info=True)
        return WorkspaceAPIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="role_grant_failed",
            message="Failed to grant workspace administrator role",
        )

    if isinstance(exc, AuditWriteFailedError):
        logger.error(f"Audit write failed: {exc}", exc_info=True)
        return WorkspaceAPIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="audit_write_failed",
            message="Failed to write audit log entry",
        )

    # Generic workspace error → HTTP 500
    if isinstance(exc, WorkspaceError):
        logger.error(f"Workspace service error: {exc}", exc_info=True)
        return WorkspaceAPIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="workspace_error",
            message="An error occurred processing the workspace operation",
        )

    # Unknown exception → HTTP 500
    logger.error(f"Unexpected error in workspace operation: {exc}", exc_info=True)
    return WorkspaceAPIError(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message="An unexpected error occurred",
    )


def format_validation_errors(errors: list[dict[str, Any]]) -> WorkspaceAPIError:
    """
    Format validation errors from P3 validation layer into HTTP 422 response.

    Args:
        errors: List of validation errors from ValidationResult

    Returns:
        WorkspaceAPIError: HTTP 422 response with fields array
    """
    return WorkspaceAPIError(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="validation_error",
        message="Request validation failed",
        fields=errors,
    )
