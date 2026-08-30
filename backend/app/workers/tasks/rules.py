"""
Celery Tasks for Rule Execution
Background tasks for async rule execution and scheduling
"""

from datetime import datetime
from uuid import UUID

from celery import Task

from app.core.logging_config import logger
from app.models.database import get_db, get_db_context
from app.schemas.rule import ExecuteRuleRequest, ExecutionType
from app.services.rules.service import RuleService
from app.workers.celery_app import celery_app


class DatabaseTask(Task):
    """Base task that provides database session"""

    _db_session = None

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Clean up database session after task completion"""
        if self._db_session is not None:
            self._db_session.close()


@celery_app.task(bind=True, base=DatabaseTask, name="rules.execute_rule")
def execute_rule_task(
    self,
    rule_id: str,
    workspace_id: str,
    executed_by: str,
    execution_type: str = "scheduled",
    sample_only: bool = False,
    sample_size: int | None = None,
):
    """
    Execute a data quality rule asynchronously

    Args:
        rule_id: UUID of the rule to execute
        workspace_id: UUID of the organization
        executed_by: UUID of the user who triggered execution
        execution_type: Type of execution (scheduled, manual, triggered)
        sample_only: Whether to run on sample data only
        sample_size: Number of rows to sample (if sample_only=True)

    Returns:
        dict: Execution result summary
    """
    logger.info(f"Starting async rule execution: {rule_id}")

    try:
        # Get database session
        db = next(get_db_context())
        self._db_session = db

        # Create service
        service = RuleService(db)

        # Create execution request
        request = ExecuteRuleRequest(
            execution_type=ExecutionType(execution_type),
            sample_only=sample_only,
            sample_size=sample_size,
        )

        # Execute rule
        execution = service.execute_rule(
            rule_id=UUID(rule_id),
            workspace_id=UUID(workspace_id),
            request=request,
            executed_by=UUID(executed_by),
        )

        logger.info(f"Completed async rule execution: {rule_id} - Status: {execution.status}")

        return {
            "execution_id": str(execution.id),
            "rule_id": str(execution.rule_id),
            "status": execution.status,
            "pass_rate": float(execution.pass_rate) if execution.pass_rate else None,
            "violation_count": execution.violation_count,
            "duration_seconds": execution.duration_seconds,
        }

    except Exception as e:
        logger.error(f"Error in async rule execution {rule_id}: {str(e)}", exc_info=True)
        # Re-raise to mark task as failed
        raise


@celery_app.task(bind=True, base=DatabaseTask, name="rules.bulk_execute")
def bulk_execute_rules_task(
    self,
    rule_ids: list[str],
    workspace_id: str,
    executed_by: str,
    execution_type: str = "manual",
    sample_only: bool = False,
    sample_size: int | None = None,
):
    """
    Execute multiple rules in parallel

    Args:
        rule_ids: List of rule UUIDs to execute
        workspace_id: UUID of the organization
        executed_by: UUID of the user who triggered execution
        execution_type: Type of execution
        sample_only: Whether to run on sample data only
        sample_size: Number of rows to sample

    Returns:
        dict: Bulk execution summary
    """
    logger.info(f"Starting bulk rule execution: {len(rule_ids)} rules")

    results = []
    failed_count = 0

    try:
        # Get database session
        db = next(get_db())
        self._db_session = db

        # Create service
        service = RuleService(db)

        # Create execution request
        request = ExecuteRuleRequest(
            execution_type=ExecutionType(execution_type),
            sample_only=sample_only,
            sample_size=sample_size,
        )

        # Execute each rule
        for rule_id in rule_ids:
            try:
                execution = service.execute_rule(
                    rule_id=UUID(rule_id),
                    workspace_id=UUID(workspace_id),
                    request=request,
                    executed_by=UUID(executed_by),
                )

                results.append(
                    {
                        "rule_id": rule_id,
                        "execution_id": str(execution.id),
                        "status": execution.status,
                        "success": True,
                    }
                )

            except Exception as e:
                logger.error(f"Failed to execute rule {rule_id} in bulk: {str(e)}")
                failed_count += 1
                results.append(
                    {"rule_id": rule_id, "status": "failed", "error": str(e), "success": False}
                )

        logger.info(
            f"Completed bulk execution: {len(rule_ids) - failed_count} successful, {failed_count} failed"
        )

        return {
            "total": len(rule_ids),
            "successful": len(rule_ids) - failed_count,
            "failed": failed_count,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error in bulk rule execution: {str(e)}", exc_info=True)
        raise


@celery_app.task(bind=True, base=DatabaseTask, name="rules.scheduled_execution")
def scheduled_rule_execution_task(self):
    """
    Periodic task to execute scheduled rules
    Runs every minute to check for rules that need execution

    This task:
    1. Finds all active rules with schedules
    2. Checks if they're due for execution based on cron expression
    3. Triggers execution for due rules
    """
    logger.info("Starting scheduled rule execution check")

    try:
        from croniter import croniter

        # Get database session
        db = next(get_db_context())
        self._db_session = db

        # Create service
        RuleService(db)

        # Get all active rules with schedules
        # TODO: This needs a dedicated query method in RuleService
        from sqlalchemy import and_, select

        from app.models.rule import DQRule

        query = select(DQRule).where(and_(DQRule.is_active == True, DQRule.schedule != None))

        result = db.execute(query)
        scheduled_rules = result.scalars().all()

        logger.info(f"Found {len(scheduled_rules)} rules with schedules")

        executed_count = 0
        now = datetime.utcnow()

        for rule in scheduled_rules:
            try:
                schedule_config = rule.schedule
                if not schedule_config or "cron" not in schedule_config:
                    continue

                cron_expr = schedule_config["cron"]

                # Check if rule is due for execution
                cron = croniter(cron_expr, now)
                cron.get_next(datetime)
                prev_run = cron.get_prev(datetime)

                # If prev_run is within the last minute, execute
                time_diff = (now - prev_run).total_seconds()
                if 0 <= time_diff <= 60:
                    # Check when rule was last executed
                    # TODO: Add method to get last execution time
                    from app.models.rule import RuleExecution

                    last_exec_query = (
                        select(RuleExecution)
                        .where(RuleExecution.rule_id == rule.id)
                        .order_by(RuleExecution.created_at.desc())
                        .limit(1)
                    )
                    last_exec_result = db.execute(last_exec_query)
                    last_exec = last_exec_result.scalar_one_or_none()

                    # Only execute if not already executed in the last minute
                    should_execute = True
                    if last_exec:
                        last_exec_age = (now - last_exec.created_at).total_seconds()
                        if last_exec_age < 60:
                            should_execute = False

                    if should_execute:
                        logger.info(f"Executing scheduled rule: {rule.id} - {rule.name}")

                        # Trigger async execution
                        execute_rule_task.delay(
                            rule_id=str(rule.id),
                            workspace_id=str(rule.workspace_id),
                            executed_by=str(rule.created_by),  # Use rule creator as executor
                            execution_type="scheduled",
                        )

                        executed_count += 1

            except Exception as e:
                logger.error(f"Error checking schedule for rule {rule.id}: {str(e)}")
                continue

        logger.info(f"Scheduled execution check complete: {executed_count} rules triggered")

        return {
            "checked": len(scheduled_rules),
            "executed": executed_count,
            "timestamp": now.isoformat(),
        }

    except Exception as e:
        logger.error(f"Error in scheduled execution task: {str(e)}", exc_info=True)
        raise


@celery_app.task(bind=True, base=DatabaseTask, name="rules.cleanup_old_violations")
def cleanup_old_violations_task(self, days: int = 90):
    """
    Cleanup old violation records

    Args:
        days: Delete violations older than this many days

    Returns:
        dict: Cleanup summary
    """
    logger.info(f"Starting violation cleanup: removing violations older than {days} days")

    try:
        from datetime import timedelta

        from app.models.rule import RuleViolation

        # Get database session
        db = next(get_db_context())
        self._db_session = db

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Delete old violations
        from sqlalchemy import delete

        stmt = delete(RuleViolation).where(RuleViolation.created_at < cutoff_date)

        result = db.execute(stmt)
        db.commit()

        deleted_count = result.rowcount

        logger.info(f"Cleaned up {deleted_count} old violation records")

        return {"deleted": deleted_count, "cutoff_date": cutoff_date.isoformat()}

    except Exception as e:
        logger.error(f"Error in violation cleanup: {str(e)}", exc_info=True)
        db.rollback()
        raise


# Register periodic tasks with Celery Beat
# Add this to celery_app configuration:
"""
celery_app.conf.beat_schedule = {
    'scheduled-rule-execution': {
        'task': 'rules.scheduled_execution',
        'schedule': 60.0,  # Every minute
    },
    'cleanup-old-violations': {
        'task': 'rules.cleanup_old_violations',
        'schedule': 86400.0,  # Daily
        'args': (90,)  # Keep 90 days
    },
}
"""
