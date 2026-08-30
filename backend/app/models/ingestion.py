"""
Ingestion Models

Database models for data ingestion tracking.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID

from app.models.database import Base


class IngestionJobStatus(str, enum.Enum):
    """Ingestion job status enum."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionJob(Base):
    """Ingestion job tracking."""

    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=False), primary_key=True)
    workspace_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    data_source_id = Column(UUID(as_uuid=False), nullable=True, index=True)

    # File details
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(50), nullable=True)  # csv, excel, json, parquet
    original_filename = Column(String(255), nullable=True)

    # Target
    target_table = Column(String(255), nullable=False)

    # Ingestion mode
    mode = Column(String(20), nullable=False, default="append")  # append, replace, upsert

    # Status
    status = Column(SQLEnum(IngestionJobStatus), nullable=False, default=IngestionJobStatus.PENDING)

    # Progress
    total_rows = Column(Integer, nullable=True)
    processed_rows = Column(Integer, default=0)
    failed_rows = Column(Integer, default=0)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Metadata (profile, columns, etc.)
    meta_data = Column("metadata", JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Audit
    created_by = Column(UUID(as_uuid=False), nullable=True)
