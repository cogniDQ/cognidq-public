"""
Authentication API endpoints
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RegisterResponse,
    SessionListResponse,
    Token,
    UpdateProfile,
    UserProfile,
)
from app.services.audit.hooks import build_user_profile_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.auth.jwt import get_current_user, verify_token
from app.services.auth.service import AuthService

logger = logging.getLogger(__name__)
_audit_svc = AuditService()

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_client_info(request: Request) -> dict:
    """Extract client information from request"""
    return {
        "user_agent": request.headers.get("user-agent"),
        "platform": request.headers.get("sec-ch-ua-platform"),
    }


def get_client_ip(request: Request) -> str:
    """Get client IP address"""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, req: Request, db: Session = Depends(get_db)):
    """
    Register a new user

    - **email**: Valid email address
    - **password**: Password (min 8 characters, must contain uppercase, lowercase, and digit)
    - **full_name**: Optional full name
    """
    auth_service = AuthService(db)
    ip_address = get_client_ip(req)

    return auth_service.register_user(request, ip_address=ip_address)


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, req: Request, db: Session = Depends(get_db)):
    """
    Login with email and password

    - **email**: User's email
    - **password**: User's password
    - **remember_me**: Keep session active for 30 days

    Returns access token, refresh token, and user profile
    """
    auth_service = AuthService(db)
    device_info = get_client_info(req)
    ip_address = get_client_ip(req)

    return auth_service.login(request, device_info=device_info, ip_address=ip_address)


@router.post("/logout", response_model=MessageResponse)
def logout(
    authorization: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Logout current user.

    Marks the session referenced by the token's ``session_id`` claim as
    revoked (``sessions.revoked_at = now()``).  ``get_current_user`` will
    refuse any subsequent request using the same JWT because the session
    revocation check in jwt.py raises 401 (BUG-005).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return MessageResponse(message="Logged out successfully")

    token = authorization.split(None, 1)[1]
    try:
        token_data = verify_token(token, token_type="access")
    except HTTPException:
        return MessageResponse(message="Logged out successfully")

    if token_data.session_id is not None:
        from sqlalchemy import text as _sql_text

        db.execute(
            _sql_text(
                "UPDATE sessions SET revoked_at = NOW() WHERE id = :sid AND revoked_at IS NULL"
            ),
            {"sid": str(token_data.session_id)},
        )
        db.commit()

    return MessageResponse(message="Logged out successfully")


@router.post("/refresh", response_model=Token)
def refresh_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Refresh access token using refresh token

    - **refresh_token**: Valid refresh token

    Returns new access token
    """
    auth_service = AuthService(db)
    result = auth_service.refresh_session(request.refresh_token)

    return Token(**result)


@router.get("/me", response_model=UserProfile)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current user's profile

    Requires authentication
    """
    return UserProfile.from_orm(current_user)


@router.put("/me", response_model=UserProfile)
def update_current_user_profile(
    request: UpdateProfile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update current user's profile

    - **full_name**: Update full name
    - **avatar_url**: Update avatar URL
    """
    if request.full_name is not None:
        current_user.full_name = request.full_name

    if request.avatar_url is not None:
        current_user.avatar_url = request.avatar_url

    db.commit()
    db.refresh(current_user)

    # F052 audit hook (best-effort; only when tenant_id is available)
    if current_user.tenant_id:
        try:
            changed_fields = {}
            if request.full_name is not None:
                changed_fields["full_name"] = request.full_name
            if request.avatar_url is not None:
                changed_fields["avatar_url"] = request.avatar_url
            _audit_svc.write(
                db,
                build_user_profile_audit_entry(
                    ctx=AuditContext(
                        tenant_id=current_user.tenant_id,
                        actor_id=current_user.id,
                        actor_type="user",
                        actor_role=current_user.platform_role or "user",
                        request_id=None,
                        source_ip=None,
                    ),
                    action="user_profile_updated",
                    user_id=current_user.id,
                    after_state=changed_fields,
                ),
            )
            db.commit()
        except Exception:
            logger.warning(
                "audit_write_failed action_type=user_profile_updated user_id=%s", current_user.id
            )

    return UserProfile.from_orm(current_user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Change user password

    - **current_password**: Current password
    - **new_password**: New password (min 8 characters, must contain uppercase, lowercase, and digit)
    """
    # Verify current password
    if not current_user.verify_password(request.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )

    # Set new password
    current_user.set_password(request.new_password)
    db.commit()

    # F052 audit hook (best-effort; no password material in state)
    if current_user.tenant_id:
        try:
            _audit_svc.write(
                db,
                build_user_profile_audit_entry(
                    ctx=AuditContext(
                        tenant_id=current_user.tenant_id,
                        actor_id=current_user.id,
                        actor_type="user",
                        actor_role=current_user.platform_role or "user",
                        request_id=None,
                        source_ip=None,
                    ),
                    action="user_password_changed",
                    user_id=current_user.id,
                    after_state={"password_changed": True},
                ),
            )
            db.commit()
        except Exception:
            logger.warning(
                "audit_write_failed action_type=user_password_changed user_id=%s", current_user.id
            )

    return MessageResponse(message="Password changed successfully")


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Request password reset

    - **email**: User's email address

    Sends password reset email if email exists
    """
    auth_service = AuthService(db)
    return auth_service.request_password_reset(request)


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(request: PasswordResetConfirm, db: Session = Depends(get_db)):
    """
    Confirm password reset with token

    - **token**: Password reset token from email
    - **new_password**: New password (min 8 characters, must contain uppercase, lowercase, and digit)
    """
    auth_service = AuthService(db)
    return auth_service.reset_password(request)


@router.get("/verify-email/{token}", response_model=MessageResponse)
def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verify email address with token

    - **token**: Email verification token from registration email
    """
    auth_service = AuthService(db)
    return auth_service.verify_email(token)


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    List all active sessions for current user

    Requires authentication
    """
    auth_service = AuthService(db)
    return auth_service.list_sessions(current_user.id)


@router.delete("/sessions/{session_id}", response_model=MessageResponse)
def revoke_session(
    session_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Revoke a specific session

    - **session_id**: Session ID to revoke

    Requires authentication
    """
    from uuid import UUID

    auth_service = AuthService(db)
    return auth_service.revoke_session(UUID(session_id), current_user.id)
