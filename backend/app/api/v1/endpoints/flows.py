"""
Flow API Endpoints

This module provides REST API endpoints for flow management:
- CRUD operations for flows
- Flow execution and monitoring
- Flow validation
- Import/export
"""

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies.workspace_auth import (
    WorkspaceActorContext,
    require_workspace_permission,
)
from app.core.config import settings
from app.models.database import get_db
from app.models.flow import DQFlow
from app.models.user import User
from app.schemas.flow import (
    CreateFlowRequest,
    ExecuteFlowRequest,
    FlowExecutionListResponse,
    FlowExecutionResponse,
    FlowListResponse,
    FlowNodeResultResponse,
    FlowResponse,
    FlowValidationResponse,
    ImportFlowRequest,
    UpdateFlowRequest,
    ValidateFlowRequest,
)
from app.services.audit.hooks import build_flow_audit_entry
from app.services.audit.models import AuditContext
from app.services.audit.service import AuditService
from app.services.flows.service import FlowService
from app.services.llm.classifiers.request_classifier import request_classifier
from app.services.llm.flow_builder import flow_builder_llm
from app.services.llm.workflows.complex_flow_builder import complex_flow_builder

router = APIRouter(prefix="/workspaces/{workspace_id}/flows", tags=["flows"])
flow_service = FlowService()
logger = logging.getLogger(__name__)
_audit_svc = AuditService()


@router.post("", response_model=FlowResponse, status_code=status.HTTP_201_CREATED)
async def create_flow(
    workspace_id: UUID,
    request: CreateFlowRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    """Create a new flow"""
    try:
        # TODO: Verify organization access when RBAC is implemented

        flow_resp = flow_service.create_flow(
            db=db, workspace_id=workspace_id, user_id=actor.actor_id, request=request
        )

        # F052 audit hook (best-effort)
        try:
            tenant_id = actor.tenant_id or workspace_id
            _audit_svc.write(
                db,
                build_flow_audit_entry(
                    ctx=AuditContext(
                        tenant_id=tenant_id,
                        actor_id=actor.actor_id,
                        actor_type="user",
                        actor_role=actor.actor_role or "user",
                        request_id=None,
                        source_ip=None,
                    ),
                    action="flow_created",
                    workspace_id=workspace_id,
                    flow_id=flow_resp.id,
                    after_state={
                        "name": flow_resp.name,
                        "status": str(flow_resp.status) if flow_resp.status else None,
                    },
                ),
            )
            db.commit()
        except Exception:
            logger.warning("audit_write_failed action_type=flow_created id=%s", flow_resp.id)

        return flow_resp
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=FlowListResponse)
async def list_flows(
    workspace_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    tags: list[str] | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """List flows with filtering and pagination"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        return flow_service.list_flows(
            db=db,
            workspace_id=workspace_id,
            user_id=actor.actor_id,  # Filter by current user
            status=status_filter,
            tags=tags,
            search=search,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# F115 — List all scheduled flows (must be before /{flow_id} to avoid route shadowing)
from datetime import UTC

from app.schemas.flow import ScheduleConfig


@router.get("/schedules", tags=["flow-schedules"])
async def list_scheduled_flows(
    workspace_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """List all flows with active schedules and their next-run times."""
    from datetime import datetime

    from croniter import croniter

    flows = (
        db.query(DQFlow)
        .filter(
            DQFlow.workspace_id == workspace_id,
            DQFlow.schedule.isnot(None),
        )
        .all()
    )

    results = []
    now = datetime.now(UTC)
    for f in flows:
        sched = f.schedule or {}
        if not sched.get("cron"):
            continue
        try:
            cron = croniter(sched["cron"], now)
            next_run = cron.get_next(datetime).isoformat()
        except Exception:
            next_run = None

        results.append(
            {
                "flow_id": str(f.id),
                "flow_name": f.name,
                "schedule": sched,
                "next_run_at": next_run,
                "status": f.status,
            }
        )

    return {"schedules": results, "total": len(results)}


@router.get("/{flow_id}", response_model=FlowResponse)
async def get_flow(
    workspace_id: UUID,
    flow_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Get flow by ID"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        flow = flow_service.get_flow(db=db, flow_id=flow_id, workspace_id=workspace_id)

        if not flow:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")

        return flow
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch("/{flow_id}", response_model=FlowResponse)
async def update_flow(
    workspace_id: UUID,
    flow_id: UUID,
    request: UpdateFlowRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    """Update a flow"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        return flow_service.update_flow(
            db=db, flow_id=flow_id, workspace_id=workspace_id, request=request
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(
    workspace_id: UUID,
    flow_id: UUID,
    hard_delete: bool = Query(False),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:delete")),
):
    """Delete a flow"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        success = flow_service.delete_flow(
            db=db, flow_id=flow_id, workspace_id=workspace_id, hard_delete=hard_delete
        )

        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ========== Ownership ==========

from pydantic import BaseModel, Field


class AssignFlowOwnerRequest(BaseModel):
    owner_user_id: UUID | None = Field(
        default=None,
        description="User to assign as owner. Use null to clear ownership.",
    )


@router.put("/{flow_id}/owner", summary="Assign or clear the owner of a flow")
async def assign_flow_owner(
    workspace_id: UUID,
    flow_id: UUID,
    request: AssignFlowOwnerRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    flow = (
        db.query(DQFlow).filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id).first()
    )
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    if request.owner_user_id is not None:
        owner = db.query(User).filter(User.id == request.owner_user_id).first()
        if owner is None:
            raise HTTPException(status_code=404, detail="Owner user not found")

    previous_owner = flow.owner_user_id
    flow.owner_user_id = request.owner_user_id
    db.commit()
    db.refresh(flow)

    # Audit (best-effort)
    try:
        tenant_id = actor.tenant_id or workspace_id
        _audit_svc.write(
            db,
            build_flow_audit_entry(
                ctx=AuditContext(
                    tenant_id=tenant_id,
                    actor_id=actor.actor_id,
                    actor_type="user",
                    actor_role=actor.actor_role or "user",
                    request_id=None,
                    source_ip=None,
                ),
                action="flow_owner_changed",
                workspace_id=workspace_id,
                flow_id=flow_id,
                before_state={"owner_user_id": str(previous_owner) if previous_owner else None},
                after_state={
                    "owner_user_id": str(flow.owner_user_id) if flow.owner_user_id else None
                },
            ),
        )
        db.commit()
    except Exception:
        logger.warning("audit_write_failed action_type=flow_owner_changed flow_id=%s", flow_id)

    return {
        "flow_id": str(flow.id),
        "owner_user_id": str(flow.owner_user_id) if flow.owner_user_id else None,
        "previous_owner_user_id": str(previous_owner) if previous_owner else None,
    }


@router.post("/validate", response_model=FlowValidationResponse)
async def validate_flow(
    workspace_id: UUID,
    request: ValidateFlowRequest,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Validate a flow definition"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        return flow_service.validator.validate_flow(request.flow_definition)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/ai-build")
async def ai_build_flow(
    workspace_id: UUID,
    request: dict,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    """
    AI-powered flow building with adaptive complexity handling.

    Automatically routes to simple or complex handler based on request analysis.

    Request body:
    {
        "prompt": "Apply completeness check on email and age columns with 90% threshold",
        "current_flow": {
            "nodes": [...],
            "connections": [...]
        },
        "available_data_sources": [...]
    }

    Response:
    {
        "success": true,
        "needs_clarification": false,
        "clarification_questions": [],
        "suggested_data_sources": [...],  // If requesting data source
        "flow_updates": {
            "nodes": [...],
            "connections": [...]
        },
        "message": "Added completeness check...",
        "classification": {
            "complexity": "simple" | "complex",
            "instruction_count": int,
            "confidence": float
        }
    }
    """
    try:
        logger.info(f"🎯 AI Build Flow API called - Org: {workspace_id}, User: {actor.actor_id}")
        # Verify organization access
        # TODO: Verify organization access

        prompt = request.get("prompt", "")
        current_flow = request.get("current_flow", {"nodes": [], "connections": []})
        available_data_sources = request.get("available_data_sources", [])

        logger.info(
            f"📥 Request data - Prompt length: {len(prompt)}, "
            f"Nodes: {len(current_flow.get('nodes', []))}, "
            f"Connections: {len(current_flow.get('connections', []))}, "
            f"Data sources: {len(available_data_sources)}"
        )

        if not prompt:
            logger.warning("⚠️ Empty prompt received")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Prompt is required"
            )

        # Classify request complexity
        classification = request_classifier.classify(prompt)

        logger.info(
            f"📊 Request classified: {classification['complexity']} "
            f"({classification['instruction_count']} instructions, "
            f"confidence: {classification['confidence']:.2f})"
        )

        # Route to appropriate handler
        # Use complex flow builder for complex requests OR when complex builder is enabled for all
        if classification["complexity"] == "complex" or settings.ENABLE_COMPLEX_FLOW_BUILDER:
            # Use complex LangGraph flow builder
            logger.info("🚀 Routing to complex flow builder (LangGraph)")
            result = await complex_flow_builder.generate_flow_update(
                prompt=prompt,
                current_flow=current_flow,
                available_data_sources=available_data_sources,
            )
        else:
            # Use existing simple flow builder
            logger.info("🚀 Routing to simple flow builder")
            result = await flow_builder_llm.generate_flow_update(
                prompt=prompt,
                current_flow=current_flow,
                available_data_sources=available_data_sources,
            )

        # Add classification metadata
        result["classification"] = classification

        logger.info(f"📤 Returning result - Success: {result.get('success')}")
        return result

    except HTTPException as he:
        logger.error(f"❌ HTTP Exception in AI flow building: {he.status_code} - {he.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error in AI flow building: {type(e).__name__}: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__}: {str(e)}",
        )


@router.post(
    "/{flow_id}/duplicate", response_model=FlowResponse, status_code=status.HTTP_201_CREATED
)
async def duplicate_flow(
    workspace_id: UUID,
    flow_id: UUID,
    new_name: str | None = Query(None),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    """Duplicate a flow"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        return flow_service.duplicate_flow(
            db=db,
            flow_id=flow_id,
            workspace_id=workspace_id,
            user_id=actor.actor_id,
            new_name=new_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{flow_id}/execute", response_model=FlowExecutionResponse)
async def execute_flow(
    workspace_id: UUID,
    flow_id: UUID,
    background_tasks: BackgroundTasks,
    request: ExecuteFlowRequest | None = None,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:execute")),
):
    """Execute a flow asynchronously"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        # Start async execution and return immediately with execution record
        return await flow_service.execute_flow_async(
            db=db,
            flow_id=flow_id,
            workspace_id=workspace_id,
            user_id=actor.actor_id,
            background_tasks=background_tasks,
            request=request,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{flow_id}/executions", response_model=FlowExecutionListResponse)
async def get_execution_history(
    workspace_id: UUID,
    flow_id: UUID,
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Get execution history for a flow"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        return flow_service.get_execution_history(
            db=db,
            flow_id=flow_id,
            workspace_id=workspace_id,
            status=status_filter,
            page=page,
            page_size=page_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{flow_id}/export")
async def export_flow(
    workspace_id: UUID,
    flow_id: UUID,
    format: str = Query("json", pattern="^(json|yaml)$"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Export flow as JSON or YAML"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        exported_data = flow_service.export_flow(
            db=db, flow_id=flow_id, workspace_id=workspace_id, format=format
        )

        # Return as plain text with appropriate content type
        from fastapi.responses import Response

        content_type = "application/json" if format == "json" else "text/yaml"

        return Response(
            content=exported_data,
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename=flow-{flow_id}.{format}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/import", response_model=FlowResponse, status_code=status.HTTP_201_CREATED)
async def import_flow(
    workspace_id: UUID,
    request: ImportFlowRequest,
    format: str = Query("json", pattern="^(json|yaml)$"),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    """Import flow from JSON or YAML"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        # Convert request to flow data string
        import json

        import yaml

        flow_data_dict = {
            "name": request.name,
            "description": request.description,
            "flow_definition": request.flow_definition.dict(),
            "tags": request.tags or [],
        }

        if format == "json":
            flow_data = json.dumps(flow_data_dict)
        else:
            flow_data = yaml.dump(flow_data_dict)

        return flow_service.import_flow(
            db=db,
            workspace_id=workspace_id,
            user_id=actor.actor_id,
            flow_data=flow_data,
            format=format,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# Execution endpoints (under /executions for cross-flow queries)
execution_router = APIRouter(
    prefix="/workspaces/{workspace_id}/flow-executions", tags=["flow-executions"]
)


@execution_router.get("", response_model=FlowExecutionListResponse)
async def list_all_executions(
    workspace_id: UUID,
    execution_status: str | None = Query(None, description="Filter by status", alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """List all flow executions for the organization (across all flows)"""
    try:
        return flow_service.get_all_executions(
            db=db,
            workspace_id=workspace_id,
            status=execution_status,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@execution_router.get("/{execution_id}", response_model=FlowExecutionResponse)
async def get_execution(
    workspace_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Get execution details"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        execution = flow_service.get_execution(
            db=db, execution_id=execution_id, workspace_id=workspace_id
        )

        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        return execution
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@execution_router.get("/{execution_id}/nodes", response_model=list[FlowNodeResultResponse])
async def get_node_results(
    workspace_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Get node results for an execution"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        return flow_service.get_node_results(
            db=db, execution_id=execution_id, workspace_id=workspace_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@execution_router.delete("/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_execution(
    workspace_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:execute")),
):
    """Cancel a running execution"""
    try:
        # Verify organization access
        # TODO: Verify organization access

        success = await flow_service.cancel_execution(
            db=db, execution_id=execution_id, workspace_id=workspace_id
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Execution not found or not running"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@execution_router.get("/{execution_id}/report")
async def get_execution_report(
    workspace_id: UUID,
    execution_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """
    Get the detailed execution report

    Returns a comprehensive report including:
    - Execution summary
    - Quality score
    - Node-by-node results
    - Violations and failures
    """
    try:
        from app.models.flow import FlowExecution

        # Get execution
        execution = db.query(FlowExecution).filter(FlowExecution.id == execution_id).first()

        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        # Check if report exists
        result_summary = execution.result_summary or {}
        report = result_summary.get("detailed_report")

        if not report:
            # Report not yet generated, trigger generation
            from app.workers.tasks.flows import generate_execution_report

            generate_execution_report.delay(str(execution_id), str(workspace_id))

            # Return basic summary while report is being generated
            return {
                "status": "generating",
                "message": "Report is being generated. Please check back in a few seconds.",
                "execution_id": str(execution_id),
                "basic_summary": {
                    "status": execution.status,
                    "nodes_executed": execution.nodes_executed,
                    "nodes_passed": execution.nodes_passed,
                    "nodes_failed": execution.nodes_failed,
                    "duration_seconds": execution.duration_seconds,
                },
            }

        return {"status": "ready", "report": report}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ========================================================================
# F115 — Flow Schedule (per-flow endpoints)
# ========================================================================


@router.get("/{flow_id}/schedule", tags=["flow-schedules"])
async def get_flow_schedule(
    workspace_id: UUID,
    flow_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Get schedule configuration for a specific flow."""
    from datetime import datetime

    from croniter import croniter

    flow = (
        db.query(DQFlow)
        .filter(
            DQFlow.id == flow_id,
            DQFlow.workspace_id == workspace_id,
        )
        .first()
    )
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    sched = flow.schedule or {}
    next_run = None
    if sched.get("cron"):
        try:
            cron = croniter(sched["cron"], datetime.now(UTC))
            next_run = cron.get_next(datetime).isoformat()
        except Exception:
            pass

    return {
        "flow_id": str(flow_id),
        "schedule": sched if sched else None,
        "next_run_at": next_run,
    }


@router.put("/{flow_id}/schedule", tags=["flow-schedules"])
async def set_flow_schedule(
    workspace_id: UUID,
    flow_id: UUID,
    payload: ScheduleConfig,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:write")),
):
    """Set or update the schedule for a flow."""
    from croniter import croniter

    if not croniter.is_valid(payload.cron):
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {payload.cron}")

    flow = (
        db.query(DQFlow)
        .filter(
            DQFlow.id == flow_id,
            DQFlow.workspace_id == workspace_id,
        )
        .first()
    )
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow.schedule = payload.model_dump()
    db.commit()
    db.refresh(flow)
    return {"flow_id": str(flow_id), "schedule": flow.schedule}


@router.delete("/{flow_id}/schedule", tags=["flow-schedules"])
async def remove_flow_schedule(
    workspace_id: UUID,
    flow_id: UUID,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:delete")),
):
    """Remove the schedule from a flow."""
    flow = (
        db.query(DQFlow)
        .filter(
            DQFlow.id == flow_id,
            DQFlow.workspace_id == workspace_id,
        )
        .first()
    )
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow.schedule = None
    db.commit()
    return {"flow_id": str(flow_id), "schedule": None}


@router.post("/{flow_id}/schedule/validate", tags=["flow-schedules"])
async def validate_cron_expression(
    workspace_id: UUID,
    flow_id: UUID,
    payload: ScheduleConfig,
    db: Session = Depends(get_db),
    actor: WorkspaceActorContext = Depends(require_workspace_permission("flows:read")),
):
    """Validate a cron expression and return the next 5 run times."""
    from datetime import datetime

    from croniter import croniter

    if not croniter.is_valid(payload.cron):
        return {
            "valid": False,
            "error": f"Invalid cron expression: {payload.cron}",
            "next_runs": [],
        }

    now = datetime.now(UTC)
    cron = croniter(payload.cron, now)
    next_runs = [cron.get_next(datetime).isoformat() for _ in range(5)]

    return {
        "valid": True,
        "cron": payload.cron,
        "timezone": payload.timezone,
        "next_runs": next_runs,
    }
