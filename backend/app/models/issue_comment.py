"""
IssueComment ORM Model — F036 Issue Comments and Activity Timeline

Maps to the ``public.issue_comments`` table created by migration
018_f036_issue_comments.sql.  Comments are immutable after creation
(no update/delete operations exposed).
"""

from uuid import uuid4

from sqlalchemy import TIMESTAMP, Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.database import Base


class IssueComment(Base):
    """Immutable user comment attached to a data-quality issue."""

    __tablename__ = "issue_comments"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)

    issue_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("issues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id = Column(PG_UUID(as_uuid=True), nullable=False)

    author_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    body = Column(Text, nullable=False)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- Relationships ---
    author = relationship("User", back_populates=None, foreign_keys=[author_id])
