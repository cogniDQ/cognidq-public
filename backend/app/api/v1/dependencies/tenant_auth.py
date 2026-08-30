"""
F001 — Authentication and Authorization Infrastructure
======================================================

Provides the security layer for every F001 (/api/v1/tenants) endpoint.

Components
----------
TenantAPIError
    Custom exception carrying a machine-readable ``code`` and optional
    ``fields`` list.  The registered handler ``tenant_api_error_handler``
    serialises it as:
        {"error": {"code": str, "message": str, "fields": [...] | null}}

ActorContext
    Frozen dataclass holding the resolved ``actor_id`` (UUID) and
    ``actor_role`` (str) extracted from a validated JWT.

get_actor_context(request) -> ActorContext
    FastAPI dependency that validates the Bearer JWT and returns an
    ActorContext.  It also writes the context to ``request.state.actor``
    so the service layer and audit log writer can access it without
    threading it through every function parameter.

require_write_access() -> dependency
    Guard factory: only ``platform_admin`` passes.

require_read_access() -> dependency
    Guard factory: ``platform_admin`` and ``platform_viewer`` pass.

validate_uuid_path_param(value, param_name) -> UUID
    Reusable UUID v4 validator for path parameters.

Security notes
--------------
* The JWT token value is **never** written to logs.
* Issuer validation is performed when ``settings.JWT_ISSUER`` is set.
* UUID v1/v3/v5 path parameters are rejected (version nibble must be 4).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# UUID v4 pattern
# ---------------------------------------------------------------------------
# Enforces:
#   • 8-4-4-4-12 hex format
#   • Third block starts with '4'  → UUID version 4
#   • Fourth block starts with 8/9/a/b → RFC 4122 variant
# UUID v1/v3/v5 and any non-UUID string are rejected.
_UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Error envelope
# ---------------------------------------------------------------------------


class TenantAPIError(Exception):
    """
    Raised by any F001 dependency or endpoint when a request must be rejected
    with a structured error response.

    The companion handler ``tenant_api_error_handler`` converts this into:
        HTTP <status_code>
        {"error": {"code": ..., "message": ..., "fields": ...}}
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: list | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields


async def tenant_api_error_handler(
    request: Request,
    exc: TenantAPIError,
) -> JSONResponse:
    """FastAPI exception handler registered in ``app.main``.

    Side-effect: stores ``exc.code`` on ``request.state.error_code`` so that
    the ``CorrelationIdMiddleware`` can include the error code in the
    structured request log (TDD §8.2) without re-parsing the response body.
    """
    try:
        request.state.error_code = exc.code
    except Exception:  # pragma: no cover
        pass
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "fields": exc.fields,
            }
        },
    )


# ---------------------------------------------------------------------------
# Actor context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActorContext:
    """Resolved identity extracted from a validated JWT.

    Attributes:
        actor_id:   UUID of the authenticated actor.
        actor_role: Role string at the time the token was issued, e.g.
                    ``"platform_admin"``, ``"tenant_admin"`` or ``"platform_viewer"``.
        tenant_id:  Optional tenant owning the actor (from JWT ``tenant_id``
                    claim). ``None`` for platform operators without a tenant.
    """

    actor_id: UUID
    actor_role: str
    tenant_id: UUID | None = None


# ---------------------------------------------------------------------------
# JWT validation helpers (private)
# ---------------------------------------------------------------------------

_BEARER_PREFIX = "Bearer "


def _extract_bearer_token(authorization: str | None) -> str:
    """Parse the ``Authorization`` header and return the raw token string.

    Raises:
        TenantAPIError(401): if the header is absent, empty, or does not use
            the ``Bearer`` scheme.
    """
    if not authorization:
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Authorization header is missing.",
        )

    if not authorization.startswith(_BEARER_PREFIX):
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Authorization header must use the Bearer scheme.",
        )

    token = authorization[len(_BEARER_PREFIX) :]
    if not token:
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Bearer token value is empty.",
        )

    return token


def _decode_token(token: str) -> dict:
    """Validate and decode the JWT.

    Validates signature and expiry unconditionally; validates issuer only
    when ``settings.JWT_ISSUER`` is configured.

    SECURITY: ``token`` is never written to any log statement.

    Raises:
        TenantAPIError(401): on expired token, invalid signature, or any
            other JWT error.
    """
    issuer: str | None = getattr(settings, "JWT_ISSUER", None)
    decode_kwargs: dict = {}
    if issuer:
        decode_kwargs["issuer"] = issuer

    try:
        payload: dict = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            **decode_kwargs,
        )
    except ExpiredSignatureError:
        logger.info("JWT validation failed: token has expired.")
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Token has expired.",
        )
    except JWTError as exc:
        logger.info("JWT validation failed: %s", type(exc).__name__)
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Token is invalid.",
        )

    return payload


def _build_actor_context(payload: dict) -> ActorContext:
    """Extract ``actor_id`` and ``actor_role`` from the decoded JWT payload.

    Raises:
        TenantAPIError(401): if either required claim is absent or
            ``actor_id`` is not a valid UUID.
    """
    raw_actor_id: str | None = payload.get("actor_id")
    actor_role: str | None = payload.get("actor_role")

    if not raw_actor_id or not actor_role:
        logger.info(
            "JWT missing required claims: actor_id_present=%s  actor_role_present=%s",
            bool(raw_actor_id),
            bool(actor_role),
        )
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Token does not contain required identity claims.",
        )

    try:
        actor_id = UUID(raw_actor_id)
    except ValueError:
        raise TenantAPIError(
            status_code=401,
            code="unauthorized",
            message="Token actor_id claim is not a valid UUID.",
        )

    raw_tenant_id = payload.get("tenant_id")
    tenant_id: UUID | None = None
    if raw_tenant_id:
        try:
            tenant_id = UUID(str(raw_tenant_id))
        except ValueError:
            # Non-fatal: fall through with tenant_id=None; downstream guards
            # will reject as needed.
            tenant_id = None

    return ActorContext(actor_id=actor_id, actor_role=actor_role, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# JWT validation dependency (public)
# ---------------------------------------------------------------------------


async def get_actor_context(request: Request) -> ActorContext:
    """FastAPI dependency: validates the Bearer JWT and returns an ActorContext.

    Side-effect: writes the resolved ``ActorContext`` to ``request.state.actor``
    so the service layer and audit log writer can access it without threading
    the actor through every function signature.

    Raises:
        TenantAPIError(401): on any authentication failure.
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    # Expose to downstream call stack (service layer, audit writer).
    request.state.actor = actor

    return actor


# ---------------------------------------------------------------------------
# Role-based authorization guards (public)
# ---------------------------------------------------------------------------

_WRITE_ALLOWED = frozenset({"platform_admin"})
_READ_ALLOWED = frozenset({"platform_admin", "platform_viewer"})


def require_write_access() -> Callable[..., Coroutine]:
    """Factory returning a FastAPI dependency that permits only platform_admin.

    ``platform_viewer``, ``customer_actor``, and any unrecognised role
    receive HTTP 403.

    Usage::

        @router.post("/tenants")
        async def create_tenant(actor: ActorContext = Depends(require_write_access())):
            ...
    """

    async def _guard(
        actor: ActorContext = Depends(get_actor_context),
    ) -> ActorContext:
        if actor.actor_role not in _WRITE_ALLOWED:
            raise TenantAPIError(
                status_code=403,
                code="forbidden",
                message="This operation requires platform_admin role.",
            )
        return actor

    return _guard


def require_read_access() -> Callable[..., Coroutine]:
    """Factory returning a FastAPI dependency that permits platform_admin and
    platform_viewer.

    ``customer_actor`` and any unrecognised role receive HTTP 403.

    Usage::

        @router.get("/tenants")
        async def list_tenants(actor: ActorContext = Depends(require_read_access())):
            ...
    """

    async def _guard(
        actor: ActorContext = Depends(get_actor_context),
    ) -> ActorContext:
        if actor.actor_role not in _READ_ALLOWED:
            raise TenantAPIError(
                status_code=403,
                code="forbidden",
                message="Insufficient role to access this resource.",
            )
        return actor

    return _guard


def validate_uuid_path_param(value: str, param_name: str = "id") -> UUID:
    """Validate that ``value`` is a well-formed UUID v4 string.

    Accepts both upper- and lower-case hex; returns the parsed ``UUID``
    object (which normalises to lowercase internally).

    UUID version decision: UUID v1, v3, and v5 are **rejected**.  The version
    nibble must be ``4``.  This decision is consistent across every F001 path
    parameter.

    Args:
        value:      Raw path-parameter string extracted from the URL.
        param_name: Human-readable parameter name used in the error message.

    Raises:
        TenantAPIError(400, "invalid_path_parameter"): if ``value`` is empty,
            not a UUID, or is a UUID of the wrong version.
    """
    if not value or not _UUID_V4_RE.match(value):
        raise TenantAPIError(
            status_code=400,
            code="invalid_path_parameter",
            message=f"Path parameter '{param_name}' must be a valid UUID v4.",
        )
    return UUID(value)


# ---------------------------------------------------------------------------
# Tenant-scoped authorization guards (BUG-006/007)
# ---------------------------------------------------------------------------
#
# The original F001 read/write guards only recognise platform-operator roles.
# Tenant admins — regular users whose ``users.tenant_id`` matches the path
# parameter AND who hold ``workspace_administrator`` in that tenant — must
# also be able to read/write their own tenant's resources.
#
# The guards below perform that broader check.  They run AFTER
# get_actor_context, so the Bearer-token validation already succeeded by the
# time this code runs.


def _is_tenant_admin(
    tenant_id: UUID,
    actor: ActorContext,
    db,  # type: ignore[name-defined]
) -> bool:
    """True iff the actor is a tenant admin for ``tenant_id``.

    Two paths grant tenant-admin status:
      1. First-class role: ``actor.actor_role == 'tenant_admin'`` AND the
         actor's JWT tenant_id matches the path param.
      2. Derived: any user whose ``users.tenant_id`` matches the path param
         AND who holds a ``workspace_administrator`` grant in a workspace of
         that tenant.
    """
    from sqlalchemy import text as _sql_text  # local import to avoid cycle

    # Path 1 — first-class tenant_admin role
    if getattr(actor, "actor_role", None) == "tenant_admin":
        actor_tid = getattr(actor, "tenant_id", None)
        if actor_tid is not None and str(actor_tid) == str(tenant_id):
            return True

    row = db.execute(
        _sql_text(
            """
            SELECT 1
            FROM users u
            JOIN control.workspace_role_assignments wra ON wra.user_id = u.id
            JOIN control.workspaces w ON w.workspace_id = wra.workspace_id
            WHERE u.id = :user_id
              AND u.tenant_id = :tenant_id
              AND w.tenant_id = :tenant_id
              AND wra.role_name = 'workspace_administrator'
            LIMIT 1
            """
        ),
        {"user_id": str(actor.actor_id), "tenant_id": str(tenant_id)},
    ).fetchone()
    return row is not None


def require_tenant_read_access() -> Callable[..., Coroutine]:
    """Guard: allow platform_admin, platform_viewer, or tenant-admin-of-path.

    The caller endpoint MUST declare ``tenant_id: str`` as a path parameter.
    """
    from app.models.database import get_db  # local to avoid cycle

    async def _guard(
        tenant_id: str,
        actor: ActorContext = Depends(get_actor_context),
        db=Depends(get_db),
    ) -> ActorContext:
        if actor.actor_role in _READ_ALLOWED:
            return actor
        validated = validate_uuid_path_param(tenant_id, "tenant_id")
        if _is_tenant_admin(validated, actor, db):
            return actor
        raise TenantAPIError(
            status_code=403,
            code="forbidden",
            message="Insufficient role to access this resource.",
        )

    return _guard


def require_tenant_write_access() -> Callable[..., Coroutine]:
    """Guard: allow platform_admin or tenant-admin-of-path."""
    from app.models.database import get_db  # local to avoid cycle

    async def _guard(
        tenant_id: str,
        actor: ActorContext = Depends(get_actor_context),
        db=Depends(get_db),
    ) -> ActorContext:
        if actor.actor_role in _WRITE_ALLOWED:
            return actor
        validated = validate_uuid_path_param(tenant_id, "tenant_id")
        if _is_tenant_admin(validated, actor, db):
            return actor
        raise TenantAPIError(
            status_code=403,
            code="forbidden",
            message="This operation requires tenant admin privileges.",
        )

    return _guard


def _is_workspace_member_of_tenant(
    tenant_id: UUID,
    actor: ActorContext,
    db,  # type: ignore[name-defined]
) -> bool:
    """True iff the actor holds any workspace role assignment in ``tenant_id``.

    Used to allow workspace-scoped read access to tenant resources
    (e.g. listing connections from inside a workspace) without granting
    tenant-admin privileges.
    """
    from sqlalchemy import text as _sql_text  # local import to avoid cycle

    row = db.execute(
        _sql_text(
            """
            SELECT 1
            FROM control.workspace_role_assignments wra
            JOIN control.workspaces w ON w.workspace_id = wra.workspace_id
            WHERE wra.user_id = :user_id
              AND w.tenant_id = :tenant_id
            LIMIT 1
            """
        ),
        {"user_id": str(actor.actor_id), "tenant_id": str(tenant_id)},
    ).fetchone()
    return row is not None


def require_tenant_member_read_access() -> Callable[..., Coroutine]:
    """Read guard that also accepts workspace members of the tenant.

    Permits, in order:
      1. Platform operators (``platform_admin``, ``platform_viewer``).
      2. First-class or derived tenant admins (see :func:`_is_tenant_admin`).
      3. Any user with at least one workspace role assignment in a workspace
         that belongs to ``tenant_id`` (read-only audience for tenant
         resources surfaced inside a workspace).

    Use this on read-only endpoints under ``/tenants/{tenant_id}/...`` that
    must be reachable from a workspace context (e.g. listing the connections
    available to a workspace).
    """
    from app.models.database import get_db  # local to avoid cycle

    async def _guard(
        tenant_id: str,
        actor: ActorContext = Depends(get_actor_context),
        db=Depends(get_db),
    ) -> ActorContext:
        if actor.actor_role in _READ_ALLOWED:
            return actor
        validated = validate_uuid_path_param(tenant_id, "tenant_id")
        if _is_tenant_admin(validated, actor, db):
            return actor
        if _is_workspace_member_of_tenant(validated, actor, db):
            return actor
        raise TenantAPIError(
            status_code=403,
            code="forbidden",
            message="Insufficient role to access this resource.",
        )

    return _guard
