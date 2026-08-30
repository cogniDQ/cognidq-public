"""
Flow Service - Main service for flow management

This module provides high-level flow operations:
- Create, update, delete flows
- Execute flows
- Manage flow schedules
- Query execution history
- Export/import flows
"""

import copy
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.flow import (
    CreateFlowRequest,
    ExecuteFlowRequest,
    FlowExecutionListResponse,
    FlowExecutionResponse,
    FlowListResponse,
    FlowNodeResultResponse,
    FlowResponse,
    FlowStatus,
    UpdateFlowRequest,
)
from app.services.flows.executor import FlowExecutor
from app.services.flows.validator import FlowValidator
from app.services.flows.visual_builder import VisualFlowBuilder
from app.services.sync.rule_flow_sync import propagate_flow_to_rules

logger = logging.getLogger(__name__)


class FlowService:
    """Service for flow management"""

    def __init__(self):
        """Initialize the flow service"""
        self.validator = FlowValidator()
        self.executor = FlowExecutor()
        self.builder = VisualFlowBuilder()

    def create_flow(
        self, db: Session, workspace_id: UUID, user_id: UUID, request: CreateFlowRequest
    ) -> FlowResponse:
        """
        Create a new flow

        Args:
            db: Database session
            workspace_id: Organization ID
            user_id: User creating the flow
            request: Flow creation request

        Returns:
            FlowResponse
        """
        # Validate flow definition
        strict_validation = request.status != FlowStatus.DRAFT
        validation = self.validator.validate_flow(request.flow_definition, strict=strict_validation)
        if not validation.is_valid:
            raise ValueError(f"Invalid flow definition: {validation.errors}")

        # Create flow
        flow = DQFlow(
            workspace_id=workspace_id,
            name=request.name,
            description=request.description,
            flow_definition=request.flow_definition.dict(),
            status=request.status.value,
            schedule=request.schedule.dict() if request.schedule else None,
            tags=request.tags,
            created_by=user_id,
            owner_user_id=user_id,
        )

        db.add(flow)
        db.commit()
        db.refresh(flow)

        return FlowResponse.from_orm(flow)

    def update_flow(
        self, db: Session, flow_id: UUID, workspace_id: UUID, request: UpdateFlowRequest
    ) -> FlowResponse:
        """
        Update an existing flow

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID
            request: Flow update request

        Returns:
            FlowResponse
        """
        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            raise ValueError(f"Flow {flow_id} not found")

        # Snapshot the prior definition so we can diff check-node configs and
        # mirror edits back to their originating rules after commit.
        old_definition = copy.deepcopy(flow.flow_definition or {})

        # Update fields
        if request.name is not None:
            flow.name = request.name
        if request.description is not None:
            flow.description = request.description
        if request.flow_definition is not None:
            # Clean up orphaned connections for draft flows
            current_status = request.status.value if request.status else flow.status
            if current_status == FlowStatus.DRAFT.value:
                request.flow_definition = self._cleanup_orphaned_connections(
                    request.flow_definition
                )

            # Validate new flow definition
            # Use lenient validation for draft flows
            strict_validation = current_status != FlowStatus.DRAFT.value
            validation = self.validator.validate_flow(
                request.flow_definition, strict=strict_validation
            )
            if not validation.is_valid:
                raise ValueError(f"Invalid flow definition: {validation.errors}")
            flow.flow_definition = request.flow_definition.dict()
            flow.version += 1
        if request.status is not None:
            flow.status = request.status.value
        if request.is_active is not None:
            flow.is_active = request.is_active
        if request.schedule is not None:
            flow.schedule = request.schedule.dict()
        if request.tags is not None:
            flow.tags = request.tags

        flow.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(flow)

        # Flow → Rule sync: mirror node config edits back into the source
        # rules. Best-effort; failures must not abort the flow update.
        try:
            if request.flow_definition is not None:
                propagate_flow_to_rules(
                    db,
                    workspace_id,
                    old_definition,
                    flow.flow_definition,
                )
        except Exception:
            logger.warning("flow_to_rule_sync_skipped flow_id=%s", flow_id, exc_info=True)

        return FlowResponse.from_orm(flow)

    def delete_flow(
        self, db: Session, flow_id: UUID, workspace_id: UUID, hard_delete: bool = False
    ) -> bool:
        """
        Delete a flow

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID
            hard_delete: If True, permanently delete. If False, soft delete (mark as archived)

        Returns:
            True if deleted
        """
        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            return False

        if hard_delete:
            db.delete(flow)
        else:
            flow.status = "archived"
            flow.is_active = False
            flow.updated_at = datetime.utcnow()

        db.commit()
        return True

    def get_flow(self, db: Session, flow_id: UUID, workspace_id: UUID) -> FlowResponse | None:
        """
        Get a flow by ID

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID

        Returns:
            FlowResponse or None
        """
        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            return None

        return FlowResponse.from_orm(flow)

    def list_flows(
        self,
        db: Session,
        workspace_id: UUID,
        user_id: UUID | None = None,
        status: str | None = None,
        tags: list[str] | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> FlowListResponse:
        """
        List flows with filtering and pagination

        Args:
            db: Database session
            workspace_id: Organization ID
            user_id: Filter by creator (optional)
            status: Filter by status
            tags: Filter by tags
            search: Search in name/description
            page: Page number (1-indexed)
            page_size: Page size

        Returns:
            FlowListResponse
        """
        query = db.query(DQFlow).filter(DQFlow.workspace_id == workspace_id)

        # Filter by creator if provided
        if user_id:
            query = query.filter(DQFlow.created_by == user_id)

        # Apply filters
        if status:
            query = query.filter(DQFlow.status == status)
        if tags:
            query = query.filter(DQFlow.tags.overlap(tags))
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(DQFlow.name.ilike(search_term), DQFlow.description.ilike(search_term))
            )

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        flows = query.order_by(DQFlow.created_at.desc()).offset(offset).limit(page_size).all()

        return FlowListResponse(
            flows=[FlowResponse.from_orm(f) for f in flows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def _cleanup_orphaned_connections(self, flow_definition):
        """
        Remove connections that reference non-existent nodes

        Args:
            flow_definition: FlowDefinition object

        Returns:
            FlowDefinition with cleaned connections
        """
        # Get all valid node IDs
        valid_node_ids = {node.id for node in flow_definition.nodes}

        # Filter connections to only include those with valid source and target
        cleaned_connections = [
            conn
            for conn in flow_definition.connections
            if conn.source in valid_node_ids and conn.target in valid_node_ids
        ]

        # Create new flow definition with cleaned connections
        flow_definition.connections = cleaned_connections
        return flow_definition

    async def execute_flow(
        self,
        db: Session,
        flow_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        request: ExecuteFlowRequest | None = None,
    ) -> FlowExecutionResponse:
        """
        Execute a flow synchronously (blocks until completion)

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID
            user_id: User executing the flow
            request: Execution request

        Returns:
            FlowExecutionResponse
        """
        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            raise ValueError(f"Flow {flow_id} not found")

        # Get execution config
        execution_config = (
            request.execution_config.dict() if request and request.execution_config else {}
        )

        # Execute flow
        execution = await self.executor.execute_flow(
            db=db,
            flow=flow,
            workspace_id=workspace_id,
            executed_by=user_id,
            execution_config=execution_config,
        )

        return FlowExecutionResponse.from_orm(execution)

    async def execute_flow_async(
        self,
        db: Session,
        flow_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        background_tasks,
        request: ExecuteFlowRequest | None = None,
    ) -> FlowExecutionResponse:
        """
        Execute a flow asynchronously (returns immediately)

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID
            user_id: User executing the flow
            background_tasks: FastAPI BackgroundTasks
            request: Execution request

        Returns:
            FlowExecutionResponse with pending status
        """
        from datetime import datetime

        from app.models.flow import FlowExecution
        from app.schemas.flow import ExecutionStatus, ExecutionTrigger

        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            raise ValueError(f"Flow {flow_id} not found")

        # Get execution config
        execution_config = (
            request.execution_config.dict() if request and request.execution_config else {}
        )

        # Create execution record with pending status
        execution = FlowExecution(
            flow_id=flow.id,
            status=ExecutionStatus.PENDING,
            execution_type=ExecutionTrigger.MANUAL,  # Use execution_type, not trigger
            executed_by=user_id,
            started_at=datetime.utcnow(),
            execution_config=execution_config,
            nodes_executed=0,
            nodes_passed=0,
            nodes_failed=0,
            nodes_skipped=0,
        )

        db.add(execution)
        db.commit()
        db.refresh(execution)

        # Schedule background execution
        background_tasks.add_task(
            self._execute_flow_background,
            execution.id,
            flow.id,
            workspace_id,
            user_id,
            execution_config,
        )

        return FlowExecutionResponse.from_orm(execution)

    async def _execute_flow_background(
        self,
        execution_id: UUID,
        flow_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        execution_config: dict,
    ):
        """
        Background task to execute flow

        Args:
            execution_id: Execution ID
            flow_id: Flow ID
            workspace_id: Organization ID
            user_id: User ID
            execution_config: Execution configuration
        """
        from datetime import datetime

        from app.models.database import SessionLocal
        from app.schemas.flow import ExecutionStatus

        db = SessionLocal()
        try:
            # Get flow and execution
            flow = db.query(DQFlow).filter(DQFlow.id == flow_id).first()
            execution = db.query(FlowExecution).filter(FlowExecution.id == execution_id).first()

            if not flow or not execution:
                return

            # Update to running status
            execution.status = ExecutionStatus.RUNNING
            db.commit()

            # Execute flow
            await self.executor.execute_flow(
                db=db,
                flow=flow,
                workspace_id=workspace_id,
                executed_by=user_id,
                execution_config=execution_config,
                execution_record=execution,  # Pass existing execution record
            )

            # Update execution with results (executor should have done this, but ensure it's done)
            db.refresh(execution)

            # F031 — Issue creation hook (best-effort, isolated per node result).
            # Each issue is created in its own DB session so that hook failures
            # cannot affect the already-committed FlowExecution state (TDD §5.3).
            _run_issue_creation_hook(execution_id, db)

            # Fire execution_failed alert when the flow finishes in a failed
            # state (best-effort, never blocks).
            try:
                from app.schemas.flow import ExecutionStatus as _ES

                exec_status = getattr(execution.status, "value", execution.status)
                failed_status = getattr(_ES.FAILED, "value", _ES.FAILED)
                logger.info(
                    "post-run alert check: exec=%s status=%s failed_marker=%s",
                    execution_id,
                    exec_status,
                    failed_status,
                )
                if (
                    str(exec_status).lower() == str(failed_status).lower()
                    or str(exec_status).lower() == "failed"
                ):
                    from app.services.alerts.alert_trigger_service import AlertTriggerService

                    flow_obj = db.query(DQFlow).filter(DQFlow.id == execution.flow_id).first()
                    n = AlertTriggerService().trigger_for_workspace(
                        db,
                        workspace_id=workspace_id,
                        trigger_type="execution_failed",
                        payload={
                            "execution_id": str(execution.id),
                            "flow_id": str(execution.flow_id),
                            "flow_name": getattr(flow_obj, "name", None),
                            "error_message": getattr(execution, "error_message", None),
                            "executed_by": str(user_id) if user_id else None,
                        },
                    )
                    db.commit()
                    logger.info("post-run alert trigger fired: events=%s", n)
            except Exception:
                logger.warning("execution_failed alert trigger failed (post-run)", exc_info=True)

        except Exception as e:
            # Update execution with error
            from app.schemas.flow import ExecutionStatus

            try:
                db.rollback()
            except Exception:
                pass
            execution = db.query(FlowExecution).filter(FlowExecution.id == execution_id).first()
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.error_message = str(e)
                execution.completed_at = datetime.utcnow()
                db.commit()
                # Fire execution_failed alert (best-effort, never blocks)
                try:
                    from app.services.alerts.alert_trigger_service import AlertTriggerService

                    flow_obj = db.query(DQFlow).filter(DQFlow.id == execution.flow_id).first()
                    n = AlertTriggerService().trigger_for_workspace(
                        db,
                        workspace_id=workspace_id,
                        trigger_type="execution_failed",
                        payload={
                            "execution_id": str(execution.id),
                            "flow_id": str(execution.flow_id),
                            "flow_name": getattr(flow_obj, "name", None),
                            "error_message": str(e)[:500],
                            "executed_by": str(user_id) if user_id else None,
                        },
                    )
                    db.commit()
                    logger.info("exception-path alert trigger fired: events=%s", n)
                except Exception:
                    logger.warning("execution_failed alert trigger failed", exc_info=True)
        finally:
            db.close()

    def get_execution_history(
        self,
        db: Session,
        flow_id: UUID,
        workspace_id: UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> FlowExecutionListResponse:
        """
        Get execution history for a flow

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID
            status: Filter by status
            page: Page number
            page_size: Page size

        Returns:
            FlowExecutionListResponse
        """
        from app.models.user import User

        # Verify flow belongs to organization
        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            raise ValueError(f"Flow {flow_id} not found")

        query = db.query(FlowExecution).filter(FlowExecution.flow_id == flow_id)

        if status:
            query = query.filter(FlowExecution.status == status)

        total = query.count()

        offset = (page - 1) * page_size
        executions = (
            query.order_by(FlowExecution.created_at.desc()).offset(offset).limit(page_size).all()
        )

        # Enhance executions with flow_name and executed_by_name
        execution_responses = []
        for execution in executions:
            response = FlowExecutionResponse.from_orm(execution)
            response.flow_name = flow.name

            # Add executed by name
            if execution.executed_by:
                user = db.query(User).filter(User.id == execution.executed_by).first()
                if user:
                    response.executed_by_name = user.full_name or user.email

            execution_responses.append(response)

        return FlowExecutionListResponse(
            executions=execution_responses, total=total, page=page, page_size=page_size
        )

    def get_all_executions(
        self,
        db: Session,
        workspace_id: UUID,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> FlowExecutionListResponse:
        """
        Get all flow executions for an organization (across all flows)

        Args:
            db: Database session
            workspace_id: Organization ID
            status: Filter by status
            page: Page number
            page_size: Page size

        Returns:
            FlowExecutionListResponse
        """
        # Get all flows for this organization
        flow_ids = db.query(DQFlow.id).filter(DQFlow.workspace_id == workspace_id).all()
        flow_ids = [f[0] for f in flow_ids]

        if not flow_ids:
            return FlowExecutionListResponse(executions=[], total=0, page=page, page_size=page_size)

        query = db.query(FlowExecution).filter(FlowExecution.flow_id.in_(flow_ids))

        if status:
            query = query.filter(FlowExecution.status == status)

        total = query.count()

        offset = (page - 1) * page_size
        executions = (
            query.order_by(FlowExecution.created_at.desc()).offset(offset).limit(page_size).all()
        )

        return FlowExecutionListResponse(
            executions=[FlowExecutionResponse.from_orm(e) for e in executions],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_execution(
        self, db: Session, execution_id: UUID, workspace_id: UUID
    ) -> FlowExecutionResponse | None:
        """
        Get execution details with enhanced report data

        Args:
            db: Database session
            execution_id: Execution ID
            workspace_id: Organization ID

        Returns:
            FlowExecutionResponse or None
        """
        from app.models.user import User

        execution = (
            db.query(FlowExecution)
            .join(DQFlow)
            .filter(FlowExecution.id == execution_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not execution:
            return None

        # Create response
        response = FlowExecutionResponse.from_orm(execution)

        # Add flow name
        response.flow_name = execution.flow.name if execution.flow else None

        # Add executed by name
        if execution.executed_by:
            user = db.query(User).filter(User.id == execution.executed_by).first()
            if user:
                response.executed_by_name = user.full_name or user.email

        # Ensure result_summary structure contains the expected data for reports
        if not execution.result_summary:
            execution.result_summary = {}

        # Build enhanced result summary if needed
        if (
            "datasets" not in execution.result_summary
            or "checks_summary" not in execution.result_summary
        ):
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"Building enhanced result summary for execution {execution.id}")
            try:
                self._build_enhanced_result_summary(db, execution)
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(execution, "result_summary")
                db.commit()
                logger.info(
                    f"Enhanced result_summary keys: {list(execution.result_summary.keys())}"
                )
            except Exception as e:
                logger.error(f"Failed to build enhanced result summary: {e}", exc_info=True)
                db.rollback()
            response.result_summary = execution.result_summary

        return response

    def _build_enhanced_result_summary(self, db: Session, execution: FlowExecution):
        """Build enhanced result summary with datasets, checks, and metrics"""

        # Get node results
        node_results = (
            db.query(FlowNodeResult)
            .filter(FlowNodeResult.execution_id == execution.id)
            .order_by(FlowNodeResult.execution_order)
            .all()
        )

        # Initialize summary structures
        datasets = []
        checks_results = []
        runtime_by_dataset = {}
        runtime_by_check_type = {}

        # Track datasets from source nodes
        for node_result in node_results:
            if node_result.node_type == "source" and node_result.result_data:
                data = node_result.result_data
                dataset_info = {
                    "name": data.get("node_label") or data.get("table_name") or node_result.node_id,
                    "source": data.get("source_name", "Unknown"),
                    "rows_analyzed": data.get("rows_scanned", 0),
                    "schema_version": data.get("schema_version"),
                    "status": "success" if node_result.status == "completed" else "error",
                    "type": "input",
                }

                # Check for schema drift
                if "schema_drift" in data:
                    dataset_info["schema_drift"] = data["schema_drift"]

                # Check for volume changes
                if "volume_change" in data:
                    dataset_info["volume_change"] = data["volume_change"]

                datasets.append(dataset_info)

                # Track runtime
                if node_result.duration_seconds:
                    runtime_by_dataset[node_result.node_id] = node_result.duration_seconds

            # Track check results
            elif node_result.node_type == "check" and node_result.result_data:
                data = node_result.result_data
                check_result = {
                    "check_name": data.get("node_label") or node_result.node_id,
                    "check_type": data.get("check_type", "unknown"),
                    "dataset": data.get("dataset", "unknown"),
                    "column": data.get("column"),
                    "threshold": data.get("threshold"),
                    "result": self._determine_check_result(node_result, data),
                    "actual_value": data.get("pass_rate") or data.get("actual_value"),
                    "expected_value": data.get("threshold") or data.get("expected_value"),
                }
                checks_results.append(check_result)

                # Track runtime by check type
                check_type = data.get("check_type", "unknown")
                if node_result.duration_seconds:
                    if check_type not in runtime_by_check_type:
                        runtime_by_check_type[check_type] = 0
                    runtime_by_check_type[check_type] += node_result.duration_seconds

        # Calculate checks summary
        checks_summary = {
            "total": len(checks_results),
            "passed": sum(1 for c in checks_results if c["result"] == "passed"),
            "warning": sum(1 for c in checks_results if c["result"] == "warning"),
            "failed": sum(1 for c in checks_results if c["result"] == "failed"),
            "skipped": sum(1 for c in checks_results if c["result"] == "skipped"),
            "results": checks_results,
        }

        # Calculate run metrics
        total_checks = len(checks_results)
        failed_checks = checks_summary["failed"]
        pass_percentage = (
            ((total_checks - failed_checks) / total_checks * 100) if total_checks > 0 else 100.0
        )

        run_metrics = {
            "total_checks": total_checks,
            "failed_checks": failed_checks,
            "pass_percentage": round(pass_percentage, 2),
            "runtime_by_dataset": runtime_by_dataset,
            "runtime_by_check_type": runtime_by_check_type,
        }

        # Build historical context (if previous execution exists)
        historical_context = self._build_historical_context(db, execution, checks_results)

        # Update result_summary
        execution.result_summary.update(
            {
                "datasets": datasets,
                "checks_summary": checks_summary,
                "run_metrics": run_metrics,
                "historical_context": historical_context,
            }
        )

    def _determine_check_result(self, node_result: FlowNodeResult, data: dict) -> str:
        """Determine check result status"""
        if node_result.status == "skipped":
            return "skipped"
        elif node_result.status == "failed":
            return "failed"

        # Check pass rate or status in data
        pass_rate = data.get("pass_rate")
        if pass_rate is not None:
            if pass_rate >= 95:
                return "passed"
            elif pass_rate >= 80:
                return "warning"
            else:
                return "failed"

        # Default to passed if completed successfully
        return "passed" if node_result.status == "completed" else "failed"

    def _build_historical_context(
        self, db: Session, current_execution: FlowExecution, current_checks: list
    ) -> list:
        """Build historical context by comparing with previous execution"""
        # Get previous execution for the same flow
        previous_execution = (
            db.query(FlowExecution)
            .filter(
                FlowExecution.flow_id == current_execution.flow_id,
                FlowExecution.id != current_execution.id,
                FlowExecution.status == "completed",
                FlowExecution.completed_at < current_execution.started_at,
            )
            .order_by(FlowExecution.completed_at.desc())
            .first()
        )

        if not previous_execution or not previous_execution.result_summary:
            return []

        historical = []
        previous_checks = previous_execution.result_summary.get("checks_summary", {}).get(
            "results", []
        )

        # Match current checks with previous
        for current_check in current_checks:
            # Find matching previous check
            prev_check = next(
                (c for c in previous_checks if c["check_name"] == current_check["check_name"]), None
            )

            if (
                prev_check
                and prev_check.get("actual_value") is not None
                and current_check.get("actual_value") is not None
            ):
                prev_value = prev_check["actual_value"]
                curr_value = current_check["actual_value"]

                # Determine trend
                if curr_value > prev_value + 1:
                    trend = "improving"
                elif curr_value < prev_value - 1:
                    trend = "degrading"
                else:
                    trend = "stable"

                # Calculate stability score (how consistent the values are)
                diff = abs(curr_value - prev_value)
                stability_score = max(0, 100 - diff)

                # Build comparison string
                comparison = f"{prev_value:.1f}% → {curr_value:.1f}%"

                historical.append(
                    {
                        "check_name": current_check["check_name"],
                        "previous_result": prev_value,
                        "current_result": curr_value,
                        "trend": trend,
                        "stability_score": stability_score,
                        "comparison": comparison,
                    }
                )

                # Add comparison to current check
                current_check["comparison"] = comparison

        return historical

    def get_node_results(
        self, db: Session, execution_id: UUID, workspace_id: UUID
    ) -> list[FlowNodeResultResponse]:
        """
        Get node results for an execution

        Args:
            db: Database session
            execution_id: Execution ID
            workspace_id: Organization ID

        Returns:
            List of FlowNodeResultResponse
        """
        # Verify execution belongs to organization
        execution = (
            db.query(FlowExecution)
            .join(DQFlow)
            .filter(FlowExecution.id == execution_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not execution:
            return []

        node_results = (
            db.query(FlowNodeResult)
            .filter(FlowNodeResult.execution_id == execution_id)
            .order_by(FlowNodeResult.execution_order)
            .all()
        )

        return [FlowNodeResultResponse.from_orm(nr) for nr in node_results]

    async def cancel_execution(self, db: Session, execution_id: UUID, workspace_id: UUID) -> bool:
        """
        Cancel a running execution

        Args:
            db: Database session
            execution_id: Execution ID
            workspace_id: Organization ID

        Returns:
            True if cancelled
        """
        # Verify execution belongs to organization
        execution = (
            db.query(FlowExecution)
            .join(DQFlow)
            .filter(FlowExecution.id == execution_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not execution:
            return False

        return await self.executor.cancel_execution(db, execution_id)

    def duplicate_flow(
        self,
        db: Session,
        flow_id: UUID,
        workspace_id: UUID,
        user_id: UUID,
        new_name: str | None = None,
    ) -> FlowResponse:
        """
        Duplicate a flow

        Args:
            db: Database session
            flow_id: Flow ID to duplicate
            workspace_id: Organization ID
            user_id: User duplicating the flow
            new_name: New flow name (defaults to "Copy of {original_name}")

        Returns:
            FlowResponse for duplicated flow
        """
        original = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not original:
            raise ValueError(f"Flow {flow_id} not found")

        # Create duplicate
        duplicate = DQFlow(
            workspace_id=workspace_id,
            name=new_name or f"Copy of {original.name}",
            description=original.description,
            flow_definition=original.flow_definition,
            status="draft",  # Always start as draft
            schedule=None,  # Don't copy schedule
            tags=original.tags,
            created_by=user_id,
            owner_user_id=user_id,
        )

        db.add(duplicate)
        db.commit()
        db.refresh(duplicate)

        return FlowResponse.from_orm(duplicate)

    def export_flow(
        self, db: Session, flow_id: UUID, workspace_id: UUID, format: str = "json"
    ) -> str:
        """
        Export flow definition

        Args:
            db: Database session
            flow_id: Flow ID
            workspace_id: Organization ID
            format: Export format ('json' or 'yaml')

        Returns:
            Exported flow as string
        """
        flow = (
            db.query(DQFlow)
            .filter(DQFlow.id == flow_id, DQFlow.workspace_id == workspace_id)
            .first()
        )

        if not flow:
            raise ValueError(f"Flow {flow_id} not found")

        if format == "json":
            return self.builder.export_to_json(
                flow_id=str(flow.id),
                name=flow.name,
                description=flow.description,
                flow_definition=flow.flow_definition,
            )
        elif format == "yaml":
            return self.builder.export_to_yaml(
                flow_id=str(flow.id),
                name=flow.name,
                description=flow.description,
                flow_definition=flow.flow_definition,
            )
        else:
            raise ValueError(f"Unsupported export format: {format}")

    def import_flow(
        self, db: Session, workspace_id: UUID, user_id: UUID, flow_data: str, format: str = "json"
    ) -> FlowResponse:
        """
        Import flow from string

        Args:
            db: Database session
            workspace_id: Organization ID
            user_id: User importing the flow
            flow_data: Flow data as string
            format: Import format ('json' or 'yaml')

        Returns:
            FlowResponse for imported flow
        """
        if format == "json":
            data = self.builder.import_from_json(flow_data)
        elif format == "yaml":
            data = self.builder.import_from_yaml(flow_data)
        else:
            raise ValueError(f"Unsupported import format: {format}")

        # Create flow from imported data
        from app.schemas.flow import CreateFlowRequest, FlowDefinition

        flow_definition = FlowDefinition(**data["flow_definition"])

        request = CreateFlowRequest(
            name=data["name"],
            description=data.get("description"),
            flow_definition=flow_definition,
            tags=data.get("tags", []),
        )

        return self.create_flow(db, workspace_id, user_id, request)


# ─────────────────────────────────────────────────────────────────────────────
# F031 — Issue creation hook (module-level helper, not part of FlowService)
# ─────────────────────────────────────────────────────────────────────────────


def _run_issue_creation_hook(execution_id: UUID, read_db) -> None:
    """
    Iterate over failed FlowNodeResults for *execution_id* and create an
    Issue for each one using an isolated DB session.

    This function is *best-effort*: all exceptions are caught and logged so
    that hook failures never affect FlowExecution.status (TDD §5.3 / P03-AC-011).

    Parameters
    ----------
    execution_id:
        PK of the FlowExecution whose node results should be evaluated.
    read_db:
        Existing SQLAlchemy Session used only for the initial SELECT of
        failed node result IDs (read-only, no writes).
    """
    from app.models.database import SessionLocal
    from app.services.audit.hooks import build_issue_audit_entry
    from app.services.audit.models import AuditContext
    from app.services.audit.service import AuditService as _AuditSvc
    from app.services.issues.issue_creation_service import IssueCreationService

    _svc = IssueCreationService()
    _audit_svc = _AuditSvc()
    try:
        failed_ids = [
            fnr.id
            for fnr in read_db.query(FlowNodeResult)
            .filter(
                FlowNodeResult.execution_id == execution_id,
                FlowNodeResult.status == "failed",
            )
            .all()
        ]
    except Exception:
        logger.error(
            "F031 hook: failed to query FlowNodeResults for execution %s",
            execution_id,
            exc_info=True,
        )
        return

    for node_result_id in failed_ids:
        issue_db = SessionLocal()
        try:
            result = _svc.create_from_node_result(
                db=issue_db,
                node_result_id=node_result_id,
                flow_execution_id=execution_id,
            )
            if result is not None:
                # F052 — system audit for auto-created issue (best-effort)
                try:
                    sys_ctx = AuditContext.for_system(result.tenant_id)
                    _audit_svc.write(
                        issue_db,
                        build_issue_audit_entry(
                            ctx=sys_ctx,
                            action="issue_created",
                            workspace_id=result.workspace_id,
                            issue_id=result.id,
                            after_state={
                                "issue_type": result.issue_type,
                                "severity": result.severity,
                                "status": result.status,
                                "title": result.title,
                            },
                        ),
                    )
                except Exception:
                    logger.warning(
                        "F052 audit write failed for system issue_created node_result_id=%s",
                        node_result_id,
                    )
                issue_db.commit()
            else:
                # Service returned None: either non-failure status or internal error.
                # Rollback to clean any partial state from DB checks above.
                issue_db.rollback()
        except Exception:
            issue_db.rollback()
            logger.error(
                "F031 hook: unexpected error creating issue",
                exc_info=True,
                extra={
                    "flow_execution_id": str(execution_id),
                    "node_result_id": str(node_result_id),
                },
            )
        finally:
            issue_db.close()
