"""
Personal Access Token models
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import ARRAY, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class AccessToken(Base):
    """Personal Access Token model for API authentication"""

    __tablename__ = "access_tokens"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(255), nullable=False)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    prefix = Column(String(20), nullable=False, index=True)
    scopes = Column(ARRAY(Text), default=[])
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="access_tokens")

    def is_valid(self) -> bool:
        """Check if token is still valid"""
        if self.revoked_at:
            return False
        if self.expires_at and self.expires_at < datetime.now(self.expires_at.tzinfo):
            return False
        return True

    def __repr__(self):
        return f"<AccessToken {self.name} ({self.prefix}...)>"
