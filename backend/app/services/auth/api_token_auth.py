"""
F057 — API Token Authentication
=================================

FastAPI dependencies for authenticating requests via Personal Access Tokens
(from F056) and enforcing scope-based access control.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.models.access_token import AccessToken
from app.models.database import get_db
from app.models.user import User
from app.services.auth.token_service import AccessTokenService

logger = logging.getLogger(__name__)

# Reuse the same HTTPBearer scheme (tokens arrive as "Bearer <token>")
_bearer = HTTPBearer()

# ---------------------------------------------------------------------------
# Valid scopes
# ---------------------------------------------------------------------------

VALID_SCOPES = frozenset(
    {
        # F057 — read scopes
        "read:datasets",
        "read:rules",
        "read:executions",
        "read:issues",
        "read:incidents",
        # F058 — write scopes
        "write:datasets",
        "write:rules",
        "write:executions",
        "write:issues",
    }
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_api_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AccessToken:
    """Validate a Personal Access Token from the Authorization header.

    Returns the ``AccessToken`` row if the token is valid (not revoked,
    not expired).  Raises 401 otherwise.
    """
    plain_token = credentials.credentials

    token = AccessTokenService.verify_token(db, plain_token)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


async def get_token_user(
    token: AccessToken = Depends(get_api_token),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the owning ``User`` from a validated API token.

    This mirrors the shape of ``get_current_user`` so endpoints can
    accept either JWT or API-token auth interchangeably.
    """
    user = db.query(User).filter(User.id == token.user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token owner not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status.upper() not in ("ACTIVE", "PENDING"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active",
        )
    return user


class ScopeChecker:
    """Callable dependency that verifies the token carries a required scope.

    Usage::

        @router.get("/datasets")
        async def list_datasets(
            token: AccessToken = Depends(get_api_token),
            _: None = Depends(ScopeChecker("read:datasets")),
        ):
            ...
    """

    def __init__(self, required_scope: str) -> None:
        self.required_scope = required_scope

    async def __call__(self, token: AccessToken = Depends(get_api_token)) -> None:
        scopes: list[str] = token.scopes or []
        if self.required_scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Token missing required scope: {self.required_scope}",
            )
