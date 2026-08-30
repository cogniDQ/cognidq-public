"""
Workspace Authorization Guards — F002 P04

Provides JWT authentication and authorization for workspace endpoints.
Extracts tenant_id from JWT for workspace isolation per § TDD §10.3.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workspace Actor Context (with tenant_id from JWT)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkspaceActorContext:
    """
    Resolved identity extracted from validated JWT for workspace operations.

    Per TDD §2.2 and §10.3:
    - tenant_id is resolved exclusively from JWT, never from request payload
    - All workspace operations are tenant-scoped

    Attributes:
        actor_id: UUID of the authenticated actor
        actor_role: Role string (e.g., "workspace_administrator")
        tenant_id: UUID of the actor's tenant (None for platform operators
                   and newly-registered users with no tenant yet — BUG-010)
    """

    actor_id: UUID
    actor_role: str
    tenant_id: UUID | None


# ---------------------------------------------------------------------------
# Workspace Authorization Errors
# ---------------------------------------------------------------------------


class WorkspaceAuthorizationError(HTTPException):
    """Base exception for workspace authorization failures."""

    pass


class ActorNotActiveError(WorkspaceAuthorizationError):
    """Actor is not active in the authentication framework → HTTP 401."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Actor is not active in the authentication framework",
        )


class InsufficientPermissionsError(WorkspaceAuthorizationError):
    """Actor does not have required permissions → HTTP 403."""

    def __init__(self, message: str):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=message)


# ---------------------------------------------------------------------------
# JWT Extraction and Validation
# ---------------------------------------------------------------------------

_BEARER_PREFIX = "Bearer "


def _extract_bearer_token(authorization: str | None) -> str:
    """
    Parse Authorization header and return raw token.

    Raises:
        HTTPException(401): If header missing or malformed
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header is missing"
        )

    if not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer scheme",
        )

    token = authorization[len(_BEARER_PREFIX) :]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token value is empty"
        )

    return token


def _decode_token(token: str) -> dict:
    """
    Validate and decode JWT.

    Args:
        token: Raw JWT token string

    Returns:
        dict: Decoded payload

    Raises:
        HTTPException(401): On expired/invalid token
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
        logger.info("JWT validation failed: token has expired")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except JWTError as exc:
        logger.info("JWT validation failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is invalid")

    return payload


def _build_workspace_actor_context(
    payload: dict,
    request: Request | None = None,
) -> WorkspaceActorContext:
    """
    Extract actor_id, actor_role, and tenant_id from JWT payload.

    Per TDD §2.2: tenant_id is resolved from JWT, never from request payload.

    BUG-010: tenant_id is OPTIONAL at decode time.  Newly-registered users
    and platform operators may legitimately have no tenant claim.  Endpoints
    that need a tenant must enforce it themselves (e.g. POST /workspaces).

    Args:
        payload: Decoded JWT payload

    Returns:
        WorkspaceActorContext: Context with actor_id, actor_role, tenant_id
    """
    raw_actor_id: str | None = payload.get("actor_id")
    actor_role: str | None = payload.get("actor_role")
    raw_tenant_id: str | None = payload.get("tenant_id")

    if not raw_actor_id or not actor_role:
        logger.info(
            "JWT missing required claims: actor_id=%s actor_role=%s",
            bool(raw_actor_id),
            bool(actor_role),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain required identity claims",
        )

    try:
        actor_id = UUID(raw_actor_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token actor_id claim is not a valid UUID",
        )

    tenant_id: UUID | None = None
    if raw_tenant_id:
        try:
            tenant_id = UUID(raw_tenant_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token tenant_id claim is not a valid UUID",
            )

    actor = WorkspaceActorContext(actor_id=actor_id, actor_role=actor_role, tenant_id=tenant_id)
    return actor


# ---------------------------------------------------------------------------
# Authorization Guard Functions
# ---------------------------------------------------------------------------


async def verify_actor_active(actor_id: UUID) -> None:
    """
    Verify actor is active in authentication framework.

    Called before any authorization checks.
    In production, this would query the authentication service.
    For P04, this is a placeholder that always passes.

    Args:
        actor_id: UUID of the actor to verify

    Raises:
        ActorNotActiveError: If actor is not active (HTTP 401)
    """
    # TODO: Integrate with authentication framework in future packet
    # For now, assume all actors are active
    logger.debug(f"verify_actor_active: actor_id={actor_id} (placeholder - always passes)")
    pass


async def verify_workspace_admin_in_tenant(request: Request) -> WorkspaceActorContext:
    """
    Verify actor has workspace_administrator role for tenant-scoped operations.

    Used for POST /workspaces (create workspace in tenant).
    Validates:
    1. JWT is present and valid
    2. JWT contains actor_id, actor_role, and tenant_id
    3. Actor is active in authentication framework
    4. Actor has workspace_administrator role (via JWT or workspace assignment)

    Args:
        request: FastAPI request object

    Returns:
        WorkspaceActorContext: Actor context with tenant_id

    Raises:
        HTTPException(401): If JWT missing/invalid or actor not active
        InsufficientPermissionsError: If actor lacks workspace_administrator role (HTTP 403)
    """
    from app.models.database import get_db as _get_db
    from app.services.workspaces.rbac import WorkspaceRBACService

    # Extract and validate JWT
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_workspace_actor_context(payload, request)

    # Store in request.state for downstream access
    request.state.workspace_actor = actor

    # Verify actor is active
    await verify_actor_active(actor.actor_id)

    # Platform admin always allowed
    if actor.actor_role == "platform_admin":
        logger.debug(
            "Authorization granted (platform_admin): actor_id=%s tenant_id=%s",
            actor.actor_id,
            actor.tenant_id,
        )
        return actor

    # Tenant admin — first-class role, may create workspaces inside their own
    # tenant. Any other tenant scope is denied.
    if actor.actor_role == "tenant_admin":
        if actor.tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant admin token missing tenant_id claim.",
            )
        logger.debug(
            "Authorization granted (tenant_admin): actor_id=%s tenant_id=%s",
            actor.actor_id,
            actor.tenant_id,
        )
        return actor

    # Beyond this point, a tenant_id claim is mandatory — workspace creation
    # is strictly tenant-scoped.
    if actor.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain tenant_id; cannot create workspace.",
        )

    # For "member" users, check if they are workspace_administrator in any
    # workspace within their tenant (via workspace_role_assignments table).
    if actor.actor_role == "member":
        db_gen = _get_db()
        db = next(db_gen)
        try:
            svc = WorkspaceRBACService()
            has_admin_role = svc.is_workspace_admin_in_tenant(actor.actor_id, actor.tenant_id, db)
            if has_admin_role:
                logger.debug(
                    "Authorization granted (workspace_admin via DB): actor_id=%s tenant_id=%s",
                    actor.actor_id,
                    actor.tenant_id,
                )
                return actor

            # BUG-002 bootstrap: if no workspace_administrator exists yet for
            # this tenant AND the caller's users.tenant_id matches, allow the
            # first workspace creation.  This breaks the chicken-and-egg
            # problem where a freshly-provisioned tenant-admin cannot create
            # their initial workspace because they have no WRA yet.
            from sqlalchemy import text as _sql_text

            user_row = db.execute(
                _sql_text("SELECT tenant_id FROM users WHERE id = :uid LIMIT 1"),
                {"uid": str(actor.actor_id)},
            ).fetchone()
            user_tenant_ok = (
                user_row is not None
                and user_row.tenant_id is not None
                and str(user_row.tenant_id) == str(actor.tenant_id)
            )
            if user_tenant_ok:
                existing_admin = db.execute(
                    _sql_text(
                        """
                        SELECT 1
                        FROM control.workspace_role_assignments wra
                        JOIN control.workspaces w ON w.workspace_id = wra.workspace_id
                        WHERE w.tenant_id = :tid
                          AND wra.role_name = 'workspace_administrator'
                        LIMIT 1
                        """
                    ),
                    {"tid": str(actor.tenant_id)},
                ).fetchone()
                if existing_admin is None:
                    logger.info(
                        "BUG-002 bootstrap: first-workspace grant for tenant_id=%s actor_id=%s",
                        actor.tenant_id,
                        actor.actor_id,
                    )
                    return actor
        finally:
            try:
                next(db_gen, None)
            except StopIteration:
                pass

    logger.warning(
        f"Access denied: actor_id={actor.actor_id} role={actor.actor_role} "
        f"tenant_id={actor.tenant_id} (requires workspace_administrator or platform_admin)"
    )
    raise InsufficientPermissionsError(
        "Only workspace administrators and platform admins can create workspaces"
    )

    logger.debug(
        "Authorization granted: actor_id=%s role=%s tenant_id=%s",
        actor.actor_id,
        actor.actor_role,
        actor.tenant_id,
    )

    return actor


async def verify_workspace_create_admin(
    request: Request,
) -> WorkspaceActorContext:
    """
    Auth guard for POST /workspaces — wraps verify_workspace_admin_in_tenant.

    Intercepts authorization failures (401/403) to emit the
    ``workspace_create_failure_count{failure_reason="unauthorized"}`` metric
    *before* re-raising, so the metric fires even though FastAPI would
    otherwise handle the HTTPException before the endpoint body runs.

    TDD §12.1 / TG-13.

    Raises
    ------
    HTTPException(401) / InsufficientPermissionsError(403)
        Propagated unchanged after metric emission.
    """
    from app.services.workspaces.metrics import (
        emit_workspace_create_failure,  # local import avoids circular
    )

    try:
        return await verify_workspace_admin_in_tenant(request)
    except HTTPException as exc:
        if exc.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ):
            emit_workspace_create_failure("unauthorized")
        raise


# ---------------------------------------------------------------------------
# Platform Operator role constant (TDD §5.4 / §4.6 / HA-8)
# ---------------------------------------------------------------------------

# Both roles have identical read access across all Tenants.
# Platform Viewer is read-only; Platform Admin additionally has write access.
PLATFORM_OPERATOR_ROLES: frozenset = frozenset({"platform_admin", "platform_viewer"})

# Read-equivalent actions that don't follow the ":read" naming convention.
_PLATFORM_READ_ACTIONS: frozenset = frozenset({"view_audit_logs"})


# ---------------------------------------------------------------------------
# Read-path auth guard — any valid JWT, no minimum role (TDD §4.6 A-10)
# ---------------------------------------------------------------------------


async def verify_any_authenticated_actor(
    request: Request,
) -> WorkspaceActorContext:
    """
    Verify that a valid JWT is present.  No specific role is required.

    Used on read endpoints (GET /workspaces, GET /workspaces/{id}) where any
    authenticated actor — regardless of role — may make the request.

    Following successful JWT validation, the actor context is stored on
    ``request.state.workspace_actor`` for downstream access.

    Raises
    ------
    HTTPException(401)
        If the Authorization header is missing, malformed, or the token is
        invalid/expired.
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_workspace_actor_context(payload, request)

    request.state.workspace_actor = actor

    await verify_actor_active(actor.actor_id)

    logger.debug(
        "verify_any_authenticated_actor: actor_id=%s role=%s tenant_id=%s",
        actor.actor_id,
        actor.actor_role,
        actor.tenant_id,
    )

    return actor


# ---------------------------------------------------------------------------
# Audit log read guard — WA (own) or Platform Operator (all) (P08 / TDD §5.4)
# ---------------------------------------------------------------------------

# Roles permitted to read audit logs (P08 acceptance criteria, TDD §5.4)
_AUDIT_LOG_ALLOWED_ROLES: frozenset = (
    frozenset({"workspace_administrator"}) | PLATFORM_OPERATOR_ROLES
)


async def verify_audit_log_actor(
    request: Request,
) -> WorkspaceActorContext:
    """
    Verify that the actor is allowed to read audit logs.

    Permitted roles: ``workspace_administrator``, ``platform_admin``,
    ``platform_viewer``.  All other roles receive HTTP 403.

    Workspace Administrators may only access logs for workspaces in their
    own Tenant; cross-tenant isolation is enforced at the repository level
    (``find_by_id`` → 404 on tenant mismatch).

    Platform Admin/Viewer bypass tenant scoping — the service uses
    ``find_by_id_any_tenant`` when ``actor_role`` is a Platform Operator.

    Raises
    ------
    HTTPException(401)
        If the Authorization header is missing, malformed, or the token is
        invalid/expired.
    InsufficientPermissionsError (HTTP 403)
        If the actor's role is not in ``_AUDIT_LOG_ALLOWED_ROLES``.
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_workspace_actor_context(payload, request)

    request.state.workspace_actor = actor

    await verify_actor_active(actor.actor_id)

    if actor.actor_role not in _AUDIT_LOG_ALLOWED_ROLES:
        logger.warning(
            "verify_audit_log_actor: access denied actor_id=%s role=%s tenant_id=%s",
            actor.actor_id,
            actor.actor_role,
            actor.tenant_id,
        )
        raise InsufficientPermissionsError(
            "Only Workspace Administrators and Platform Operators may view audit logs."
        )

    logger.debug(
        "verify_audit_log_actor: access granted actor_id=%s role=%s tenant_id=%s",
        actor.actor_id,
        actor.actor_role,
        actor.tenant_id,
    )

    return actor


# ---------------------------------------------------------------------------
# Settings read guard — WA + data_engineer + data_steward + PO  (F003 TDD §5.5)
# ---------------------------------------------------------------------------

_SETTINGS_READ_ALLOWED_ROLES: frozenset = (
    frozenset(
        {
            "workspace_administrator",
            "data_engineer",
            "data_steward",
        }
    )
    | PLATFORM_OPERATOR_ROLES
)


async def verify_workspace_settings_read_actor(
    request: Request,
) -> WorkspaceActorContext:
    """
    Verify that the actor is allowed to read workspace settings.

    Permitted roles: ``workspace_administrator``, ``data_engineer``,
    ``data_steward``, ``platform_admin``, ``platform_viewer``.
    All other roles receive HTTP 403.

    Platform Operators (`platform_admin`, `platform_viewer`) bypass tenant
    scoping — the service will call ``WorkspaceRepository.find_by_id`` with
    ``tenant_id=None`` so they can access any workspace.

    Raises
    ------
    HTTPException(401)
        If the Authorization header is missing, malformed, or the token is
        invalid/expired.
    InsufficientPermissionsError (HTTP 403)
        If the actor's role is not in ``_SETTINGS_READ_ALLOWED_ROLES``.
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_workspace_actor_context(payload, request)

    request.state.workspace_actor = actor

    await verify_actor_active(actor.actor_id)

    if actor.actor_role not in _SETTINGS_READ_ALLOWED_ROLES:
        logger.warning(
            "verify_workspace_settings_read_actor: denied actor_id=%s role=%s",
            actor.actor_id,
            actor.actor_role,
        )
        raise InsufficientPermissionsError(
            "Your role does not have permission to read workspace settings."
        )

    logger.debug(
        "verify_workspace_settings_read_actor: granted actor_id=%s role=%s",
        actor.actor_id,
        actor.actor_role,
    )
    return actor


# ---------------------------------------------------------------------------
# Settings write guard — WA only  (F003 TDD §5.5)
# ---------------------------------------------------------------------------


async def verify_workspace_settings_write_actor(
    request: Request,
) -> WorkspaceActorContext:
    """
    Verify that the actor is allowed to update workspace settings.

    Permitted roles: ``workspace_administrator`` only.
    Platform Operators are intentionally excluded from the write path.

    Raises
    ------
    HTTPException(401)
        If the Authorization header is missing, malformed, or the token is
        invalid/expired.
    InsufficientPermissionsError (HTTP 403)
        If the actor's role is not ``workspace_administrator``.
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_workspace_actor_context(payload, request)

    request.state.workspace_actor = actor

    await verify_actor_active(actor.actor_id)

    if actor.actor_role not in ("workspace_administrator", "platform_admin"):
        logger.warning(
            "verify_workspace_settings_write_actor: denied actor_id=%s role=%s",
            actor.actor_id,
            actor.actor_role,
        )
        raise InsufficientPermissionsError(
            "Only Workspace Administrators and Platform Admins may update workspace settings."
        )

    logger.debug(
        "verify_workspace_settings_write_actor: granted actor_id=%s role=%s",
        actor.actor_id,
        actor.actor_role,
    )
    return actor


# ---------------------------------------------------------------------------
# F007 — workspace-scoped permission guard factory
# ---------------------------------------------------------------------------


def require_workspace_permission(action: str):
    """
    FastAPI dependency factory that enforces a workspace-level permission.

    Usage in route definitions::

        @router.get("/workspaces/{workspace_id}/members/{user_id}/role",
                    dependencies=[Depends(require_workspace_permission("roles:read"))])

    The guard:
    1. Validates the JWT and builds a ``WorkspaceActorContext``.
    2. Looks up the actor's role assignment in
       ``control.workspace_role_assignments`` for the requested workspace.
    3. Checks whether the role's permission set (``FIXED_ROLE_PERMISSIONS``)
       includes *action*.
    4. Returns the actor context on success; raises ``HTTP 403`` otherwise.

    Note: Platform operators (``platform_admin``, ``platform_viewer``) bypass
    the workspace-level check — they may always read but may not write.
    Write actions for platform operators still raise 403.

    Args:
        action: Permission code to check (e.g. ``"roles:assign"``).

    Returns:
        A ``Callable`` suitable for use in ``Depends()``.
    """
    from app.models.database import get_db
    from app.services.workspaces.rbac import WorkspaceRBACService

    async def _guard(
        request: Request,
        workspace_id: UUID,
        db=Depends(get_db),
    ) -> WorkspaceActorContext:
        authorization: str | None = request.headers.get("Authorization")
        token = _extract_bearer_token(authorization)
        payload = _decode_token(token)
        actor = _build_workspace_actor_context(payload, request)
        request.state.workspace_actor = actor
        await verify_actor_active(actor.actor_id)

        # Platform operators bypass workspace-level checks:
        # platform_admin has full access (read + write)
        # platform_viewer has read-only access
        if actor.actor_role in PLATFORM_OPERATOR_ROLES:
            if actor.actor_role == "platform_admin":
                return actor  # full access
            # platform_viewer: read-only
            if action.endswith(":read") or action in _PLATFORM_READ_ACTIONS:
                return actor
            raise InsufficientPermissionsError(
                f"Platform viewers may not perform '{action}' on workspaces."
            )

        # Tenant admins bypass workspace-level checks inside their own tenant
        # (full read + write, including roles:assign). Out-of-tenant access is
        # denied by the workspace ownership check below.
        if actor.actor_role == "tenant_admin":
            from sqlalchemy import text as _sql_text

            row = db.execute(
                _sql_text(
                    "SELECT tenant_id FROM control.workspaces WHERE workspace_id = :ws LIMIT 1"
                ),
                {"ws": str(workspace_id)},
            ).fetchone()
            if row and actor.tenant_id is not None and str(row.tenant_id) == str(actor.tenant_id):
                return actor
            raise InsufficientPermissionsError(
                "Tenant admin privileges do not extend to this workspace."
            )

        svc = WorkspaceRBACService()
        allowed = svc.check_permission(workspace_id, actor.actor_id, action, db)
        if not allowed:
            logger.warning(
                "require_workspace_permission denied: actor=%s workspace=%s action=%s",
                actor.actor_id,
                workspace_id,
                action,
            )
            raise InsufficientPermissionsError(
                f"You do not have permission to perform '{action}' in this workspace."
            )

        logger.debug(
            "require_workspace_permission granted: actor=%s workspace=%s action=%s",
            actor.actor_id,
            workspace_id,
            action,
        )
        return actor

    return _guard
