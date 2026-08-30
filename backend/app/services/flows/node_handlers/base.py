"""
Base Node Handler - Abstract base class for all node handlers
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.flow import NodeStatus


class NodeExecutionContext:
    """Context passed to node handlers during execution"""

    def __init__(
        self,
        db: Session,
        workspace_id: UUID,
        flow_id: UUID,
        execution_id: UUID,
        node_id: str,
        node_config: dict[str, Any],
        execution_config: dict[str, Any],
        input_data: dict[str, Any] | None = None,
        check_type: str | None = None,
    ):
        self.db = db
        self.workspace_id = workspace_id
        self.check_type = check_type
        self.flow_id = flow_id
        self.execution_id = execution_id
        self.node_id = node_id
        self.node_config = node_config
        self.execution_config = execution_config
        self.input_data = input_data or {}
        self.started_at = datetime.utcnow()


class NodeExecutionResult:
    """Result returned by node handlers"""

    def __init__(
        self,
        status: NodeStatus,
        result_data: dict[str, Any] | None = None,
        error_message: str | None = None,
        error_details: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
    ):
        self.status = status
        self.result_data = result_data or {}
        self.error_message = error_message
        self.error_details = error_details
        self.output_data = output_data or {}  # Data to pass to downstream nodes
        self.completed_at = datetime.utcnow()


class BaseNodeHandler(ABC):
    """Abstract base class for all node handlers"""

    @abstractmethod
    async def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        """
        Execute the node logic

        Args:
            context: Node execution context

        Returns:
            NodeExecutionResult with execution results
        """
        pass

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> bool:
        """
        Validate node configuration

        Args:
            config: Node configuration

        Returns:
            True if valid, False otherwise
        """
        pass

    def handle_error(self, error: Exception, context: NodeExecutionContext) -> NodeExecutionResult:
        """
        Handle execution errors

        Args:
            error: Exception that occurred
            context: Node execution context

        Returns:
            NodeExecutionResult with error information
        """
        import traceback

        error_message = str(error)
        if not error_message:
            # If str(error) is empty, use error type
            error_message = f"{type(error).__name__} occurred"

        return NodeExecutionResult(
            status=NodeStatus.FAILED,
            error_message=error_message,
            error_details={
                "error_type": type(error).__name__,
                "message": error_message,
                "traceback": traceback.format_exc(),
                "node_id": context.node_id,
                "flow_id": str(context.flow_id),
            },
        )
