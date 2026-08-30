"""Data Source models for managing database connections and schema metadata."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.database import Base


class DataSource(Base):
    """
    Data Source model representing a connection to an external data system.
    Supports databases (PostgreSQL, MySQL, Snowflake, Databricks) and cloud storage (S3, GCS, Azure).
    """

    __tablename__ = "data_sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), nullable=True)
    name = Column(String(255), nullable=False)
    type = Column(
        String(50), nullable=False
    )  # postgresql, mysql, snowflake, databricks, s3, gcs, azure_datalake
    connection_config = Column(JSON, nullable=False)  # encrypted credentials and connection params
    status = Column(String(50), default="active")  # active, inactive, error, testing
    last_tested_at = Column(DateTime, nullable=True)
    test_result = Column(JSON, nullable=True)  # last test connection result
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    schemas = relationship(
        "DataSourceSchema", back_populates="datasource", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<DataSource {self.name} ({self.type})>"


class DataSourceSchema(Base):
    """
    Data Source Schema model storing metadata about tables, columns, and data types.
    Populated by schema introspection/refresh operations.
    """

    __tablename__ = "data_source_schemas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data_source_id = Column(
        UUID(as_uuid=True), ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False
    )
    schema_name = Column(String(255), nullable=True)  # database schema (e.g., 'public', 'dbo')
    table_name = Column(String(255), nullable=True)
    column_name = Column(String(255), nullable=True)
    column_type = Column(String(100), nullable=True)
    is_nullable = Column(Boolean, nullable=True)
    is_primary_key = Column(Boolean, default=False)
    default_value = Column(Text, nullable=True)
    meta_data = Column("metadata", JSON, default={})  # max_length, precision, scale, etc.
    refreshed_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    datasource = relationship("DataSource", back_populates="schemas")

    def __repr__(self):
        return f"<DataSourceSchema {self.schema_name}.{self.table_name}.{self.column_name}>"
