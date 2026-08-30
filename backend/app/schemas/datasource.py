"""Data Source schemas for request/response validation."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, validator


class DataSourceBase(BaseModel):
    """Base schema for data source with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Data source name")
    type: str = Field(..., description="Data source type (postgresql, mysql, snowflake, etc.)")
    connection_config: dict[str, Any] = Field(
        ..., description="Connection configuration (credentials will be encrypted)"
    )


class CreateDataSourceRequest(DataSourceBase):
    """Request schema for creating a new data source."""

    @validator("type")
    def validate_type(cls, v):
        allowed_types = [
            "postgresql",
            "mysql",
            "snowflake",
            "databricks",
            "starburst",
            "s3",
            "gcs",
            "azure_datalake",
        ]
        if v not in allowed_types:
            raise ValueError(f"Type must be one of: {', '.join(allowed_types)}")
        return v


class UpdateDataSourceRequest(BaseModel):
    """Request schema for updating a data source."""

    name: str | None = Field(None, min_length=1, max_length=255)
    connection_config: dict[str, Any] | None = None
    status: str | None = Field(None, description="active, inactive, error")


class DataSourceResponse(DataSourceBase):
    """Response schema for data source (credentials masked)."""

    id: UUID
    workspace_id: UUID
    status: str
    last_tested_at: datetime | None
    test_result: dict[str, Any] | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    # Override connection_config to mask sensitive data
    connection_config: dict[str, Any] = Field(
        ..., description="Connection config (credentials masked)"
    )

    class Config:
        from_attributes = True


class TestConnectionRequest(BaseModel):
    """Request schema for testing a connection before saving."""

    type: str
    connection_config: dict[str, Any]

    @validator("type")
    def validate_type(cls, v):
        allowed_types = [
            "postgresql",
            "mysql",
            "snowflake",
            "databricks",
            "starburst",
            "s3",
            "gcs",
            "azure_datalake",
        ]
        if v not in allowed_types:
            raise ValueError(f"Type must be one of: {', '.join(allowed_types)}")
        return v


class TestConnectionResponse(BaseModel):
    """Response schema for connection test results."""

    success: bool
    message: str
    details: dict[str, Any] | None = None
    tested_at: datetime


class SchemaColumn(BaseModel):
    """Schema for a database column."""

    column_name: str
    column_type: str
    is_nullable: bool
    is_primary_key: bool = False
    default_value: str | None = None
    metadata: dict[str, Any] = {}


class SchemaTable(BaseModel):
    """Schema for a database table."""

    schema_name: str | None
    table_name: str
    columns: list[SchemaColumn]
    row_count: int | None = None


class SchemaMetadataResponse(BaseModel):
    """Response schema for schema metadata."""

    data_source_id: UUID
    tables: list[SchemaTable]
    refreshed_at: datetime | None = None


class DataPreviewRequest(BaseModel):
    """Request schema for data preview."""

    schema_name: str | None
    table_name: str
    limit: int = Field(default=100, ge=1, le=1000, description="Number of rows to preview")


class DataPreviewResponse(BaseModel):
    """Response schema for data preview."""

    schema_name: str | None
    table_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    preview_rows: int
