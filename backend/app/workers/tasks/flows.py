"""
Flow Celery Tasks - Background tasks for flow execution

This module provides Celery tasks for:
- Async flow execution
- Scheduled flow execution
- Flow completion notifications
"""

from datetime import datetime, timedelta
from uuid import UUID

from celery import shared_task

from app.models.database import SessionLocal
from app.models.flow import DQFlow, FlowExecution
from app.services.flows.service import FlowService
from app.workers.celery_app import celery_app


@shared_task(name="flows.execute_flow_task")
def execute_flow_task(
    flow_id: str, workspace_id: str, executed_by: str, execution_config: dict | None = None
):
    """
    Execute a flow asynchronously

    Args:
        flow_id: Flow UUID as string
        workspace_id: Organization UUID as string
        executed_by: User UUID as string
        execution_config: Optional execution configuration

    Returns:
        Execution ID as string
    """
    db = SessionLocal()
    execution_id = None
    try:
        flow_service = FlowService()

        # Import asyncio to run async function
        import asyncio

        # Execute flow
        execution = asyncio.run(
            flow_service.execute_flow(
                db=db,
                flow_id=UUID(flow_id),
                workspace_id=UUID(workspace_id),
                user_id=UUID(executed_by),
                request=None,  # execution_config handled separately
            )
        )

        execution_id = str(execution.id)

        # Trigger post-execution tasks
        if execution.status in ["completed", "failed"]:
            # Send completion notification
            send_flow_completion_notification.delay(execution_id)

            # Generate execution report
            generate_execution_report.delay(execution_id, workspace_id)

        return execution_id

    except Exception as e:
        print(f"Error executing flow {flow_id}: {str(e)}")
        # Still try to send notification even on error
        if execution_id:
            send_flow_completion_notification.delay(execution_id)
        raise
    finally:
        db.close()


@shared_task(name="flows.scheduled_flow_execution_task")
def scheduled_flow_execution_task():
    """
    Check for scheduled flows that need to be executed

    This task runs periodically (e.g., every minute) and checks if any flows
    with active schedules are due for execution.
    """
    db = SessionLocal()
    try:
        from croniter import croniter

        # Get all active flows with schedules
        flows = db.query(DQFlow).filter(DQFlow.is_active == True, DQFlow.schedule.isnot(None)).all()

        current_time = datetime.utcnow()

        for flow in flows:
            try:
                schedule = flow.schedule
                if not schedule or not schedule.get("enabled"):
                    continue

                cron_expr = schedule.get("cron")
                if not cron_expr:
                    continue

                # Get timezone (default to UTC)
                schedule.get("timezone", "UTC")

                # Calculate next run time
                cron = croniter(cron_expr, current_time)
                next_run = cron.get_next(datetime)

                # Check if the flow is due (within the last minute)
                time_since_next_run = current_time - next_run
                if timedelta(seconds=0) <= time_since_next_run <= timedelta(minutes=1):
                    # Check if there's already a recent execution
                    recent_execution = (
                        db.query(FlowExecution)
                        .filter(
                            FlowExecution.flow_id == flow.id,
                            FlowExecution.created_at >= current_time - timedelta(minutes=2),
                        )
                        .first()
                    )

                    if not recent_execution:
                        # Trigger execution
                        execute_flow_task.delay(
                            flow_id=str(flow.id),
                            workspace_id=str(flow.workspace_id),
                            executed_by=str(flow.created_by),  # Use flow creator as executor
                            execution_config={"execution_type": "scheduled"},
                        )

                        print(f"Scheduled execution triggered for flow {flow.id} ({flow.name})")

            except Exception as e:
                print(f"Error processing scheduled flow {flow.id}: {str(e)}")
                continue

    except Exception as e:
        print(f"Error in scheduled_flow_execution_task: {str(e)}")
        raise
    finally:
        db.close()


@shared_task(name="flows.send_flow_completion_notification")
def send_flow_completion_notification(execution_id: str):
    """
    Send notification when flow execution completes

    Args:
        execution_id: Execution UUID as string
    """
    db = SessionLocal()
    try:
        execution = db.query(FlowExecution).filter(FlowExecution.id == UUID(execution_id)).first()

        if not execution:
            print(f"Execution {execution_id} not found")
            return

        flow = db.query(DQFlow).filter(DQFlow.id == execution.flow_id).first()
        if not flow:
            print(f"Flow for execution {execution_id} not found")
            return

        # Build notification message
        status_emoji = "✅" if execution.status == "completed" else "❌"
        message = f"{status_emoji} Flow '{flow.name}' execution {execution.status}"

        if execution.status == "completed":
            message += "\n\nResults:"
            message += f"\n- Nodes executed: {execution.nodes_executed}"
            message += f"\n- Nodes passed: {execution.nodes_passed}"
            message += f"\n- Nodes failed: {execution.nodes_failed}"
            message += f"\n- Duration: {execution.duration_seconds}s"
        elif execution.status == "failed":
            message += f"\n\nError: {execution.error_message}"
        print(message)  # surfaced for tests and log capture
        # Map execution status → alert trigger_type and fire matching alert rules.
        trigger_type = (
            "execution_completed"
            if execution.status == "completed"
            else "execution_failed"
            if execution.status == "failed"
            else None
        )
        if trigger_type is not None:
            try:
                from app.services.alerts.alert_trigger_service import AlertTriggerService

                payload = {
                    "subject": f"DQ Flow {execution.status.capitalize()}: {flow.name}",
                    "body": message,
                    "flow_id": str(flow.id),
                    "flow_name": flow.name,
                    "execution_id": str(execution.id),
                    "status": execution.status,
                    "nodes_executed": execution.nodes_executed or 0,
                    "nodes_passed": execution.nodes_passed or 0,
                    "nodes_failed": execution.nodes_failed or 0,
                    "duration_seconds": execution.duration_seconds,
                    "severity": "critical" if execution.status == "failed" else "info",
                }
                fired = AlertTriggerService().trigger_for_workspace(
                    db,
                    workspace_id=execution.workspace_id,
                    trigger_type=trigger_type,
                    payload=payload,
                )
                print(f"Alert events queued for execution {execution_id}: {fired}")

                # F10 — also fire `check_failed` once per execution when at
                # least one check node produced rows_failed > 0 (the flow as
                # a whole may have status='completed').
                if (execution.nodes_failed or 0) > 0:
                    AlertTriggerService().trigger_for_workspace(
                        db,
                        workspace_id=execution.workspace_id,
                        trigger_type="check_failed",
                        payload={
                            **payload,
                            "title": flow.name,
                            "severity": "major",
                        },
                    )
                db.commit()
            except Exception as alert_exc:  # noqa: BLE001
                print(f"AlertTriggerService failed for execution {execution_id}: {alert_exc}")

    except Exception as e:
        print(f"Error sending flow completion notification: {str(e)}")
    finally:
        db.close()


@shared_task(name="flows.generate_execution_report")
def generate_execution_report(execution_id: str, workspace_id: str):
    """
    Generate a report for a completed flow execution

    Args:
        execution_id: Execution UUID as string
        workspace_id: Organization UUID as string
    """
    db = SessionLocal()
    try:
        import logging

        from app.models.flow import FlowNodeResult

        logger = logging.getLogger(__name__)

        execution = db.query(FlowExecution).filter(FlowExecution.id == UUID(execution_id)).first()

        if not execution:
            logger.warning(f"Execution {execution_id} not found for report generation")
            return

        flow = db.query(DQFlow).filter(DQFlow.id == execution.flow_id).first()
        if not flow:
            logger.warning(f"Flow for execution {execution_id} not found")
            return

        # Get all node results
        node_results = (
            db.query(FlowNodeResult)
            .filter(FlowNodeResult.execution_id == UUID(execution_id))
            .order_by(FlowNodeResult.execution_order)
            .all()
        )

        # Build comprehensive report
        report = {
            "execution_id": execution_id,
            "flow_id": str(flow.id),
            "flow_name": flow.name,
            "workspace_id": workspace_id,
            "executed_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "status": execution.status,
            "duration_seconds": execution.duration_seconds,
            "summary": {
                "total_nodes": execution.nodes_executed or 0,
                "nodes_passed": execution.nodes_passed or 0,
                "nodes_failed": execution.nodes_failed or 0,
                "nodes_skipped": execution.nodes_skipped or 0,
                "overall_quality_score": None,  # Calculate below
            },
            "nodes": [],
            "violations": [],
            "metadata": execution.result_summary or {},
        }

        # Process each node result
        total_checks = 0
        passed_checks = 0
        total_violations = 0

        for node_result in node_results:
            node_data = {
                "node_id": node_result.node_id,
                "node_type": node_result.node_type,
                "status": node_result.status,
                "execution_order": node_result.execution_order,
                "started_at": node_result.started_at.isoformat()
                if node_result.started_at
                else None,
                "completed_at": node_result.completed_at.isoformat()
                if node_result.completed_at
                else None,
                "duration_seconds": node_result.duration_seconds,
                "result": node_result.result or {},
                "error": node_result.error_message,
            }

            # Extract check results
            if node_result.node_type == "check" and node_result.result:
                check_result = node_result.result
                total_checks += 1
                if check_result.get("passed", False):
                    passed_checks += 1

                violations_count = check_result.get("failed_rows", 0)
                total_violations += violations_count

                # Add to violations list if failed
                if violations_count > 0:
                    report["violations"].append(
                        {
                            "node_id": node_result.node_id,
                            "check_type": check_result.get("check_type", "unknown"),
                            "column": check_result.get("column"),
                            "table": check_result.get("table"),
                            "failed_rows": violations_count,
                            "total_rows": check_result.get("total_rows", 0),
                            "failure_rate": check_result.get("failure_rate", 0),
                            "details": check_result.get("details"),
                        }
                    )

            report["nodes"].append(node_data)

        # Calculate overall quality score (0-100)
        if total_checks > 0:
            pass_rate = (passed_checks / total_checks) * 100
            report["summary"]["overall_quality_score"] = round(pass_rate, 2)

        report["summary"]["total_violations"] = total_violations

        # Store report in execution record
        execution.result_summary = execution.result_summary or {}
        execution.result_summary["detailed_report"] = report
        execution.result_summary["report_generated_at"] = datetime.utcnow().isoformat()

        db.commit()

        logger.info(f"Generated execution report for {execution_id}")
        logger.info(
            f"Quality Score: {report['summary']['overall_quality_score']}%, "
            f"Violations: {total_violations}, "
            f"Checks Passed: {passed_checks}/{total_checks}"
        )

        return report

    except Exception as e:
        print(f"Error generating execution report: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        db.close()


@shared_task(name="flows.cleanup_old_executions")
def cleanup_old_executions(days: int = 90):
    """
    Clean up old flow executions

    Args:
        days: Number of days to retain executions (default: 90)
    """
    db = SessionLocal()
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Delete old executions (CASCADE will handle node_results)
        deleted_count = (
            db.query(FlowExecution)
            .filter(
                FlowExecution.created_at < cutoff_date,
                FlowExecution.status.in_(["completed", "failed", "cancelled"]),
            )
            .delete(synchronize_session=False)
        )

        db.commit()

        print(f"Cleaned up {deleted_count} flow executions older than {days} days")

    except Exception as e:
        print(f"Error cleaning up old executions: {str(e)}")
        db.rollback()
    finally:
        db.close()


# Register tasks with Celery Beat schedule
@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """Setup periodic tasks for flows"""

    # Check for scheduled flows every minute
    sender.add_periodic_task(
        60.0,  # Every 60 seconds
        scheduled_flow_execution_task.s(),
        name="check-scheduled-flows",
    )

    # Clean up old executions daily at 3 AM
    sender.add_periodic_task(
        crontab(hour=3, minute=0),
        cleanup_old_executions.s(days=90),
        name="cleanup-old-flow-executions",
    )


# Import crontab for periodic tasks
from celery.schedules import crontab
