"""
F005 — Dataset Authorization Guards
=====================================

Provides JWT authentication and RBAC for dataset endpoints.
Follows the same pattern as data_source_auth.py (F004).

Canonical workspace roles (see ``services/workspaces/rbac.py``):
  Write:   workspace_administrator, data_engineer, data_steward
  Read:    + business_analyst, governance_viewer
  Archive: workspace_administrator only (+ platform_admin)
  Pause:   workspace_administrator, data_engineer (+ platform_admin)

Legacy role aliases (``workspace_steward``, ``workspace_viewer``,
``data_owner``, ``platform_operator``) remain accepted so historical
tokens and integration tests stay green.
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

DATASET_WRITE_ROLES: frozenset = frozenset(
    {
        # canonical workspace roles with datasets:write
        "workspace_administrator",
        "data_engineer",
        "data_steward",
        # platform admin
        "platform_admin",
        # tenant admin (mirrors data_sources auth — owns tenant resources)
        "tenant_admin",
        # legacy aliases
        "workspace_steward",
    }
)

DATASET_READ_ROLES: frozenset = frozenset(
    {
        # canonical workspace roles with datasets:read (all five)
        "workspace_administrator",
        "data_engineer",
        "data_steward",
        "business_analyst",
        "governance_viewer",
        # platform operators
        "platform_admin",
        "platform_viewer",
        # tenant admin (mirrors data_sources auth — owns tenant resources)
        "tenant_admin",
        # legacy aliases
        "workspace_steward",
        "workspace_viewer",
        "data_owner",
        "platform_operator",
    }
)

DATASET_ARCHIVE_ROLES: frozenset = frozenset(
    {"workspace_administrator", "platform_admin", "tenant_admin"}
)

DATASET_PAUSE_ROLES: frozenset = frozenset(
    {"workspace_administrator", "data_engineer", "platform_admin", "tenant_admin"}
)


# ---------------------------------------------------------------------------
# Actor context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetActorContext:
    """Resolved identity extracted from JWT for dataset operations."""

    actor_id: UUID
    actor_role: str
    tenant_id: UUID | None


# Roles whose tokens may legitimately omit ``tenant_id`` (mirrors
# ``data_source_auth._TENANT_OPTIONAL_ROLES``). Platform operators are
# global by design and are not bound to a single tenant.
_TENANT_OPTIONAL_ROLES: frozenset = frozenset(
    {
        "platform_admin",
        "platform_viewer",
        "platform_operator",  # legacy alias
    }
)


# ---------------------------------------------------------------------------
# Internal helpers
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


def _build_actor_context(payload: dict) -> DatasetActorContext:
    raw_actor_id: str | None = payload.get("actor_id")
    actor_role: str | None = payload.get("actor_role")
    raw_tenant_id: str | None = payload.get("tenant_id")

    if not raw_actor_id or not actor_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain required identity claims",
        )
    # Platform-scoped roles may legitimately omit tenant_id (they aren't
    # bound to a single tenant). Tenant-scoped roles must carry one.
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
    return DatasetActorContext(
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
    )


# ---------------------------------------------------------------------------
# FastAPI dependency functions
# ---------------------------------------------------------------------------


async def verify_dataset_write_actor(request: Request) -> DatasetActorContext:
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    if actor.actor_role not in DATASET_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{actor.actor_role}' is not authorised to modify datasets. "
                f"Required: {sorted(DATASET_WRITE_ROLES)}"
            ),
        )
    return actor


async def verify_dataset_read_actor(request: Request) -> DatasetActorContext:
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    if actor.actor_role not in DATASET_READ_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{actor.actor_role}' is not authorised to read datasets. "
                f"Required: {sorted(DATASET_READ_ROLES)}"
            ),
        )
    return actor


async def verify_dataset_archive_actor(request: Request) -> DatasetActorContext:
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    if actor.actor_role not in DATASET_ARCHIVE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{actor.actor_role}' is not authorised to archive datasets. "
                f"Required: {sorted(DATASET_ARCHIVE_ROLES)}"
            ),
        )
    return actor


async def verify_dataset_pause_actor(request: Request) -> DatasetActorContext:
    authorization: str | None = request.headers.get("Authorization")
    token = _extract_bearer_token(authorization)
    payload = _decode_token(token)
    actor = _build_actor_context(payload)

    if actor.actor_role not in DATASET_PAUSE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{actor.actor_role}' is not authorised to pause/deactivate datasets. "
                f"Required: {sorted(DATASET_PAUSE_ROLES)}"
            ),
        )
    return actor
