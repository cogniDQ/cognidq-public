"""
Ingestion Schemas

Pydantic schemas for ingestion requests and responses.
"""

from typing import Any

from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """Response after file upload."""

    file_id: str
    file_path: str
    original_filename: str
    file_type: str
    row_count: int
    file_size: int
    encoding: str | None = None
    parse_time: float | None = None
    columns: list[dict[str, Any]]
    sample_data: list[dict[str, Any]]


class CreateIngestionJobRequest(BaseModel):
    """Request to create an ingestion job."""

    data_source_id: str | None = None
    target_table: str = Field(..., min_length=1, max_length=255)
    mode: str = Field(default="append", pattern="^(append|replace|upsert)$")


class IngestionJobResponse(BaseModel):
    """Ingestion job response."""

    id: str
    data_source_id: str | None = None
    target_table: str
    mode: str
    status: str
    total_rows: int | None = None
    processed_rows: int
    failed_rows: int
    error_message: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class IngestionJobListResponse(BaseModel):
    """List of ingestion jobs."""

    id: str
    data_source_id: str | None = None
    target_table: str
    mode: str
    status: str
    total_rows: int | None = None
    processed_rows: int
    failed_rows: int
    created_at: str


class DataProfileResponse(BaseModel):
    """Data profiling results."""

    total_rows: int
    total_columns: int
    columns: list[dict[str, Any]]
    profiled_at: str
