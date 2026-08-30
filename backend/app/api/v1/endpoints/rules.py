"""
Rule Management API Endpoints
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.core.config import get_settings
from app.core.logging_config import logger
from app.models.database import get_db
from app.models.rule import DQRule
from app.models.user import User
from app.schemas.rule import (
    BulkExecuteRequest,
    BulkExecuteResponse,
    CreateRuleRequest,
    ExecuteRuleRequest,
    ExecutionResponse,
    ExecutionStatus,
    ExecutionSummary,
    RuleResponse,
    RuleStatus,
    ScheduleConfig,
    UpdateRuleRequest,
    ViolationResponse,
)
from app.services.audit.hooks import build_rule_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.rules.change_history_models import RuleChangeQueryParams
from app.services.rules.change_history_service import RuleChangeHistoryService
from app.services.rules.service import RuleService
from app.services.sync.rule_flow_sync import propagate_rule_to_flows

router = APIRouter()
settings = get_settings()
_audit_svc = AuditService()
_history_svc = RuleChangeHistoryService()


def get_rule_service(db: Session = Depends(get_db)) -> RuleService:
    """Dependency to get RuleService instance"""
    return RuleService(db)


# ========== Rule CRUD Endpoints ==========


@router.post(
    "/workspaces/{workspace_id}/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new data quality rule",
    description="Create a new rule with canonical definition and compile to SQL/Spark",
)
async def create_rule(
    workspace_id: UUID,
    request: CreateRuleRequest,
    db: Session = Depends(get_db),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:write")),
):
    """Create a new data quality rule"""
    try:
        created_by = actor.actor_id
        rule = await service.create_rule(request, created_by, workspace_id)

        # F052 audit hook (best-effort)
        try:
            tenant_id = actor.tenant_id or workspace_id
            _audit_svc.write(
                db,
                build_rule_audit_entry(
                    ctx=AuditContext(
                        tenant_id=tenant_id,
                        actor_id=actor.actor_id,
                        actor_type="user",
                        actor_role=actor.actor_role or "user",
                        request_id=None,
                        source_ip=None,
                    ),
                    action="rule_created",
                    workspace_id=workspace_id,
                    rule_id=rule.id,
                    after_state={
                        "name": rule.name,
                        "category": rule.category,
                        "severity": (rule.canonical_rule or {}).get("severity")
                        if isinstance(rule.canonical_rule, dict)
                        else None,
                    },
                ),
            )
            db.commit()
        except Exception:
            logger.warning("audit_write_failed action_type=rule_created rule_id=%s", rule.id)

        return rule

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating rule: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create rule"
        )


@router.get(
    "/workspaces/{workspace_id}/rules",
    response_model=list[RuleResponse],
    summary="List data quality rules",
    description="List all rules for an organization with optional filtering",
)
async def list_rules(
    workspace_id: UUID,
    data_source_id: UUID | None = Query(None, description="Filter by data source"),
    category: str | None = Query(
        None, description="Filter by category (completeness, validity, etc)"
    ),
    status: RuleStatus | None = Query(None, description="Filter by status"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Search in name and description"),
    tags: list[str] | None = Query(None, description="Filter by tags (OR logic)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """List rules with filtering and pagination"""
    try:
        rules = await service.list_rules(
            workspace_id=workspace_id,
            data_source_id=data_source_id,
            category=category,
            status=status,
            is_active=is_active,
            search=search,
            tags=tags,
            skip=skip,
            limit=limit,
        )
        return rules

    except Exception:
        logger.exception("Error listing rules")
        raise HTTPException(status_code=500, detail="Failed to list rules")


@router.get(
    "/workspaces/{workspace_id}/rules/{rule_id}",
    response_model=RuleResponse,
    summary="Get a specific rule",
    description="Get rule details by ID",
)
async def get_rule(
    workspace_id: UUID,
    rule_id: UUID,
    include_executions: bool = Query(False, description="Include execution history"),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Get rule by ID"""
    rule = await service.get_rule(
        rule_id=rule_id, workspace_id=workspace_id, include_executions=include_executions
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found"
        )

    return rule


@router.patch(
    "/workspaces/{workspace_id}/rules/{rule_id}",
    response_model=RuleResponse,
    summary="Update a rule",
    description="Update rule fields. If canonical_rule is changed, rule will be recompiled.",
)
async def update_rule(
    workspace_id: UUID,
    rule_id: UUID,
    request: UpdateRuleRequest,
    db: Session = Depends(get_db),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:write")),
):
    """Update an existing rule"""
    try:
        # Capture before_state for audit diff (P04-AC-02)
        original = await service.get_rule(
            rule_id=rule_id,
            workspace_id=workspace_id,
        )

        rule = await service.update_rule(
            rule_id=rule_id, workspace_id=workspace_id, request=request
        )

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found"
            )

        # Rule → Flow sync: push changes into every flow node linked to this
        # rule. Best-effort; failures here must not fail the rule update.
        try:
            rule_row = (
                db.query(DQRule)
                .filter(DQRule.id == rule_id, DQRule.workspace_id == workspace_id)
                .first()
            )
            if rule_row is not None:
                propagate_rule_to_flows(db, workspace_id, rule_row)
        except Exception:
            logger.warning("rule_to_flow_sync_skipped rule_id=%s", rule_id, exc_info=True)

        # F052 audit hook (best-effort)
        try:
            tenant_id = actor.tenant_id or workspace_id
            before_state = {"name": original.name} if original else None
            _audit_svc.write(
                db,
                build_rule_audit_entry(
                    ctx=AuditContext(
                        tenant_id=tenant_id,
                        actor_id=actor.actor_id,
                        actor_type="user",
                        actor_role=actor.actor_role or "user",
                        request_id=None,
                        source_ip=None,
                    ),
                    action="rule_updated",
                    workspace_id=workspace_id,
                    rule_id=rule_id,
                    before_state=before_state,
                    after_state={"name": rule.name},
                ),
            )
            db.commit()
        except Exception:
            logger.warning("audit_write_failed action_type=rule_updated rule_id=%s", rule_id)

        return rule

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating rule {rule_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update rule"
        )


@router.delete(
    "/workspaces/{workspace_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a rule",
    description="Delete a rule (soft delete by default, set hard_delete=true for permanent deletion)",
)
async def delete_rule(
    workspace_id: UUID,
    rule_id: UUID,
    hard_delete: bool = Query(False, description="Permanent deletion (default: soft delete)"),
    db: Session = Depends(get_db),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:delete")),
):
    """Delete a rule"""
    try:
        deleted = await service.delete_rule(
            rule_id=rule_id, workspace_id=workspace_id, soft_delete=not hard_delete
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found"
            )

        # F052 audit hook (best-effort)
        try:
            tenant_id = actor.tenant_id or workspace_id
            _audit_svc.write(
                db,
                build_rule_audit_entry(
                    ctx=AuditContext(
                        tenant_id=tenant_id,
                        actor_id=actor.actor_id,
                        actor_type="user",
                        actor_role=actor.actor_role or "user",
                        request_id=None,
                        source_ip=None,
                    ),
                    action="rule_deleted",
                    workspace_id=workspace_id,
                    rule_id=rule_id,
                    after_state={"deleted": True},
                ),
            )
            db.commit()
        except Exception:
            logger.warning("audit_write_failed action_type=rule_deleted rule_id=%s", rule_id)

        return None

    except Exception as e:
        logger.error(f"Error deleting rule {rule_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete rule"
        )


# ========== Ownership Endpoints ==========


class AssignRuleOwnerRequest(BaseModel):
    owner_user_id: UUID | None = Field(
        default=None,
        description="User to assign as owner. Use null to clear ownership.",
    )


@router.put(
    "/workspaces/{workspace_id}/rules/{rule_id}/owner",
    summary="Assign or clear the owner of a rule",
    description="Sets `dq_rules.owner_user_id`. Pass null to clear.",
)
async def assign_rule_owner(
    workspace_id: UUID,
    rule_id: UUID,
    request: AssignRuleOwnerRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:write")),
):
    rule = (
        db.query(DQRule).filter(DQRule.id == rule_id, DQRule.workspace_id == workspace_id).first()
    )
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    if request.owner_user_id is not None:
        owner = db.query(User).filter(User.id == request.owner_user_id).first()
        if owner is None:
            raise HTTPException(status_code=404, detail="Owner user not found")

    previous_owner = rule.owner_user_id
    rule.owner_user_id = request.owner_user_id
    rule.updated_by = actor.actor_id
    db.commit()
    db.refresh(rule)

    # Audit (best-effort)
    try:
        tenant_id = actor.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_rule_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="rule_owner_changed",
                workspace_id=workspace_id,
                rule_id=rule_id,
                before_state={"owner_user_id": str(previous_owner) if previous_owner else None},
                after_state={
                    "owner_user_id": str(rule.owner_user_id) if rule.owner_user_id else None
                },
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=rule_owner_changed rule_id=%s", rule_id)

    return {
        "rule_id": str(rule.id),
        "owner_user_id": str(rule.owner_user_id) if rule.owner_user_id else None,
        "previous_owner_user_id": str(previous_owner) if previous_owner else None,
    }


# ========== Execution Endpoints ==========


@router.post(
    "/workspaces/{workspace_id}/rules/{rule_id}/execute",
    response_model=ExecutionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute a rule",
    description="Trigger rule execution against the data source",
)
async def execute_rule(
    workspace_id: UUID,
    rule_id: UUID,
    request: ExecuteRuleRequest,
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:execute")),
):
    """Execute a data quality rule"""
    try:
        executed_by = actor.actor_id

        execution = await service.execute_rule(
            rule_id=rule_id, workspace_id=workspace_id, request=request, executed_by=executed_by
        )
        return execution

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error executing rule {rule_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to execute rule"
        )


@router.get(
    "/workspaces/{workspace_id}/rules/{rule_id}/executions",
    response_model=list[ExecutionResponse],
    summary="Get rule execution history",
    description="Retrieve execution history for a rule",
)
async def get_execution_history(
    workspace_id: UUID,
    rule_id: UUID,
    status: ExecutionStatus | None = Query(None, description="Filter by execution status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Get execution history for a rule"""
    try:
        executions = await service.get_execution_history(
            rule_id=rule_id, workspace_id=workspace_id, status=status, skip=skip, limit=limit
        )
        return executions

    except Exception as e:
        logger.error(f"Error getting execution history for rule {rule_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve execution history",
        )


@router.get(
    "/workspaces/{workspace_id}/executions/{execution_id}",
    response_model=ExecutionResponse,
    summary="Get execution details",
    description="Get details of a specific execution",
)
async def get_execution(
    workspace_id: UUID,
    execution_id: UUID,
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Get execution by ID"""
    execution = await service.get_execution(execution_id=execution_id, workspace_id=workspace_id)

    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution {execution_id} not found"
        )

    return execution


@router.get(
    "/workspaces/{workspace_id}/executions/{execution_id}/violations",
    response_model=list[ViolationResponse],
    summary="Get execution violations",
    description="Retrieve violations detected during rule execution",
)
async def get_violations(
    workspace_id: UUID,
    execution_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Get violations for an execution"""
    try:
        violations = await service.get_violations(
            execution_id=execution_id, workspace_id=workspace_id, skip=skip, limit=limit
        )
        return violations

    except Exception as e:
        logger.error(
            f"Error getting violations for execution {execution_id}: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve violations",
        )


@router.delete(
    "/workspaces/{workspace_id}/executions/{execution_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel execution",
    description="Cancel a pending or running execution",
)
async def cancel_execution(
    workspace_id: UUID,
    execution_id: UUID,
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:execute")),
):
    """Cancel a running execution"""
    try:
        cancelled = await service.cancel_execution(
            execution_id=execution_id, workspace_id=workspace_id
        )

        if not cancelled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execution {execution_id} not found or cannot be cancelled",
            )

        return None

    except Exception as e:
        logger.error(f"Error cancelling execution {execution_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel execution"
        )


# ========== Bulk Operations ==========


@router.post(
    "/workspaces/{workspace_id}/rules/bulk-execute",
    response_model=BulkExecuteResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Execute multiple rules",
    description="Execute multiple rules in parallel",
)
async def bulk_execute(
    workspace_id: UUID,
    request: BulkExecuteRequest,
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:execute")),
):
    """Execute multiple rules"""
    try:
        executed_by = actor.actor_id

        result = await service.bulk_execute(
            request=request, workspace_id=workspace_id, executed_by=executed_by
        )
        return result

    except Exception as e:
        logger.error(f"Error in bulk execute: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute rules in bulk",
        )


# ========== Statistics & Summary ==========


@router.get(
    "/workspaces/{workspace_id}/rules/summary",
    response_model=ExecutionSummary,
    summary="Get execution summary",
    description="Get summary statistics for rule executions",
)
async def get_execution_summary(
    workspace_id: UUID,
    rule_id: UUID | None = Query(None, description="Filter by specific rule"),
    days: int = Query(30, ge=1, le=365, description="Number of days to include"),
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Get execution summary statistics"""
    try:
        summary = await service.get_execution_summary(
            workspace_id=workspace_id, rule_id=rule_id, days=days
        )
        return summary

    except Exception as e:
        logger.error(f"Error getting execution summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve execution summary",
        )


# ========== Scheduling ==========


@router.post(
    "/workspaces/{workspace_id}/rules/{rule_id}/schedule",
    response_model=RuleResponse,
    summary="Schedule rule execution",
    description="Set up automatic execution schedule for a rule",
)
async def schedule_rule(
    workspace_id: UUID,
    rule_id: UUID,
    schedule: ScheduleConfig,
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:write")),
):
    """Schedule automatic rule execution"""
    try:
        rule = await service.schedule_rule(
            rule_id=rule_id, workspace_id=workspace_id, schedule=schedule
        )

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found"
            )

        return rule

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error scheduling rule {rule_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to schedule rule"
        )


@router.delete(
    "/workspaces/{workspace_id}/rules/{rule_id}/schedule",
    response_model=RuleResponse,
    summary="Remove schedule",
    description="Remove automatic execution schedule from a rule",
)
async def unschedule_rule(
    workspace_id: UUID,
    rule_id: UUID,
    service: RuleService = Depends(get_rule_service),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:write")),
):
    """Remove schedule from rule"""
    try:
        rule = await service.unschedule_rule(rule_id=rule_id, workspace_id=workspace_id)

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found"
            )

        return rule

    except Exception as e:
        logger.error(f"Error unscheduling rule {rule_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove schedule"
        )


# ========== F054 — Rule Change History ==========


@router.get(
    "/workspaces/{workspace_id}/rules/{rule_id}/history",
    summary="Get rule change history",
    description="Return paginated change history for a rule from the audit log",
)
async def get_rule_change_history(
    workspace_id: UUID,
    rule_id: UUID,
    action_type: str | None = Query(None, description="Filter by action type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:read")),
):
    """Return paginated rule change history from audit log."""
    tenant_id = actor.tenant_id or workspace_id
    filters = RuleChangeQueryParams(
        action_type=action_type,
        page=page,
        page_size=page_size,
    )
    result = _history_svc.get_page(
        session=db,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        rule_id=rule_id,
        filters=filters,
    )
    return result


# ========== Build Flow from Rules ==========


class BuildFlowFromRulesRequest(BaseModel):
    rule_ids: list[str] = Field(..., min_length=1, description="Rule IDs to build flow from")
    flow_name: str | None = Field(None, max_length=255, description="Custom flow name")


@router.post(
    "/workspaces/{workspace_id}/rules/build-flow",
    status_code=status.HTTP_201_CREATED,
    summary="Build a DQ flow from one or more rules",
    description="Generates a DQ flow with source and check nodes from the selected rules' canonical definitions",
)
async def build_flow_from_rules(
    workspace_id: UUID,
    request: BuildFlowFromRulesRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("rules:write")),
):
    """Build a flow automatically from one or more rules."""
    from sqlalchemy import text as _sql_text

    from app.schemas.nl_compiler import CompiledCheckConfig
    from app.schemas.nl_flow_generator import GenerateFlowRequest
    from app.services.nl_flow_generator.generator import NLFlowGenerator

    # Load rules
    rules = (
        db.query(DQRule)
        .filter(
            DQRule.id.in_(request.rule_ids),
            DQRule.workspace_id == workspace_id,
        )
        .all()
    )

    if not rules:
        raise HTTPException(status_code=404, detail="No rules found for the given IDs")

    def _resolve_dataset_id(
        candidate: str | None,
        rule: DQRule,
    ) -> str | None:
        """Return a workspace dataset_id (control.datasets.dataset_id).

        Resolution order:
          1. ``candidate`` if it already maps to a dataset in this workspace.
          2. Lookup by (workspace_id, physical_identifier=target_table)
             — optionally filtered by schema_name when present.
          3. Lookup by (workspace_id, dataset_name=target_table).
        """
        if candidate:
            try:
                row = db.execute(
                    _sql_text(
                        "SELECT dataset_id FROM control.datasets "
                        "WHERE dataset_id = CAST(:id AS UUID) "
                        "AND workspace_id = CAST(:ws AS UUID) LIMIT 1"
                    ),
                    {"id": str(candidate), "ws": str(workspace_id)},
                ).fetchone()
                if row:
                    return str(row[0])
            except Exception:
                pass

        target_table = rule.target_table
        target_schema = rule.target_schema
        if not target_table:
            return None
        try:
            if target_schema:
                row = db.execute(
                    _sql_text(
                        "SELECT dataset_id FROM control.datasets "
                        "WHERE workspace_id = CAST(:ws AS UUID) "
                        "AND lower(physical_identifier) = lower(:t) "
                        "AND lower(schema_name) = lower(:s) LIMIT 1"
                    ),
                    {"ws": str(workspace_id), "t": target_table, "s": target_schema},
                ).fetchone()
                if row:
                    return str(row[0])
            row = db.execute(
                _sql_text(
                    "SELECT dataset_id FROM control.datasets "
                    "WHERE workspace_id = CAST(:ws AS UUID) "
                    "AND (lower(physical_identifier) = lower(:t) "
                    "     OR lower(dataset_name) = lower(:t)) "
                    "LIMIT 1"
                ),
                {"ws": str(workspace_id), "t": target_table},
            ).fetchone()
            if row:
                return str(row[0])
        except Exception:
            return None
        return None

    # Convert rules into compiled check configs
    compiled_configs = []
    rule_texts = []
    for rule in rules:
        cr = rule.canonical_rule or {}
        meta = rule.meta_data or {}
        check_configs = meta.get("check_configs", [])

        if check_configs:
            # Use stored check configs from NL builder
            for cc in check_configs:
                resolved_ds_id = _resolve_dataset_id(cc.get("dataset_id"), rule)
                if not resolved_ds_id:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Cannot build flow: rule '{rule.name}' has no resolvable "
                            f"dataset (target_table={rule.target_table!r}). "
                            f"Attach the rule to a workspace dataset first."
                        ),
                    )
                compiled_configs.append(
                    CompiledCheckConfig(
                        check_type=cc.get("check_dimension", rule.category or "completeness"),
                        subtype=cc.get("check_subtype", rule.rule_type or "null_check"),
                        dataset_id=resolved_ds_id,
                        rule_name=cc.get("rule_name") or rule.name,
                        severity=cc.get("severity", cr.get("severity", "medium")),
                        description=cc.get("description") or rule.description,
                        rule_id=str(rule.id),
                        config={
                            **cc.get("config", {}),
                            "dataset_name": cc.get("dataset_name") or rule.target_table,
                            "columns": cc.get("columns", rule.target_columns or []),
                            "thresholds": cc.get("thresholds", {}),
                        },
                    )
                )
        else:
            # Build from canonical rule
            resolved_ds_id = _resolve_dataset_id(None, rule)
            if not resolved_ds_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot build flow: rule '{rule.name}' has no resolvable "
                        f"dataset (target_table={rule.target_table!r}). "
                        f"Attach the rule to a workspace dataset first."
                    ),
                )
            cr_params = cr.get("parameters", {}) or {}
            # Prefer canonical-parameter subtype/dimension over the legacy
            # ``condition`` string (which is a SQL fragment, not a subtype).
            check_dim = (
                cr_params.get("check_dimension")
                or cr.get("dimension")
                or rule.category
                or "completeness"
            )
            check_subtype = (
                cr_params.get("check_subtype")
                or cr_params.get("check_mode")
                or rule.rule_type
                or "null"
            )
            base_config = {k: v for k, v in cr_params.items() if k != "columns"}
            base_config.update(
                {
                    "dataset_name": rule.target_table,
                    "columns": rule.target_columns or [],
                }
            )
            compiled_configs.append(
                CompiledCheckConfig(
                    check_type=check_dim,
                    subtype=check_subtype,
                    dataset_id=resolved_ds_id,
                    rule_name=rule.name,
                    severity=cr.get("severity", "medium"),
                    description=rule.description,
                    rule_id=str(rule.id),
                    config=base_config,
                )
            )
        rule_texts.append(rule.name)

    # Generate flow
    flow_name = request.flow_name or f"Rules: {', '.join(rule_texts)[:80]}"
    gen_request = GenerateFlowRequest(
        compiled_configs=compiled_configs,
        flow_name=flow_name,
        flow_description=f"Auto-generated from {len(rules)} rule(s)",
        nl_rule_text="; ".join(rule_texts),
    )

    generator = NLFlowGenerator()
    result = generator.generate(db, workspace_id, actor.actor_id, gen_request)
    return result
