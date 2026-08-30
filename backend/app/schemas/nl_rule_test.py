"""
F107 — NL Rule Test Preview Pydantic Schemas.
TestPreviewRequest, TestPreviewResponse, TestStatistics, etc.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.nl_compiler import CompiledCheckConfig


class TestPreviewRequest(BaseModel):
    compiled_config: CompiledCheckConfig = Field(..., description="Compiled rule from F104")
    sample_size: int = Field(default=50, ge=1, le=1000, description="Number of sample data rows")
    violation_limit: int = Field(default=10, ge=1, le=100, description="Max violation examples")


class TestStatistics(BaseModel):
    total_rows: int = Field(0, ge=0, description="Total rows in dataset")
    rows_passed: int = Field(0, ge=0, description="Rows passing the rule")
    rows_failed: int = Field(0, ge=0, description="Rows failing the rule")
    pass_rate: float = Field(0.0, ge=0.0, le=100.0, description="Pass rate percentage")


class TestPreviewResponse(BaseModel):
    status: str = Field(..., description="success or error")
    sample_data: list[dict[str, Any]] = Field(
        default_factory=list, description="First N rows from dataset"
    )
    statistics: TestStatistics | None = Field(None, description="Row count statistics")
    violations: list[dict[str, Any]] = Field(
        default_factory=list, description="Example violating rows"
    )
    expression: str | None = Field(None, description="Technical SQL/expression of the rule")
    warnings: list[str] = Field(default_factory=list, description="Type/null warnings")
    error_message: str | None = Field(None, description="Error detail if status is error")
