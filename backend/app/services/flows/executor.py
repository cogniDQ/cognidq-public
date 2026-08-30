"""
Flow Execution Engine - Executes flows by running nodes in correct order

This module provides the core execution engine that:
- Parses flow definition
- Builds execution DAG
- Executes nodes in dependency order
- Handles parallel execution
- Tracks progress and results
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.flow import DQFlow, FlowExecution, FlowNodeResult
from app.schemas.flow import (
    FlowConnection,
    FlowDefinition,
    FlowNode,
    NodeStatus,
    NodeType,
)
from app.services.flows.node_handlers import (
    CheckNodeHandler,
    NodeExecutionContext,
    SourceNodeHandler,
)
from app.services.flows.validator import FlowValidator
from app.utils.json_utils import sanitize_result_data


class FlowExecutor:
    """Flow execution engine"""

    def __init__(self):
        """Initialize the flow executor"""
        self.validator = FlowValidator()
        self.logger = logging.getLogger(__name__)

        # Register node handlers
        self.node_handlers = {
            NodeType.SOURCE: SourceNodeHandler(),
            NodeType.CHECK: CheckNodeHandler(),
            # Add more handlers as they're implemented
        }

    async def execute_flow(
        self,
        db: Session,
        flow: DQFlow,
        workspace_id: UUID,
        executed_by: UUID,
        execution_config: dict[str, Any] | None = None,
        execution_record: FlowExecution | None = None,
    ) -> FlowExecution:
        """
        Execute a flow

        Args:
            db: Database session
            flow: Flow to execute
            workspace_id: Organization ID
            executed_by: User executing the flow
            execution_config: Execution configuration
            execution_record: Optional existing execution record (for async execution)

        Returns:
            FlowExecution record
        """
        # Parse flow definition
        flow_def = FlowDefinition(**flow.flow_definition)

        # Debug logging to identify duplicate nodes
        self.logger.error(f"\n{'=' * 80}")
        self.logger.error(f"⚡ STARTING FLOW EXECUTION for flow {flow.id}")
        self.logger.error(f"{'=' * 80}")
        self.logger.error(f"Flow has {len(flow_def.nodes)} nodes total")
        self.logger.error(
            f"Source nodes: {len([n for n in flow_def.nodes if n.type == NodeType.SOURCE])}"
        )
        self.logger.error(
            f"Check nodes: {len([n for n in flow_def.nodes if n.type == NodeType.CHECK])}"
        )
        self.logger.error("\n📋 FLOW DEFINITION NODES:")
        for node in flow_def.nodes:
            self.logger.error(f"  🔹 Node {node.id}:")
            self.logger.error(f"     Type: {node.type.value}")
            self.logger.error(f"     CheckType: {node.checkType}")
            self.logger.error(f"     Label: {node.label}")
            self.logger.error(f"     Config: {node.config}")
        self.logger.error(f"{'=' * 80}\n")

        # Validate flow before execution
        validation_result = self.validator.validate_flow(flow_def)
        if not validation_result.is_valid:
            # Update or create failed execution record
            if execution_record:
                execution = execution_record
                execution.status = "failed"
                execution.completed_at = datetime.utcnow()
                execution.error_message = "Flow validation failed"
                execution.error_details = {"errors": [e.dict() for e in validation_result.errors]}
            else:
                execution = FlowExecution(
                    flow_id=flow.id,
                    execution_type="manual",
                    status="failed",
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    error_message="Flow validation failed",
                    error_details={"errors": [e.dict() for e in validation_result.errors]},
                    executed_by=executed_by,
                )
                db.add(execution)
            db.commit()
            return execution

        # Use existing execution record or create new one
        if execution_record:
            execution = execution_record
            execution.status = "running"
            execution.execution_config = execution_config or {}
        else:
            execution = FlowExecution(
                flow_id=flow.id,
                execution_type="manual",
                status="running",
                started_at=datetime.utcnow(),
                execution_config=execution_config or {},
                executed_by=executed_by,
            )
            db.add(execution)
        db.commit()
        db.refresh(execution)

        try:
            self.logger.info(
                f"Starting execution for flow {flow.id}, execution record {execution.id}"
            )

            # Get execution levels for parallel execution
            execution_levels = self.validator.get_execution_levels(
                flow_def.nodes, flow_def.connections
            )

            self.logger.info(f"Execution plan: {len(execution_levels)} levels")
            for level_idx, level_nodes in enumerate(execution_levels):
                self.logger.info(
                    f"  Level {level_idx + 1}: {len(level_nodes)} nodes - {level_nodes}"
                )

            # Execute nodes level by level with parallel execution within each level
            self.logger.info(
                f"Beginning parallel execution of {len(flow_def.nodes)} nodes across {len(execution_levels)} levels"
            )
            node_results = await self._execute_nodes_parallel(
                db=db,
                workspace_id=workspace_id,
                flow=flow,
                execution=execution,
                nodes=flow_def.nodes,
                connections=flow_def.connections,
                execution_levels=execution_levels,
                execution_config=execution_config or {},
            )
            self.logger.info(
                f"Parallel execution completed. Got results for {len(node_results)} nodes"
            )

            # Aggregate results
            self.logger.info("Aggregating results from all nodes...")
            summary = self._aggregate_results(node_results)
            self.logger.info(f"Aggregation complete: {summary}")

            # Update execution record
            execution.status = "completed" if summary["all_passed"] else "failed"
            execution.completed_at = datetime.utcnow()
            execution.duration_seconds = int(
                (execution.completed_at - execution.started_at).total_seconds()
            )
            execution.nodes_executed = summary["nodes_executed"]
            execution.nodes_passed = summary["nodes_passed"]
            execution.nodes_failed = summary["nodes_failed"]
            execution.nodes_skipped = summary["nodes_skipped"]
            execution.result_summary = summary["summary"]

            self.logger.info(
                f"Flow execution {execution.id} completed with status: {execution.status}"
            )
            self.logger.info(f"  Duration: {execution.duration_seconds}s")
            self.logger.info(
                f"  Nodes executed: {execution.nodes_executed}, passed: {execution.nodes_passed}, failed: {execution.nodes_failed}, skipped: {execution.nodes_skipped}"
            )

            db.commit()
            db.refresh(execution)

            return execution

        except Exception as e:
            # Update execution with error
            self.logger.error(
                f"❌ FLOW EXECUTION FAILED with exception: {type(e).__name__}: {str(e)}"
            )
            self.logger.error("Exception details:", exc_info=True)

            try:
                db.rollback()
            except Exception:
                pass

            execution = db.query(FlowExecution).filter(FlowExecution.id == execution.id).first()
            if execution:
                execution.status = "failed"
                execution.completed_at = datetime.utcnow()
                execution.duration_seconds = int(
                    (execution.completed_at - execution.started_at).total_seconds()
                )
                execution.error_message = str(e)
                execution.error_details = {"error_type": type(e).__name__, "traceback": str(e)}

                db.commit()

            self.logger.error("Execution marked as failed")
            raise

    async def _execute_nodes_parallel(
        self,
        db: Session,
        workspace_id: UUID,
        flow: DQFlow,
        execution: FlowExecution,
        nodes: list[FlowNode],
        connections: list[FlowConnection],
        execution_levels: list[list[str]],
        execution_config: dict[str, Any],
    ) -> dict[str, FlowNodeResult]:
        """
        Execute nodes level by level with parallel execution within each level.
        Nodes at the same level can run concurrently.

        Args:
            db: Database session
            workspace_id: Organization ID
            flow: Flow being executed
            execution: Execution record
            nodes: List of nodes
            connections: List of connections
            execution_levels: List of levels, where each level contains node IDs that can run in parallel
            execution_config: Execution configuration

        Returns:
            Dict mapping node_id to FlowNodeResult
        """
        node_dict = {node.id: node for node in nodes}
        node_results = {}
        node_output_data = {}  # Store output data from each node

        # Build dependency map
        dependencies = defaultdict(list)
        for conn in connections:
            dependencies[conn.target].append(conn.source)

        # Track overall execution order for indexing
        order_idx = 0

        # Execute level by level
        for level_idx, level_node_ids in enumerate(execution_levels):
            # Check if execution was cancelled
            db.refresh(execution)
            if execution.status == "cancelled":
                # Mark all remaining nodes as skipped
                for remaining_level in execution_levels[level_idx:]:
                    for node_id in remaining_level:
                        self._create_node_result(
                            db,
                            execution.id,
                            node_id,
                            node_dict[node_id].type.value,
                            NodeStatus.SKIPPED,
                            order_idx,
                        )
                        order_idx += 1
                break

            # Prepare tasks for parallel execution within this level
            level_tasks = []
            level_node_order = {}

            for node_id in level_node_ids:
                node = node_dict[node_id]

                # Gather input data from dependencies
                input_data = {}
                for dep_node_id in dependencies.get(node_id, []):
                    if dep_node_id in node_output_data:
                        # Merge input data from all dependencies
                        self.logger.info(
                            f"📥 Node {node_id} receiving input from dependency {dep_node_id}"
                        )
                        self.logger.info(
                            f"   Input data keys: {list(node_output_data[dep_node_id].keys())}"
                        )
                        input_data.update(node_output_data[dep_node_id])
                    else:
                        self.logger.warning(
                            f"⚠️ Dependency {dep_node_id} not found in output data for node {node_id}"
                        )

                # Track execution order for this node
                level_node_order[node_id] = order_idx
                order_idx += 1

                # Create task for this node
                task = self._execute_node(
                    db=db,
                    workspace_id=workspace_id,
                    flow_id=flow.id,
                    execution_id=execution.id,
                    node=node,
                    execution_config=execution_config,
                    input_data=input_data,
                    execution_order=level_node_order[node_id],
                )
                level_tasks.append((node_id, task))

            # Execute all nodes in this level concurrently
            self.logger.info(
                f"⚡ Executing level {level_idx + 1}/{len(execution_levels)} with {len(level_tasks)} nodes in parallel"
            )
            self.logger.info(
                f"   Level {level_idx + 1} nodes: {[node_id for node_id, _ in level_tasks]}"
            )

            level_results = await asyncio.gather(
                *[task for _, task in level_tasks], return_exceptions=True
            )

            self.logger.info(
                f"✅ Level {level_idx + 1} execution completed, processing {len(level_results)} results"
            )

            # Process results from this level
            has_failure = False
            for (node_id, _), result in zip(level_tasks, level_results):
                if isinstance(result, Exception):
                    # Handle exception from asyncio.gather
                    self.logger.error(
                        f"❌ Node {node_id} failed with exception: {type(result).__name__}: {result}"
                    )
                    self.logger.error("   Exception traceback:", exc_info=result)
                    node_result = self._create_node_result(
                        db=db,
                        execution_id=execution.id,
                        node_id=node_id,
                        node_type=node_dict[node_id].type.value,
                        status=NodeStatus.FAILED,
                        execution_order=level_node_order[node_id],
                        error_message=f"{type(result).__name__}: {str(result)}",
                    )
                    has_failure = True
                else:
                    node_result = result
                    if node_result.status == "failed":
                        self.logger.warning(
                            f"⚠️ Node {node_id} completed with failed status: {node_result.error_message}"
                        )
                        has_failure = True
                    else:
                        self.logger.info(
                            f"✅ Node {node_id} completed successfully with status: {node_result.status}"
                        )

                node_results[node_id] = node_result

                # Store output data for downstream nodes
                if node_result.result_data and "output_data" in node_result.result_data:
                    node_output_data[node_id] = node_result.result_data["output_data"]
                    self.logger.info(
                        f"📤 Stored output_data from node {node_id} for downstream nodes"
                    )
                    self.logger.info(
                        f"   Output data keys: {list(node_output_data[node_id].keys())}"
                    )
                else:
                    self.logger.warning(
                        f"⚠️ Node {node_id} has no output_data to pass to downstream nodes"
                    )
                    self.logger.warning(
                        f"   result_data keys: {list(node_result.result_data.keys()) if node_result.result_data else 'None'}"
                    )

            # Check if we should continue on error
            if has_failure and not execution_config.get("continue_on_error", False):
                # Mark all remaining nodes as skipped
                for remaining_level in execution_levels[level_idx + 1 :]:
                    for node_id in remaining_level:
                        self._create_node_result(
                            db,
                            execution.id,
                            node_id,
                            node_dict[node_id].type.value,
                            NodeStatus.SKIPPED,
                            order_idx,
                        )
                        order_idx += 1
                break

        return node_results

    async def _execute_node(
        self,
        db: Session,
        workspace_id: UUID,
        flow_id: UUID,
        execution_id: UUID,
        node: FlowNode,
        execution_config: dict[str, Any],
        input_data: dict[str, Any],
        execution_order: int,
    ) -> FlowNodeResult:
        """
        Execute a single node

        Args:
            db: Database session
            workspace_id: Organization ID
            flow_id: Flow ID
            execution_id: Execution ID
            node: Node to execute
            execution_config: Execution configuration
            input_data: Input data from upstream nodes
            execution_order: Execution order index

        Returns:
            FlowNodeResult record
        """
        # Get appropriate handler
        handler = self.node_handlers.get(node.type)
        if not handler:
            # No handler for this node type
            return self._create_node_result(
                db=db,
                execution_id=execution_id,
                node_id=node.id,
                node_type=node.type.value,
                status=NodeStatus.FAILED,
                execution_order=execution_order,
                error_message=f"No handler for node type: {node.type.value}",
            )

        # Create node result record
        node_result_record = FlowNodeResult(
            execution_id=execution_id,
            node_id=node.id,
            node_type=node.type.value,
            status="running",
            started_at=datetime.utcnow(),
            execution_order=execution_order,
        )
        db.add(node_result_record)
        db.commit()
        db.refresh(node_result_record)

        try:
            # Create execution context
            self.logger.info(f"\n{'=' * 60}")
            self.logger.info(f"🎯 EXECUTING NODE: {node.id}")
            self.logger.info(f"   Node Label: {node.label}")
            self.logger.info(f"   Node Type: {node.type.value}")
            self.logger.info(f"   Check Type: {node.checkType}")
            self.logger.info(f"   Node Config: {node.config}")
            self.logger.info(f"   Input Data Keys: {list(input_data.keys())}")
            if "columns" in input_data:
                self.logger.info(f"   Input Columns: {input_data.get('columns', [])}")
            if "data_source" in input_data:
                ds = input_data["data_source"]
                self.logger.info(
                    f"   Data Source: {ds.get('name', 'Unknown')} (type: {ds.get('type', 'Unknown')})"
                )
            self.logger.info(f"{'=' * 60}")

            context = NodeExecutionContext(
                db=db,
                workspace_id=workspace_id,
                flow_id=flow_id,
                execution_id=execution_id,
                node_id=node.id,
                node_config=node.config,
                execution_config=execution_config,
                input_data=input_data,
                check_type=node.checkType,  # Pass checkType from node
            )

            # Execute node
            self.logger.info(f"▶️ Calling handler.execute() for node {node.id}...")
            result = await handler.execute(context)
            self.logger.info(f"✅ Handler returned for node {node.id} with status: {result.status}")

            # Update node result record
            node_result_record.status = result.status.value
            node_result_record.completed_at = datetime.utcnow()
            duration = int(
                (node_result_record.completed_at - node_result_record.started_at).total_seconds()
            )
            node_result_record.duration_seconds = duration

            # Sanitize result data to handle NaN, Infinity, and other non-JSON values
            raw_result_data = {
                **result.result_data,
                "output_data": result.output_data,  # Include for downstream nodes
            }
            # Inject node_label so the frontend can display meaningful names
            if node.label and "node_label" not in raw_result_data:
                raw_result_data["node_label"] = node.label
            node_result_record.result_data = sanitize_result_data(raw_result_data)

            node_result_record.error_message = result.error_message
            node_result_record.error_details = result.error_details

            self.logger.info(
                f"💾 Saving node result for {node.id}: status={result.status.value}, duration={duration}s"
            )
            if result.error_message:
                self.logger.warning(f"   Error message: {result.error_message}")

            db.commit()
            db.refresh(node_result_record)

            self.logger.info(f"✅ Node {node.id} execution complete")
            return node_result_record

        except Exception as e:
            # Update node result with error (don't create new one - update existing)
            self.logger.error(
                f"❌ EXCEPTION during node {node.id} execution: {type(e).__name__}: {str(e)}"
            )
            self.logger.error("Exception details:", exc_info=True)

            node_result_record.status = "failed"
            node_result_record.completed_at = datetime.utcnow()
            node_result_record.duration_seconds = int(
                (node_result_record.completed_at - node_result_record.started_at).total_seconds()
            )
            node_result_record.error_message = str(e)
            node_result_record.error_details = {
                "error_type": type(e).__name__,
                "node_id": node.id,
                "node_type": node.type.value,
            }

            db.commit()
            db.refresh(node_result_record)

            self.logger.error(f"💾 Saved failed node result for {node.id}")
            return node_result_record

    def _create_node_result(
        self,
        db: Session,
        execution_id: UUID,
        node_id: str,
        node_type: str,
        status: NodeStatus,
        execution_order: int,
        error_message: str | None = None,
    ) -> FlowNodeResult:
        """Create a node result record"""
        node_result = FlowNodeResult(
            execution_id=execution_id,
            node_id=node_id,
            node_type=node_type,
            status=status.value,
            execution_order=execution_order,
            error_message=error_message,
            created_at=datetime.utcnow(),
        )
        db.add(node_result)
        db.commit()
        db.refresh(node_result)
        return node_result

    def _aggregate_results(self, node_results: dict[str, FlowNodeResult]) -> dict[str, Any]:
        """
        Aggregate results from all nodes

        Args:
            node_results: Dict mapping node_id to FlowNodeResult

        Returns:
            Aggregated summary
        """
        nodes_executed = len(node_results)
        nodes_passed = sum(1 for r in node_results.values() if r.status == "completed")
        nodes_failed = sum(1 for r in node_results.values() if r.status == "failed")
        nodes_skipped = sum(1 for r in node_results.values() if r.status == "skipped")

        all_passed = nodes_failed == 0

        # Aggregate check results
        total_rows_scanned = 0
        total_violations = 0

        for result in node_results.values():
            if result.result_data and result.node_type == "check":
                total_rows_scanned += result.result_data.get("rows_scanned", 0)
                total_violations += result.result_data.get("violation_count", 0)

        return {
            "nodes_executed": nodes_executed,
            "nodes_passed": nodes_passed,
            "nodes_failed": nodes_failed,
            "nodes_skipped": nodes_skipped,
            "all_passed": all_passed,
            "summary": {
                "total_rows_scanned": total_rows_scanned,
                "total_violations": total_violations,
                "node_count": nodes_executed,
                "success_rate": (nodes_passed / nodes_executed * 100) if nodes_executed > 0 else 0,
            },
        }

    async def cancel_execution(self, db: Session, execution_id: UUID) -> bool:
        """
        Cancel a running execution

        Args:
            db: Database session
            execution_id: Execution ID to cancel

        Returns:
            True if cancelled, False if not running
        """
        execution = db.query(FlowExecution).filter(FlowExecution.id == execution_id).first()

        if not execution or execution.status != "running":
            return False

        execution.status = "cancelled"
        execution.completed_at = datetime.utcnow()
        execution.duration_seconds = int(
            (execution.completed_at - execution.started_at).total_seconds()
        )

        db.commit()
        return True
