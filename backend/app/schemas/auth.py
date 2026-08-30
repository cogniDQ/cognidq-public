"""
Authentication schemas
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, validator


class UserStatus(str, Enum):
    """User status enum"""

    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    SUSPENDED = "suspended"


class MFAMethod(str, Enum):
    """MFA method enum"""

    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"


# Registration
class RegisterRequest(BaseModel):
    """User registration request.

    Registration is gated by settings.ALLOW_PUBLIC_REGISTRATION.  When that
    flag is False (production default), ``invitation_token`` is REQUIRED and
    must correspond to a pending row in ``public.invitations``.  The token
    carries the tenant_id and workspace role that the new user inherits.
    """

    email: EmailStr
    password: str = Field(
        ..., min_length=8, max_length=128, description="Password must be 8-128 characters"
    )
    full_name: str | None = None
    invitation_token: str | None = Field(
        default=None,
        description="Invitation token from /tenants/{id}/invitations. "
        "Required unless ALLOW_PUBLIC_REGISTRATION=true.",
    )

    @validator("password")
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class RegisterResponse(BaseModel):
    """User registration response"""

    id: UUID
    email: str
    full_name: str | None
    message: str = "Registration successful. Please check your email to verify your account."

    class Config:
        from_attributes = True


# Login
class LoginRequest(BaseModel):
    """User login request.

    Note: ``email`` is intentionally typed as ``str`` (not ``EmailStr``) so that
    QA / fixture accounts using reserved TLDs such as ``*.test`` can log in.
    Authentication itself looks the address up verbatim in the users table, so
    strict RFC-deliverability checks add no security value here.
    """

    email: str = Field(..., min_length=3, max_length=320)
    password: str
    remember_me: bool = False


# User Profile
class UserProfile(BaseModel):
    """User profile schema"""

    id: UUID
    email: str
    full_name: str | None
    avatar_url: str | None
    email_verified: bool
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime
    platform_role: str | None = None
    tenant_id: UUID | None = None

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """User login response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile  # Now defined before use
    requires_mfa: bool = False

    class Config:
        from_attributes = True


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""

    refresh_token: str


class UpdateProfile(BaseModel):
    """Update user profile request"""

    full_name: str | None = None
    avatar_url: str | None = None


class ChangePasswordRequest(BaseModel):
    """Change password request"""

    current_password: str
    new_password: str = Field(..., min_length=8)

    @validator("new_password")
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# Password Reset
class PasswordResetRequest(BaseModel):
    """Request password reset"""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with token"""

    token: str
    new_password: str = Field(..., min_length=8)

    @validator("new_password")
    def password_strength(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


# Email Verification
class EmailVerificationRequest(BaseModel):
    """Request email verification"""

    email: EmailStr


class EmailVerificationConfirm(BaseModel):
    """Confirm email with token"""

    token: str


# MFA
class MFASetupRequest(BaseModel):
    """MFA setup request"""

    method: MFAMethod = MFAMethod.TOTP


class MFASetupResponse(BaseModel):
    """MFA setup response"""

    secret: str
    qr_code_url: str
    backup_codes: list[str]


class MFAVerifyRequest(BaseModel):
    """MFA verification request"""

    code: str = Field(..., min_length=6, max_length=6)


class MFADisableRequest(BaseModel):
    """MFA disable request"""

    password: str


# Sessions
class SessionInfo(BaseModel):
    """Session information"""

    id: UUID
    device_info: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """List of user sessions"""

    sessions: list[SessionInfo]
    total: int


# Token
class Token(BaseModel):
    """JWT Token"""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token payload data"""

    user_id: UUID
    email: str
    session_id: UUID | None = None


# General responses
class MessageResponse(BaseModel):
    """Generic message response"""

    message: str
    success: bool = True
