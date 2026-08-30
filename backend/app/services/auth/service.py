"""
Authentication Service
Main service for user authentication, registration, and session management
"""

import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import EmailVerification, MFASettings, PasswordReset, User, UserStatus
from app.models.user import Session as UserSession
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    RegisterResponse,
    SessionInfo,
    SessionListResponse,
    UserProfile,
)
from app.services.auth.jwt import create_access_token, create_refresh_token, verify_token

# Workspace role precedence (highest -> lowest) for JWT projection.
# When a user has no platform_role, we project their highest workspace
# role into ``actor_role`` so downstream guards that read the JWT (e.g.
# ``verify_data_source_write_actor``) can authorise without a per-request
# DB round-trip. Multi-workspace users still see a single role here;
# fine-grained per-workspace checks happen in workspace_auth which
# resolves ``control.workspace_role_assignments`` directly.
#
# Canonical fixed roles live in
# ``app.services.workspaces.rbac.FIXED_ROLE_PERMISSIONS``. The legacy
# names (``workspace_steward``, ``workspace_viewer``) are retained as
# lower-precedence aliases so historical tokens and integration fixtures
# keep working while production users with canonical roles
# (``data_steward``, ``business_analyst``, ``governance_viewer``) get the
# permissions they actually own.
_WORKSPACE_ROLE_PRECEDENCE = [
    "workspace_administrator",
    "data_engineer",
    "data_steward",
    "workspace_steward",  # legacy alias
    "business_analyst",
    "governance_viewer",
    "workspace_viewer",  # legacy alias
]


def _resolve_actor_role(db: Session, user) -> str:
    """Pick the role to project into the JWT for ``user``.

    Order:
      1. ``user.platform_role`` if set (e.g. platform_admin / tenant_admin).
      2. Highest-precedence row from ``control.workspace_role_assignments``
         for the user, per ``_WORKSPACE_ROLE_PRECEDENCE``.
      3. Literal ``"member"`` fallback (legacy behaviour).
    """
    platform_role = getattr(user, "platform_role", None) if user else None
    if platform_role:
        return platform_role
    if user is None:
        return "member"
    try:
        from sqlalchemy import text as _sql_text  # local import keeps top-level imports tidy

        rows = db.execute(
            _sql_text(
                "SELECT DISTINCT role_name FROM control.workspace_role_assignments "
                "WHERE user_id = :uid"
            ),
            {"uid": str(user.id)},
        ).fetchall()
        roles = {row.role_name for row in rows if row.role_name}
        for candidate in _WORKSPACE_ROLE_PRECEDENCE:
            if candidate in roles:
                return candidate
    except Exception:  # pragma: no cover - never block login on this lookup
        pass
    return "member"


class AuthService:
    """Authentication service"""

    def __init__(self, db: Session):
        self.db = db

    def register_user(
        self, request: RegisterRequest, ip_address: str | None = None
    ) -> RegisterResponse:
        """
        Register a new user.

        Gated by two rules (BUG-003):
          1. If settings.ALLOW_PUBLIC_REGISTRATION is False (default),
             the request MUST include a valid ``invitation_token``.
          2. Any valid invitation_token overrides the flag — the invitation
             itself authorises the registration and carries the tenant /
             workspace role.  The token is consumed (status='accepted',
             accepted_at=now()) in the same transaction.
        """
        from sqlalchemy import text as _sql_text

        invitation_row = None
        if request.invitation_token:
            invitation_row = self.db.execute(
                _sql_text(
                    "SELECT id, workspace_id, tenant_id, email, role, expires_at, "
                    "COALESCE(status,'pending') AS status, accepted "
                    "FROM invitations WHERE token = :tok LIMIT 1"
                ),
                {"tok": request.invitation_token},
            ).fetchone()

            if not invitation_row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invitation token is invalid.",
                )
            if invitation_row.accepted or (
                invitation_row.status and invitation_row.status != "pending"
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invitation token has already been used.",
                )
            if invitation_row.expires_at and invitation_row.expires_at < datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invitation token has expired.",
                )
            if invitation_row.email.lower() != request.email.lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invitation was issued to a different email address.",
                )

        elif not settings.ALLOW_PUBLIC_REGISTRATION:
            # No invitation, and public registration disabled → 403.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Public registration is disabled. An invitation is required.",
            )

        # Check if user already exists
        existing_user = self.db.query(User).filter(User.email == request.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
            )

        # Create new user
        user = User(
            email=request.email,
            full_name=request.full_name,
            status=UserStatus.PENDING,
        )
        user.set_password(request.password)

        if invitation_row is not None and invitation_row.tenant_id is not None:
            user.tenant_id = invitation_row.tenant_id
            # Invitation pre-verifies the email.
            user.email_verified = True
            user.status = UserStatus.ACTIVE

        self.db.add(user)
        self.db.flush()  # assign user.id before attaching workspace role

        if invitation_row is not None:
            # Consume the invitation.
            self.db.execute(
                _sql_text(
                    "UPDATE invitations SET accepted=TRUE, status='accepted', "
                    "accepted_at=NOW() WHERE id = :id"
                ),
                {"id": invitation_row.id},
            )

            # Attach workspace role if the invitation was scoped to one.
            if invitation_row.workspace_id is not None and invitation_row.role:
                try:
                    self.db.execute(
                        _sql_text(
                            "INSERT INTO control.workspace_role_assignments "
                            "(workspace_id, user_id, role_name, granted_by) "
                            "VALUES (:ws, :uid, :role, :uid) "
                            "ON CONFLICT (workspace_id, user_id) DO NOTHING"
                        ),
                        {
                            "ws": invitation_row.workspace_id,
                            "uid": str(user.id),
                            "role": invitation_row.role,
                        },
                    )
                except Exception:  # pragma: no cover - best effort
                    pass

        self.db.commit()
        self.db.refresh(user)

        # Only create an email-verification row when no invitation consumed
        # (otherwise the email is already verified).
        if invitation_row is None:
            self._create_email_verification(user.id)

        return RegisterResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            message=(
                "Registration successful."
                if invitation_row is not None
                else "Registration successful. Please check your email to verify your account."
            ),
        )

    def login(
        self,
        request: LoginRequest,
        device_info: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> LoginResponse:
        """
        Authenticate user and create session

        Args:
            request: Login request data
            device_info: Device information
            ip_address: User's IP address

        Returns:
            LoginResponse with tokens and user data

        Raises:
            HTTPException: If credentials are invalid
        """
        # Find user
        user = self.db.query(User).filter(User.email == request.email).first()

        if not user or not user.verify_password(request.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
            )

        # Check if account is active
        if user.status == UserStatus.DISABLED:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

        if user.status == UserStatus.SUSPENDED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Account is suspended"
            )

        # Check if MFA is enabled
        mfa_settings = self.db.query(MFASettings).filter(MFASettings.user_id == user.id).first()

        if mfa_settings and mfa_settings.enabled:
            # Return response indicating MFA is required
            # Frontend should then call MFA verification endpoint
            return LoginResponse(
                access_token="",
                refresh_token="",
                expires_in=0,
                user=UserProfile.from_orm(user),
                requires_mfa=True,
            )

        # Create session
        session = self._create_session(
            user.id, device_info=device_info, ip_address=ip_address, remember_me=request.remember_me
        )

        # Update last login
        user.last_login_at = datetime.utcnow()
        user.status = UserStatus.ACTIVE  # Activate on first login
        self.db.commit()

        # Create tokens
        token_data = {
            "sub": str(user.id),
            "actor_id": str(user.id),
            "email": user.email,
            "session_id": str(session.id),
            # Embed role so tenant endpoints can authorise without a DB round-trip.
            # Platform roles win; otherwise we project the highest workspace role
            # the user holds (per ``_WORKSPACE_ROLE_PRECEDENCE``). Falls back to
            # "member" only when the user has no role assignments at all.
            "actor_role": _resolve_actor_role(self.db, user),
        }
        # Include tenant_id if the user has one assigned (required by workspace endpoints).
        if getattr(user, "tenant_id", None):
            token_data["tenant_id"] = str(user.tenant_id)

        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserProfile.from_orm(user),
        )

    def logout(self, session_id: UUID) -> MessageResponse:
        """
        Logout user by invalidating session

        Args:
            session_id: Session ID to invalidate

        Returns:
            MessageResponse
        """
        session = self.db.query(UserSession).filter(UserSession.id == session_id).first()

        if session:
            self.db.delete(session)
            self.db.commit()

        return MessageResponse(message="Logged out successfully")

    def refresh_session(self, refresh_token: str) -> dict[str, str]:
        """
        Refresh access token using refresh token

        Args:
            refresh_token: Refresh token

        Returns:
            Dictionary with new access token

        Raises:
            HTTPException: If refresh token is invalid
        """
        token_data = verify_token(refresh_token, token_type="refresh")

        # Verify session still exists
        if token_data.session_id:
            session = (
                self.db.query(UserSession).filter(UserSession.id == token_data.session_id).first()
            )

            if not session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid"
                )

            # Check if session is expired
            if session.expires_at < datetime.utcnow():
                self.db.delete(session)
                self.db.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired"
                )

        # Create new access token — re-fetch user to get latest platform_role
        user = self.db.query(User).filter(User.id == token_data.user_id).first()
        new_token_data = {
            "sub": str(token_data.user_id),
            "actor_id": str(token_data.user_id),
            "email": token_data.email,
            "session_id": str(token_data.session_id) if token_data.session_id else None,
            "actor_role": _resolve_actor_role(self.db, user),
        }
        # Include tenant_id if the user has one assigned (required by workspace endpoints).
        if user and getattr(user, "tenant_id", None):
            new_token_data["tenant_id"] = str(user.tenant_id)

        access_token = create_access_token(new_token_data)

        return {"access_token": access_token, "token_type": "bearer"}

    def verify_email(self, token: str) -> MessageResponse:
        """
        Verify user email with token

        Args:
            token: Email verification token

        Returns:
            MessageResponse

        Raises:
            HTTPException: If token is invalid or expired
        """
        verification = (
            self.db.query(EmailVerification).filter(EmailVerification.token == token).first()
        )

        if not verification:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token"
            )

        if verification.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token expired"
            )

        # Update user
        user = self.db.query(User).filter(User.id == verification.user_id).first()
        if user:
            user.email_verified = True
            user.status = UserStatus.ACTIVE

        # Delete verification token
        self.db.delete(verification)
        self.db.commit()

        return MessageResponse(message="Email verified successfully")

    def request_password_reset(self, request: PasswordResetRequest) -> MessageResponse:
        """
        Request password reset

        Args:
            request: Password reset request

        Returns:
            MessageResponse
        """
        user = self.db.query(User).filter(User.email == request.email).first()

        # Always return success even if user doesn't exist (security)
        if not user:
            return MessageResponse(
                message="If the email exists, a password reset link has been sent"
            )

        # Create password reset token
        reset_token = self._create_password_reset(user.id)

        # Send password reset email (best-effort). Uses tenant SMTP via the
        # dispatcher; if no SMTP is configured we log a warning so an operator
        # can still recover the token from logs in dev.
        try:
            from app.services.auth.password_reset_email import (
                send_password_reset_email,
            )

            send_password_reset_email(
                self.db,
                user=user,
                token=reset_token.token,
            )
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "password_reset_email_failed user_id=%s err=%s", user.id, exc
            )

        return MessageResponse(message="If the email exists, a password reset link has been sent")

    def reset_password(self, request: PasswordResetConfirm) -> MessageResponse:
        """
        Reset password with token

        Args:
            request: Password reset confirmation

        Returns:
            MessageResponse

        Raises:
            HTTPException: If token is invalid or expired
        """
        reset = (
            self.db.query(PasswordReset)
            .filter(PasswordReset.token == request.token, PasswordReset.used == False)
            .first()
        )

        if not reset:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or already used reset token",
            )

        if reset.expires_at < datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token expired"
            )

        # Update password
        user = self.db.query(User).filter(User.id == reset.user_id).first()
        if user:
            user.set_password(request.new_password)
            # Activate PENDING accounts when they complete the
            # invitation / activation password flow.
            if user.status == UserStatus.PENDING:
                user.status = UserStatus.ACTIVE
                user.email_verified = True
            reset.used = True

            # Invalidate all sessions
            self.db.query(UserSession).filter(UserSession.user_id == user.id).delete()

        self.db.commit()

        return MessageResponse(message="Password reset successfully")

    def list_sessions(
        self, user_id: UUID, current_session_id: UUID | None = None
    ) -> SessionListResponse:
        """
        List user's active sessions

        Args:
            user_id: User ID
            current_session_id: Current session ID to mark

        Returns:
            SessionListResponse
        """
        sessions = (
            self.db.query(UserSession)
            .filter(UserSession.user_id == user_id, UserSession.expires_at > datetime.utcnow())
            .all()
        )

        session_infos = [
            SessionInfo(
                id=session.id,
                device_info=session.device_info,
                ip_address=str(session.ip_address) if session.ip_address else None,
                created_at=session.created_at,
                expires_at=session.expires_at,
                is_current=(session.id == current_session_id),
            )
            for session in sessions
        ]

        return SessionListResponse(sessions=session_infos, total=len(session_infos))

    def revoke_session(self, session_id: UUID, user_id: UUID) -> MessageResponse:
        """
        Revoke a specific session

        Args:
            session_id: Session ID to revoke
            user_id: User ID (for verification)

        Returns:
            MessageResponse

        Raises:
            HTTPException: If session not found or doesn't belong to user
        """
        session = (
            self.db.query(UserSession)
            .filter(UserSession.id == session_id, UserSession.user_id == user_id)
            .first()
        )

        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        self.db.delete(session)
        self.db.commit()

        return MessageResponse(message="Session revoked successfully")

    # Helper methods

    def _create_session(
        self,
        user_id: UUID,
        device_info: dict[str, Any] | None = None,
        ip_address: str | None = None,
        remember_me: bool = False,
    ) -> UserSession:
        """Create a new user session"""
        # Set expiration based on remember_me
        if remember_me:
            expires_at = datetime.utcnow() + timedelta(days=30)
        else:
            expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        session = UserSession(
            user_id=user_id,
            token=secrets.token_urlsafe(32),
            device_info=device_info,
            ip_address=ip_address,
            expires_at=expires_at,
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return session

    def _create_email_verification(self, user_id: UUID) -> EmailVerification:
        """Create email verification token"""
        verification = EmailVerification(
            user_id=user_id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        self.db.add(verification)
        self.db.commit()
        self.db.refresh(verification)

        return verification

    def _create_password_reset(self, user_id: UUID) -> PasswordReset:
        """Create password reset token"""
        reset = PasswordReset(
            user_id=user_id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )

        self.db.add(reset)
        self.db.commit()
        self.db.refresh(reset)

        return reset
