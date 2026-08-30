"""
F004 — Data Source Authorization Guards
=========================================

Provides JWT authentication and RBAC for data source endpoints.
Follows the same pattern as workspace_auth.py (F002 P04).

Roles (canonical workspace roles, see ``services/workspaces/rbac.py``):
  Write: workspace_administrator, data_engineer
         + platform_admin (always allowed)
  Read:  workspace_administrator, data_engineer, data_steward,
         governance_viewer
         + platform_admin / platform_viewer (always allowed)

Legacy role aliases (``workspace_steward``, ``workspace_viewer``,
``platform_operator``) are accepted in addition to the canonical names
so older integration fixtures and tokens still authenticate. New code
should rely on the canonical roles only.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request, status
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role constants
# ---------------------------------------------------------------------------

DATA_SOURCE_WRITE_ROLES: frozenset = frozenset(
    {
        # canonical workspace roles with datasources:write
        "workspace_administrator",
        "data_engineer",
        # tenant-level admins manage data sources for all workspaces in
        # their tenant (matches the F-CONN-RBAC tenant-admin lockdown).
        "tenant_admin",
        # platform operators (admin-only for write)
        "platform_admin",
        # legacy aliases
        "workspace_steward",
    }
)
DATA_SOURCE_READ_ROLES: frozenset = frozenset(
    {
        # canonical workspace roles with datasources:read
        "workspace_administrator",
        "data_engineer",
        "data_steward",
        "business_analyst",
        "governance_viewer",
        # tenant-level roles
        "tenant_admin",
        "member",
        # platform operators
        "platform_admin",
        "platform_viewer",
        # legacy aliases
        "workspace_steward",
        "workspace_viewer",
        "platform_operator",
    }
)


# ---------------------------------------------------------------------------
# Actor context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataSourceActorContext:
    """Resolved identity extracted from JWT for data source operations."""

    actor_id: UUID
    actor_role: str
    tenant_id: UUID | None


# Roles whose tokens may legitimately omit ``tenant_id``.
_TENANT_OPTIONAL_ROLES: frozenset = frozenset(
    {
        "platform_admin",
        "platform_viewer",
    }
)


# ---------------------------------------------------------------------------
# Internal helpers (shared with workspace_auth.py logic)
# ---------------------------------------------------------------------------

_BEARER_PREFIX = "Bearer "


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )
    if not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must use Bearer scheme",
        )
    token = authorization[len(_BEARER_PREFIX) :]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token value is empty",
        )
    return token


def _decode_token(token: str) -> dict:
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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid",
        )
    return payload


def _build_actor_context(payload: dict) -> DataSourceActorContext:
    raw_actor_id: str | None = payload.get("actor_id")
    actor_role: str | None = payload.get("actor_role")
    raw_tenant_id: str | None = payload.get("tenant_id")

    if not raw_actor_id or not actor_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain required identity claims",
        )
    # Platform-scoped roles may omit tenant_id (they aren't bound to a tenant).
    if not raw_tenant_id and actor_role not in _TENANT_OPTIONAL_ROLES:
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
    return DataSourceActorContext(
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency functions
# ---------------------------------------------------------------------------


async def verify_data_source_write_actor(request: Request) -> DataSourceActorContext:
    """
    Dependency: actor must carry a DATA_SOURCE_WRITE_ROLES role.

    When ``settings.WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY`` is True
    (F-CONN-RBAC projection lockdown), the actor must additionally be a
    tenant admin for the path workspace's tenant. The tenant-admin check
    runs in :func:`enforce_data_source_tenant_admin_lockdown` because it
    needs the path ``workspace_id`` and a DB session, which this
    Request-only dependency cannot resolve.

    Raises:
        HTTPException(401): missing / invalid token
        HTTPException(403): insufficient role
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    if actor.actor_role not in DATA_SOURCE_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{actor.actor_role}' is not authorised to modify data sources. "
                f"Required: {sorted(DATA_SOURCE_WRITE_ROLES)}"
            ),
        )
    return actor


async def verify_data_source_read_actor(request: Request) -> DataSourceActorContext:
    """
    Dependency: actor must carry a DATA_SOURCE_READ_ROLES role.

    Raises:
        HTTPException(401): missing / invalid token
        HTTPException(403): insufficient role
    """
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    if actor.actor_role not in DATA_SOURCE_READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{actor.actor_role}' is not authorised to read data sources. "
                f"Required: {sorted(DATA_SOURCE_READ_ROLES)}"
            ),
        )
    return actor


# ---------------------------------------------------------------------------
# F-CONN-RBAC — Workspace data-source projection lockdown (spec §15.2)
# ---------------------------------------------------------------------------


def enforce_data_source_tenant_admin_lockdown(
    workspace_id: UUID,
    actor: DataSourceActorContext,
    db,
) -> None:
    """Enforce the F-CONN-RBAC projection lockdown for write operations.

    When ``settings.WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY`` is False
    (default), this is a no-op — the legacy F004 RBAC remains in effect.

    When the flag is True (production posture per the
    ``connections_datasets`` plan), only tenant admins for the workspace's
    tenant may write. ``platform_admin`` continues to pass.

    Endpoint contract: call this immediately after the
    :func:`verify_data_source_write_actor` dependency has produced an
    ``actor`` and the workspace_id path parameter is known.

    Raises:
        HTTPException(403): RBAC_FORBIDDEN — projection lockdown active
            and actor is not a tenant admin for the path workspace's tenant.
        HTTPException(404): workspace not found / not in actor's tenant.
    """
    if not getattr(settings, "WORKSPACE_DATA_SOURCE_TENANT_ADMIN_ONLY", False):
        return  # legacy mode — RBAC unchanged

    if actor.actor_role == "platform_admin":
        return  # platform_admin always allowed

    # Local imports to avoid circular dependency at module load.
    from sqlalchemy import text as _sql_text

    from app.api.v1.dependencies.tenant_auth import (
        ActorContext as _ActorContext,
    )
    from app.api.v1.dependencies.tenant_auth import (
        _is_tenant_admin,
    )

    row = db.execute(
        _sql_text("SELECT tenant_id FROM control.workspaces WHERE workspace_id = :wid"),
        {"wid": str(workspace_id)},
    ).fetchone()
    if row is None:
        # Don't leak existence — same shape as legacy 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    workspace_tenant_id = row[0]
    if str(workspace_tenant_id) != str(actor.tenant_id):
        # Cross-tenant attempt — collapse to 404 to avoid existence leaks.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    surrogate = _ActorContext(
        actor_id=actor.actor_id,
        actor_role=actor.actor_role,
        tenant_id=actor.tenant_id,
    )
    if not _is_tenant_admin(workspace_tenant_id, surrogate, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": {
                    "code": "RBAC_FORBIDDEN",
                    "message": (
                        "Workspace data sources are managed at the tenant "
                        "level. Contact your tenant administrator."
                    ),
                    "fields": None,
                }
            },
        )
