"""
Data Quality Rule Schemas
Pydantic models for request/response validation.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# Enums
class RuleCategory(str, Enum):
    """Rule category enumeration."""

    COMPLETENESS = "completeness"
    VALIDITY = "validity"
    CONFORMITY = "conformity"
    UNIQUENESS = "uniqueness"
    CONSISTENCY = "consistency"
    ACCURACY = "accuracy"
    TIMELINESS = "timeliness"
    STATISTICAL = "statistical"
    RECONCILIATION = "reconciliation"


class RuleStatus(str, Enum):
    """Rule status enumeration."""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ExecutionStatus(str, Enum):
    """Execution status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionType(str, Enum):
    """Execution type enumeration."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    TEST = "test"


class ViolationSeverity(str, Enum):
    """Violation severity enumeration."""

    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


# Request Schemas
class CanonicalRuleDefinition(BaseModel):
    """Canonical rule definition structure."""

    dimension: RuleCategory
    entity: str = Field(..., description="Table.column or just table name")
    condition: str = Field(..., description="Rule condition (IS NOT NULL, REGEX, etc.)")
    expectation: str = Field(..., description="Expected outcome (100%, >95%, etc.)")
    severity: ViolationSeverity
    parameters: dict[str, Any] | None = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "dimension": "completeness",
                "entity": "customers.email",
                "condition": "IS NOT NULL",
                "expectation": "100%",
                "severity": "blocker",
                "parameters": {},
            }
        }


class ScheduleConfig(BaseModel):
    """Schedule configuration."""

    cron: str = Field(..., description="Cron expression")
    timezone: str = Field(default="UTC")
    enabled: bool = Field(default=True)

    class Config:
        json_schema_extra = {"example": {"cron": "0 0 * * *", "timezone": "UTC", "enabled": True}}


class ThresholdConfig(BaseModel):
    """Threshold configuration for pass/fail criteria."""

    pass_threshold: float | None = Field(None, description="Minimum pass rate (0-100)")
    warning_threshold: float | None = Field(None, description="Warning threshold (0-100)")
    blocker_threshold: float | None = Field(None, description="Blocker threshold (0-100)")
    max_violations: int | None = Field(None, description="Maximum allowed violations")

    class Config:
        json_schema_extra = {
            "example": {"pass_threshold": 95.0, "warning_threshold": 90.0, "max_violations": 100}
        }


class NotificationConfig(BaseModel):
    """Notification configuration."""

    enabled: bool = Field(default=True)
    on_failure: bool = Field(default=True)
    on_success: bool = Field(default=False)
    recipients: list[str] = Field(default_factory=list, description="Email addresses")
    channels: list[str] = Field(default_factory=list, description="slack, email, webhook")

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "on_failure": True,
                "on_success": False,
                "recipients": ["team@example.com"],
                "channels": ["email", "slack"],
            }
        }


class CreateRuleRequest(BaseModel):
    """Request to create a new rule."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    category: RuleCategory
    rule_type: str = Field(..., description="null_check, regex_check, range_check, etc.")
    canonical_rule: CanonicalRuleDefinition
    data_source_id: str | None = None
    target_schema: str | None = None
    target_table: str | None = None
    target_columns: list[str] | None = None
    status: RuleStatus | None = RuleStatus.DRAFT
    is_active: bool = True
    schedule: ScheduleConfig | None = None
    threshold_config: ThresholdConfig | None = None
    notification_config: NotificationConfig | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class UpdateRuleRequest(BaseModel):
    """Request to update an existing rule."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    category: RuleCategory | None = None
    rule_type: str | None = None
    canonical_rule: CanonicalRuleDefinition | None = None
    data_source_id: str | None = None
    target_schema: str | None = None
    target_table: str | None = None
    target_columns: list[str] | None = None
    status: RuleStatus | None = None
    is_active: bool | None = None
    schedule: ScheduleConfig | None = None
    threshold_config: ThresholdConfig | None = None
    notification_config: NotificationConfig | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class ExecuteRuleRequest(BaseModel):
    """Request to execute a rule."""

    execution_type: ExecutionType | None = ExecutionType.MANUAL
    parameters: dict[str, Any] | None = Field(default_factory=dict)
    sample_only: bool = Field(default=False, description="Execute on sample data only")
    sample_size: int | None = Field(None, description="Sample size for testing")


# Response Schemas
class RuleResponse(BaseModel):
    """Rule response."""

    id: str
    workspace_id: str
    name: str
    description: str | None
    category: RuleCategory
    rule_type: str | None
    canonical_rule: dict[str, Any]
    compiled_sql: str | None
    compiled_spark: str | None
    data_source_id: str | None
    target_schema: str | None
    target_table: str | None
    target_columns: list[str] | None
    status: RuleStatus
    is_active: bool
    schedule: dict[str, Any] | None
    threshold_config: dict[str, Any] | None
    notification_config: dict[str, Any] | None
    tags: list[str] | None
    metadata: dict[str, Any] | None
    created_by: str | None
    updated_by: str | None
    owner_user_id: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExecutionResponse(BaseModel):
    """Execution response."""

    id: str
    rule_id: str
    execution_type: ExecutionType
    status: ExecutionStatus
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    rows_scanned: int
    rows_passed: int
    rows_failed: int
    pass_rate: Decimal | None
    error_message: str | None
    error_details: dict[str, Any] | None
    result_details: dict[str, Any] | None
    execution_params: dict[str, Any] | None
    environment: dict[str, Any] | None
    executed_by: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class ViolationResponse(BaseModel):
    """Violation response."""

    id: str
    execution_id: str
    row_identifier: str | None
    row_number: int | None
    violation_details: dict[str, Any]
    severity: ViolationSeverity
    category: RuleCategory | None
    is_sample: bool
    metadata: dict[str, Any] | None
    created_at: datetime

    class Config:
        from_attributes = True


class ExecutionSummary(BaseModel):
    """Summary of recent executions."""

    total_executions: int
    completed: int
    failed: int
    running: int
    pending: int
    average_pass_rate: float | None
    last_execution: ExecutionResponse | None


class RuleWithExecutions(RuleResponse):
    """Rule with recent execution summary."""

    execution_summary: ExecutionSummary | None = None
    recent_executions: list[ExecutionResponse] = []


class BulkExecuteRequest(BaseModel):
    """Request to execute multiple rules."""

    rule_ids: list[str] = Field(..., min_length=1)
    execution_type: ExecutionType | None = ExecutionType.MANUAL
    parameters: dict[str, Any] | None = Field(default_factory=dict)


class BulkExecuteResponse(BaseModel):
    """Response from bulk execution."""

    total_rules: int
    executions_started: int
    execution_ids: list[str]
    errors: list[dict[str, str]] = []
