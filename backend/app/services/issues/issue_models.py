"""
Pydantic domain models for the Issues module — F031 Automatic Issue Creation.

These models are the service-layer contract; they are intentionally independent
of the ORM so that repository methods can be tested without a live database.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

# F037 — valid sort column and direction constants
VALID_SORT_COLUMNS = frozenset({"opened_at", "due_at", "severity", "status", "updated_at"})
VALID_SORT_DIRECTIONS = frozenset({"asc", "desc"})


class IssueDomain(BaseModel):
    """Full domain representation of an Issue — used for insert and internal transfer."""

    id: UUID | None = None
    tenant_id: UUID
    workspace_id: UUID
    # F6 — nullable: rule-only executions have no FlowExecution
    flow_execution_id: UUID | None = None
    flow_node_result_id: UUID | None = None
    rule_id: UUID | None = None
    dataset_id: UUID | None = None
    assignee_id: UUID | None = None

    issue_type: str
    severity: str
    status: str = "open"

    title: str
    impact_summary: str | None = None

    failure_count: int | None = None
    rows_scanned: int | None = None
    pass_rate: Decimal | None = None

    due_at: datetime | None = None
    opened_at: datetime | None = None
    last_seen_at: datetime | None = None  # F032: set on grouping update
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class IssueListItem(BaseModel):
    """Slim projection used in paginated list responses."""

    id: UUID
    workspace_id: UUID
    issue_type: str
    severity: str
    status: str
    title: str
    impact_summary: str | None = None
    failure_count: int | None = None
    due_at: datetime | None = None
    opened_at: datetime | None = None
    # F037 — denormalized fields for triage list
    assignee_id: UUID | None = None
    assignee_display_name: str | None = None
    dataset_name: str | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class IssuePage(BaseModel):
    """Paginated list of issues."""

    items: list[IssueListItem]
    total: int
    page: int
    page_size: int
    has_next: bool


class IssueDetail(BaseModel):
    """Full detail view of a single issue — includes all foreign-key IDs."""

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    flow_execution_id: UUID | None = None  # F6
    flow_node_result_id: UUID | None = None
    rule_id: UUID | None = None
    dataset_id: UUID | None = None
    assignee_id: UUID | None = None

    issue_type: str
    severity: str
    status: str

    title: str
    impact_summary: str | None = None
    resolution_summary: str | None = None

    failure_count: int | None = None
    rows_scanned: int | None = None
    pass_rate: Decimal | None = None

    due_at: datetime | None = None
    opened_at: datetime | None = None
    last_seen_at: datetime | None = None  # F032: set on grouping update
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# F035 — Issue Update request model
# ---------------------------------------------------------------------------


class IssueUpdateRequest(BaseModel):
    """
    PATCH request body for issue mutations.

    All fields are optional. Use ``model_fields_set`` to distinguish between
    'field not provided' and 'field explicitly set to null'.
    """

    status: str | None = None
    assignee_id: UUID | None = None
    due_at: datetime | None = None
    resolution_summary: str | None = None


# ---------------------------------------------------------------------------
# F033 — Enrichment summary models for Issue Detail context
# ---------------------------------------------------------------------------


class RuleSummary(BaseModel):
    """Resolved rule context attached to an enriched issue detail."""

    id: UUID
    name: str
    category: str | None = None
    severity: str | None = None
    status: str | None = None
    target_table: str | None = None
    target_columns: list[str] | None = None


class DatasetSummary(BaseModel):
    """Resolved dataset context from control.datasets."""

    dataset_id: UUID
    dataset_name: str
    business_domain: str | None = None
    criticality: str | None = None
    status: str | None = None


class AssigneeSummary(BaseModel):
    """Resolved assignee context from the users table."""

    id: UUID
    display_name: str
    email: str


class FlowExecutionSummary(BaseModel):
    """Resolved execution context for the issue's originating run."""

    id: UUID
    flow_name: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    nodes_total: int | None = None
    nodes_passed: int | None = None
    nodes_failed: int | None = None


class NodeResultSummary(BaseModel):
    """Resolved node result context with metrics from result_data."""

    id: UUID
    node_id: str
    node_type: str | None = None
    status: str | None = None
    rows_scanned: int | None = None
    rows_passed: int | None = None
    rows_failed: int | None = None
    pass_rate: float | None = None
    # F042 (Sprint 4.2) — evidence fields surfaced from result_data
    check_type: str | None = None
    dataset: str | None = None
    table_name: str | None = None
    schema_name: str | None = None
    columns: list[str] | None = None
    threshold: str | None = None
    violations: list[dict[str, Any]] | None = None
    sample_data: list[dict[str, Any]] | None = None


class EnrichedIssueDetail(BaseModel):
    """Full issue detail with resolved context objects — F033 response model."""

    id: UUID
    tenant_id: UUID
    workspace_id: UUID
    flow_execution_id: UUID | None = None  # F6
    flow_node_result_id: UUID | None = None
    rule_id: UUID | None = None
    dataset_id: UUID | None = None
    assignee_id: UUID | None = None

    issue_type: str
    severity: str
    status: str

    title: str
    impact_summary: str | None = None
    resolution_summary: str | None = None

    failure_count: int | None = None
    rows_scanned: int | None = None
    pass_rate: Decimal | None = None

    due_at: datetime | None = None
    opened_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None

    # Enriched context objects (None when referenced entity is missing/deleted)
    rule: RuleSummary | None = None
    dataset: DatasetSummary | None = None
    assignee: AssigneeSummary | None = None
    flow_execution: FlowExecutionSummary | None = None
    node_result: NodeResultSummary | None = None
