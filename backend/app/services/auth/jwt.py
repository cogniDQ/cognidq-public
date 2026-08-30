"""
JWT Token Service
"""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.database import get_db
from app.models.user import User
from app.schemas.auth import TokenData

# Security scheme
security = HTTPBearer()


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create JWT access token

    Args:
        data: Dictionary containing token payload (user_id, email, etc.)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "access"})

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create JWT refresh token

    Args:
        data: Dictionary containing token payload (user_id, email, etc.)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT refresh token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "iat": datetime.utcnow(), "type": "refresh"})

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    return encoded_jwt


def verify_token(token: str, token_type: str = "access") -> TokenData:
    """
    Verify and decode JWT token

    Args:
        token: JWT token string
        token_type: Expected token type ("access" or "refresh")

    Returns:
        TokenData object with decoded payload

    Raises:
        HTTPException: If token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

        # Verify token type
        if payload.get("type") != token_type:
            raise credentials_exception

        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        session_id: str | None = payload.get("session_id")

        if user_id is None or email is None:
            raise credentials_exception

        token_data = TokenData(
            user_id=UUID(user_id), email=email, session_id=UUID(session_id) if session_id else None
        )

        return token_data

    except JWTError:
        raise credentials_exception


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token

    This is a FastAPI dependency that can be used to protect routes.

    Usage:
        @app.get("/protected")
        def protected_route(current_user: User = Depends(get_current_user)):
            return {"user": current_user.email}

    Args:
        credentials: HTTP Bearer credentials
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If user not found or inactive
    """
    token = credentials.credentials
    token_data = verify_token(token, token_type="access")

    # BUG-005: enforce session revocation.  A token whose session has been
    # revoked (logout) or never existed must be rejected.
    if token_data.session_id is not None:
        from sqlalchemy import text as _sql_text

        sess_row = db.execute(
            _sql_text("SELECT revoked_at, expires_at FROM sessions WHERE id = :sid LIMIT 1"),
            {"sid": str(token_data.session_id)},
        ).fetchone()
        if sess_row is None or sess_row.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user = db.query(User).filter(User.id == token_data.user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check user status (case-insensitive)
    if user.status.upper() not in ["ACTIVE", "PENDING"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active"
        )

    # Expunge the user from the session so that subsequent ORM operations
    # in the same request (e.g., rule/flow creation) don't hit SQLAlchemy
    # compiled-query-cache conflicts between the User and the new entity.
    db.expunge(user)
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Get current active user (additional check)

    Args:
        current_user: Current user from get_current_user

    Returns:
        User object if active

    Raises:
        HTTPException: If user is disabled
    """
    if current_user.status.upper() == "DISABLED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is disabled")

    return current_user
