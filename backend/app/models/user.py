"""
User and authentication models
"""

import enum
import hashlib
from uuid import uuid4

import bcrypt
from sqlalchemy import ARRAY, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()


class UserStatus(str, enum.Enum):
    """User status enum"""

    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    SUSPENDED = "suspended"


class MFAMethod(str, enum.Enum):
    """MFA method enum"""

    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"


class User(Base):
    """User model"""

    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(Text, nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    status = Column(
        SQLEnum(UserStatus, name="user_status"),
        default=UserStatus.PENDING,
        nullable=False,
        index=True,
    )
    # Platform-level role for the F001 tenant management feature.
    # Allowed values: 'platform_admin', 'platform_viewer', 'tenant_admin',
    # or NULL (regular user; workspace-level access only).
    platform_role = Column(String(50), nullable=True, default=None)
    # F002 workspace isolation: tenant_id for workspace_administrator role
    tenant_id = Column(PGUUID(as_uuid=True), nullable=True, default=None)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    email_verifications = relationship(
        "EmailVerification", back_populates="user", cascade="all, delete-orphan"
    )
    password_resets = relationship(
        "PasswordReset", back_populates="user", cascade="all, delete-orphan"
    )
    mfa_settings = relationship(
        "MFASettings", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    access_tokens = relationship("AccessToken", back_populates="user", cascade="all, delete-orphan")
    teams = relationship("Team", secondary="team_members", back_populates="members")
    role_assignments = relationship(
        "UserRoleAssignment",
        foreign_keys="UserRoleAssignment.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def set_password(self, password: str) -> None:
        """Hash and set password - supports passwords up to 128 characters"""
        # Hash with SHA-256 first to support passwords longer than 72 bytes (bcrypt limit)
        # SHA-256 produces a 64-character hex string which is well under bcrypt's 72-byte limit
        password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
        # Hash with bcrypt for secure storage
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(password_hash.encode("utf-8"), salt).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        if not self.password_hash:
            return False
        try:
            # Hash with SHA-256 first to match set_password behavior
            password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return bcrypt.checkpw(password_hash.encode("utf-8"), self.password_hash.encode("utf-8"))
        except Exception:
            return False

    def __repr__(self):
        return f"<User {self.email}>"


class Session(Base):
    """Session model for tracking user sessions"""

    __tablename__ = "sessions"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token = Column(String(255), unique=True, nullable=False, index=True)
    device_info = Column(JSONB, nullable=True)
    ip_address = Column(INET, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<Session {self.id} for user {self.user_id}>"


class EmailVerification(Base):
    """Email verification tokens"""

    __tablename__ = "email_verifications"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="email_verifications")

    def __repr__(self):
        return f"<EmailVerification {self.id} for user {self.user_id}>"


class PasswordReset(Base):
    """Password reset tokens"""

    __tablename__ = "password_resets"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="password_resets")

    def __repr__(self):
        return f"<PasswordReset {self.id} for user {self.user_id}>"


class MFASettings(Base):
    """Multi-factor authentication settings"""

    __tablename__ = "mfa_settings"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    method = Column(SQLEnum(MFAMethod, name="mfa_method"), nullable=True)
    secret = Column(String(255), nullable=True)
    backup_codes = Column(ARRAY(Text), nullable=True)
    enabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="mfa_settings")

    def __repr__(self):
        return f"<MFASettings {self.id} for user {self.user_id}>"
