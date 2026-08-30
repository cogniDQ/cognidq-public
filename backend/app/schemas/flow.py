"""
Flow Schemas - Pydantic models for request/response validation

This module defines the Pydantic schemas for flow-related API operations.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ==============================================
# Enums
# ==============================================


class FlowStatus(str, Enum):
    """Flow status enumeration"""

    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ExecutionType(str, Enum):
    """Execution type enumeration"""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    TRIGGERED = "triggered"
    TEST = "test"


# Alias for frontend compatibility
ExecutionTrigger = ExecutionType


class ExecutionStatus(str, Enum):
    """Execution status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(str, Enum):
    """Node execution status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class NodeType(str, Enum):
    """Node type enumeration"""

    SOURCE = "source"
    CHECK = "check"
    JOIN = "join"
    FILTER = "filter"
    AGGREGATE = "aggregate"
    TRANSFORM = "transform"


# ==============================================
# Flow Definition Sub-schemas
# ==============================================


class NodePosition(BaseModel):
    """Node position on canvas"""

    x: float
    y: float


class FlowNode(BaseModel):
    """Flow node definition"""

    id: str = Field(..., description="Unique node identifier")
    type: NodeType = Field(..., description="Node type")
    label: str | None = Field(None, description="Node display label")
    config: dict[str, Any] = Field(default_factory=dict, description="Node configuration")
    position: NodePosition | None = Field(None, description="Node position on canvas")

    # For check nodes
    checkType: str | None = Field(None, description="Type of check (for check nodes)")

    # Visual styling
    style: dict[str, Any] | None = Field(None, description="Node visual style")


class FlowConnection(BaseModel):
    """Flow connection between nodes"""

    id: str = Field(..., description="Unique connection identifier")
    source: str = Field(..., alias="from", description="Source node ID")
    target: str = Field(..., alias="to", description="Target node ID")
    sourcePort: str | None = Field("output", description="Source port name")
    targetPort: str | None = Field("input", description="Target port name")
    label: str | None = Field(None, description="Connection label")

    class Config:
        populate_by_name = True  # Allow both 'source' and 'from'


class FlowDefinition(BaseModel):
    """Complete flow definition"""

    nodes: list[FlowNode] = Field(..., description="List of flow nodes")
    connections: list[FlowConnection] = Field(..., description="List of connections between nodes")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Additional metadata")


class ScheduleConfig(BaseModel):
    """Flow schedule configuration"""

    enabled: bool = Field(False, description="Whether scheduling is enabled")
    cron: str = Field(..., description="Cron expression for schedule")
    timezone: str = Field("UTC", description="Timezone for schedule")


class ExecutionConfig(BaseModel):
    """Execution configuration"""

    sample_size: int | None = Field(None, description="Number of rows to sample")
    parallel: bool = Field(True, description="Execute independent nodes in parallel")
    continue_on_error: bool = Field(False, description="Continue execution if a node fails")
    timeout_seconds: int | None = Field(None, description="Execution timeout in seconds")


# ==============================================
# Request Schemas
# ==============================================


class CreateFlowRequest(BaseModel):
    """Request schema for creating a flow"""

    name: str = Field(..., min_length=1, max_length=255, description="Flow name")
    description: str | None = Field(None, description="Flow description")
    flow_definition: FlowDefinition = Field(
        ..., description="Flow definition (nodes and connections)"
    )
    status: FlowStatus = Field(FlowStatus.DRAFT, description="Initial flow status")
    schedule: ScheduleConfig | None = Field(None, description="Schedule configuration")
    tags: list[str] | None = Field(None, description="Flow tags")


class UpdateFlowRequest(BaseModel):
    """Request schema for updating a flow"""

    name: str | None = Field(None, min_length=1, max_length=255, description="Flow name")
    description: str | None = Field(None, description="Flow description")
    flow_definition: FlowDefinition | None = Field(None, description="Flow definition")
    status: FlowStatus | None = Field(None, description="Flow status")
    is_active: bool | None = Field(None, description="Whether flow is active")
    schedule: ScheduleConfig | None = Field(None, description="Schedule configuration")
    tags: list[str] | None = Field(None, description="Flow tags")


class ExecuteFlowRequest(BaseModel):
    """Request schema for executing a flow"""

    execution_config: ExecutionConfig | None = Field(None, description="Execution configuration")
    parameters: dict[str, Any] | None = Field(None, description="Runtime parameters")


class ValidateFlowRequest(BaseModel):
    """Request schema for validating a flow definition"""

    flow_definition: FlowDefinition = Field(..., description="Flow definition to validate")


class ImportFlowRequest(BaseModel):
    """Request schema for importing a flow"""

    name: str = Field(..., description="Flow name")
    description: str | None = Field(None, description="Flow description")
    flow_definition: FlowDefinition = Field(..., description="Flow definition")
    tags: list[str] | None = Field(None, description="Flow tags")


# ==============================================
# Response Schemas
# ==============================================


class FlowResponse(BaseModel):
    """Response schema for a flow"""

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    flow_definition: dict[str, Any]  # FlowDefinition as dict
    status: str
    is_active: bool
    schedule: dict[str, Any] | None  # ScheduleConfig as dict
    tags: list[str] | None
    version: int
    created_by: UUID | None
    owner_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    # Optional execution statistics
    execution_count: int | None = None
    last_execution: datetime | None = None
    last_execution_status: str | None = None

    class Config:
        from_attributes = True


class FlowListResponse(BaseModel):
    """Response schema for list of flows"""

    flows: list[FlowResponse]
    total: int
    page: int
    page_size: int


class NodeResultData(BaseModel):
    """Node execution result data"""

    rows_scanned: int | None = None
    rows_passed: int | None = None
    rows_failed: int | None = None
    pass_rate: float | None = None
    violations: list[dict[str, Any]] | None = None

    # Additional fields depending on node type
    extra: dict[str, Any] | None = None


class FlowNodeResultResponse(BaseModel):
    """Response schema for a flow node result"""

    id: UUID
    execution_id: UUID
    node_id: str
    node_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    result_data: dict[str, Any] | None
    error_message: str | None
    error_details: dict[str, Any] | None
    execution_order: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class FlowExecutionResponse(BaseModel):
    """Response schema for a flow execution"""

    id: UUID
    flow_id: UUID
    execution_type: str = Field(..., alias="trigger", serialization_alias="trigger")
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: int | None
    nodes_executed: int
    nodes_passed: int
    nodes_failed: int
    nodes_skipped: int
    execution_config: dict[str, Any] | None
    result_summary: dict[str, Any] | None
    error_message: str | None
    error_details: dict[str, Any] | None
    executed_by: UUID | None
    created_at: datetime

    # Optional flow details
    flow_name: str | None = None

    # Optional node results
    node_results: list[FlowNodeResultResponse] | None = None

    # Enhanced fields for new report
    executed_by_name: str | None = None

    class Config:
        from_attributes = True
        populate_by_name = True


class FlowExecutionListResponse(BaseModel):
    """Response schema for list of flow executions"""

    executions: list[FlowExecutionResponse]
    total: int
    page: int
    page_size: int


class ValidationError(BaseModel):
    """Validation error details"""

    type: str
    message: str
    node_id: str | None = None
    connection_id: str | None = None


class FlowValidationResponse(BaseModel):
    """Response schema for flow validation"""

    is_valid: bool
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[ValidationError] = Field(default_factory=list)

    # Validation metadata
    node_count: int
    connection_count: int
    has_source: bool
    has_checks: bool
    has_circular_dependencies: bool


class FlowExportResponse(BaseModel):
    """Response schema for flow export"""

    flow_id: UUID
    name: str
    description: str | None
    flow_definition: dict[str, Any]
    exported_at: datetime
    export_format: str  # json, yaml

    class Config:
        from_attributes = True


class FlowTemplateResponse(BaseModel):
    """Response schema for a flow template"""

    id: UUID
    name: str
    description: str | None
    category: str | None
    template_definition: dict[str, Any]
    preview_image_url: str | None
    is_public: bool
    use_count: int
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExecutionSummaryResponse(BaseModel):
    """Summary statistics for flow executions"""

    total_executions: int
    successful_executions: int
    failed_executions: int
    running_executions: int
    average_duration_seconds: float | None
    success_rate: float
    last_execution: FlowExecutionResponse | None
