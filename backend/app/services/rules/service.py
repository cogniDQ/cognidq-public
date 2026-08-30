"""
Rule Service - CRUD operations and rule execution management
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.logging_config import logger
from app.models.rule import DQRule, RuleExecution, RuleViolation
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
from app.services.rules.compiler import RuleCompiler
from app.services.rules.executor import RuleExecutor


class RuleService:
    """Service for managing data quality rules"""

    def __init__(self, db: Session):
        self.db = db
        self.compiler = RuleCompiler()
        self.executor = RuleExecutor()

    # ========== CRUD Operations ==========

    async def create_rule(
        self, request: CreateRuleRequest, created_by: UUID, workspace_id: UUID | None = None
    ) -> RuleResponse:
        """Create a new data quality rule"""
        try:
            # Use workspace_id from parameter or request
            workspace_id = workspace_id or request.workspace_id
            if not workspace_id:
                raise ValueError("workspace_id is required")

            # Compile the canonical rule
            logger.info(f"Compiling rule: {request.name}")
            # Parse entity (schema.table.column or table.column)
            _entity = request.canonical_rule.entity or ""
            _parts = _entity.split(".")
            if len(_parts) >= 3:
                _target_schema = _parts[0]
                _target_table = _parts[1]
                _target_column = _parts[2]
            elif len(_parts) == 2:
                _target_schema = None
                _target_table = _parts[0]
                _target_column = _parts[1]
            else:
                _target_schema = None
                _target_table = _entity
                _target_column = None
            # Use explicit request fields if provided
            if request.target_schema:
                _target_schema = request.target_schema
            if request.target_table:
                _target_table = request.target_table
            if request.target_columns:
                _target_column = request.target_columns[0]
            compilation = self.compiler.compile_rule(
                request.canonical_rule.dict(),
                target_schema=_target_schema,
                target_table=_target_table,
                target_columns=[_target_column] if _target_column else None,
            )

            # Validate compilation succeeded
            if not compilation.get("compiled_sql"):
                raise ValueError("Rule compilation failed - no SQL generated")

            # Create rule model
            rule = DQRule(
                workspace_id=workspace_id,
                data_source_id=request.data_source_id,
                name=request.name,
                description=request.description,
                category=request.canonical_rule.dimension,
                rule_type=request.canonical_rule.type
                if hasattr(request.canonical_rule, "type")
                else None,
                canonical_rule=request.canonical_rule.dict(),
                compiled_sql=compilation["compiled_sql"],
                compiled_postgres=compilation.get("compiled_postgres"),
                compiled_mysql=compilation.get("compiled_mysql"),
                compiled_snowflake=compilation.get("compiled_snowflake"),
                compiled_spark=compilation.get("compiled_spark"),
                target_schema=_target_schema,
                target_table=_target_table,
                target_columns=[_target_column]
                if _target_column
                else (request.target_columns or []),
                status=RuleStatus.DRAFT,
                is_active=True,
                schedule=request.schedule.dict() if request.schedule else None,
                threshold_config=request.threshold_config.dict()
                if request.threshold_config
                else None,
                notification_config=request.notification_config.dict()
                if request.notification_config
                else None,
                tags=request.tags,
                created_by=created_by,
                owner_user_id=created_by,
            )

            self.db.add(rule)
            self.db.commit()
            self.db.refresh(rule)

            logger.info(f"Created rule: {rule.id} - {rule.name}")
            return self._to_response(rule)

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Database integrity error creating rule: {str(e)}")
            raise ValueError(
                f"Rule with name '{request.name}' already exists for this organization"
            )
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating rule: {str(e)}", exc_info=True)
            raise

    async def get_rule(
        self, rule_id: UUID, workspace_id: UUID, include_executions: bool = False
    ) -> RuleResponse | None:
        """Get a rule by ID"""
        query = select(DQRule).where(
            and_(DQRule.id == rule_id, DQRule.workspace_id == workspace_id)
        )

        if include_executions:
            query = query.options(selectinload(DQRule.executions))

        result = self.db.execute(query)
        rule = result.scalar_one_or_none()

        if not rule:
            return None

        return self._to_response(rule)

    async def list_rules(
        self,
        workspace_id: UUID,
        data_source_id: UUID | None = None,
        category: str | None = None,
        status: RuleStatus | None = None,
        is_active: bool | None = None,
        search: str | None = None,
        tags: list[str] | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[RuleResponse]:
        """List rules with filtering and pagination"""
        query = self.db.query(DQRule).filter(DQRule.workspace_id == workspace_id)

        # Apply filters
        if data_source_id:
            query = query.filter(DQRule.data_source_id == data_source_id)

        if category:
            query = query.filter(DQRule.category == category)

        if status:
            query = query.filter(DQRule.status == status)

        if is_active is not None:
            query = query.filter(DQRule.is_active == is_active)

        if search:
            search_filter = or_(
                DQRule.name.ilike(f"%{search}%"), DQRule.description.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)

        if tags:
            # Check if any of the tags match
            query = query.filter(DQRule.tags.overlap(tags))

        # Order by created_at descending, then paginate
        rules = query.order_by(desc(DQRule.created_at)).offset(skip).limit(limit).all()

        return [self._to_response(rule) for rule in rules]

    async def update_rule(
        self, rule_id: UUID, workspace_id: UUID, request: UpdateRuleRequest
    ) -> RuleResponse | None:
        """Update an existing rule"""
        try:
            # Fetch rule
            query = select(DQRule).where(
                and_(DQRule.id == rule_id, DQRule.workspace_id == workspace_id)
            )
            result = self.db.execute(query)
            rule = result.scalar_one_or_none()

            if not rule:
                return None

            # Check if canonical rule changed - recompile if needed
            needs_recompilation = False
            if request.canonical_rule and request.canonical_rule.dict() != rule.canonical_rule:
                needs_recompilation = True
                logger.info(f"Canonical rule changed for {rule_id}, recompiling...")

                compilation = self.compiler.compile_rule(request.canonical_rule.dict())

                if not compilation.get("compiled_sql"):
                    raise ValueError("Rule recompilation failed - no SQL generated")

                rule.canonical_rule = request.canonical_rule.dict()
                rule.category = request.canonical_rule.dimension
                rule.compiled_sql = compilation["compiled_sql"]
                rule.compiled_postgres = compilation.get("compiled_postgres")
                rule.compiled_mysql = compilation.get("compiled_mysql")
                rule.compiled_snowflake = compilation.get("compiled_snowflake")
                rule.compiled_spark = compilation.get("compiled_spark")
                rule.violation_sql = compilation.get("violation_sql")

                # Update target info
                entity = request.canonical_rule.entity
                rule.target_schema = entity.split(".")[0] if "." in entity else None
                rule.target_table = (
                    entity.split(".")[1]
                    if "." in entity and entity.count(".") == 2
                    else entity.split(".")[0]
                )
                rule.target_columns = [entity.split(".")[-1]]

            # Update other fields
            if request.name is not None:
                rule.name = request.name

            if request.description is not None:
                rule.description = request.description

            if request.category is not None:
                rule.category = request.category

            if request.rule_type is not None:
                rule.rule_type = request.rule_type

            if request.data_source_id is not None:
                rule.data_source_id = request.data_source_id

            if request.target_table is not None:
                rule.target_table = request.target_table

            if request.target_columns is not None:
                rule.target_columns = request.target_columns

            if request.status is not None:
                rule.status = request.status

            if request.is_active is not None:
                rule.is_active = request.is_active

            if request.schedule is not None:
                rule.schedule = request.schedule.dict() if request.schedule else None

            if request.threshold_config:
                rule.threshold_config = request.threshold_config.dict()

            if hasattr(request, "max_violations") and request.max_violations is not None:
                rule.max_violations = request.max_violations

            if request.notification_config is not None:
                rule.notification_config = (
                    request.notification_config.dict() if request.notification_config else None
                )

            if request.tags is not None:
                rule.tags = request.tags

            if request.metadata is not None:
                rule.meta_data = request.metadata

            rule.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(rule)

            logger.info(f"Updated rule: {rule_id} (recompiled: {needs_recompilation})")
            return self._to_response(rule)

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating rule {rule_id}: {str(e)}", exc_info=True)
            raise

    async def delete_rule(
        self, rule_id: UUID, workspace_id: UUID, soft_delete: bool = True
    ) -> bool:
        """Delete a rule (soft or hard delete)"""
        try:
            query = select(DQRule).where(
                and_(DQRule.id == rule_id, DQRule.workspace_id == workspace_id)
            )
            result = self.db.execute(query)
            rule = result.scalar_one_or_none()

            if not rule:
                return False

            if soft_delete:
                # Soft delete - just mark as inactive
                rule.is_active = False
                rule.status = RuleStatus.ARCHIVED
                rule.updated_at = datetime.utcnow()
                logger.info(f"Soft deleted rule: {rule_id}")
            else:
                # Hard delete - will cascade to executions and violations
                self.db.delete(rule)
                logger.info(f"Hard deleted rule: {rule_id}")

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting rule {rule_id}: {str(e)}", exc_info=True)
            raise

    # ========== Execution Operations ==========

    async def execute_rule(
        self, rule_id: UUID, workspace_id: UUID, request: ExecuteRuleRequest, executed_by: UUID
    ) -> ExecutionResponse:
        """Execute a data quality rule"""
        try:
            # Fetch rule
            query = select(DQRule).where(
                and_(DQRule.id == rule_id, DQRule.workspace_id == workspace_id)
            )
            result = self.db.execute(query)
            rule = result.scalar_one_or_none()

            if not rule:
                raise ValueError(f"Rule {rule_id} not found")

            if not rule.is_active:
                raise ValueError(f"Rule {rule_id} is not active")

            # Execute using the executor
            logger.info(f"Executing rule: {rule_id} ({rule.name})")
            execution = await self.executor.execute_rule(
                db=self.db,
                rule=rule,
                execution_type=request.execution_type,
                sample_only=request.sample_only,
                sample_size=request.sample_size,
                executed_by=executed_by,
            )

            return self._execution_to_response(execution)

        except Exception as e:
            logger.error(f"Error executing rule {rule_id}: {str(e)}", exc_info=True)
            raise

    async def get_execution(
        self, execution_id: UUID, workspace_id: UUID
    ) -> ExecutionResponse | None:
        """Get execution by ID"""
        query = (
            select(RuleExecution)
            .join(DQRule)
            .where(and_(RuleExecution.id == execution_id, DQRule.workspace_id == workspace_id))
            .options(joinedload(RuleExecution.rule))
        )

        result = self.db.execute(query)
        execution = result.scalar_one_or_none()

        if not execution:
            return None

        return self._execution_to_response(execution)

    async def get_execution_history(
        self,
        rule_id: UUID,
        workspace_id: UUID,
        status: ExecutionStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ExecutionResponse]:
        """Get execution history for a rule"""
        query = (
            select(RuleExecution)
            .join(DQRule)
            .where(and_(RuleExecution.rule_id == rule_id, DQRule.workspace_id == workspace_id))
        )

        if status:
            query = query.where(RuleExecution.status == status)

        query = query.order_by(desc(RuleExecution.created_at))
        query = query.offset(skip).limit(limit)

        result = self.db.execute(query)
        executions = result.scalars().all()

        return [self._execution_to_response(exec) for exec in executions]

    async def get_violations(
        self, execution_id: UUID, workspace_id: UUID, skip: int = 0, limit: int = 100
    ) -> list[ViolationResponse]:
        """Get violations for an execution"""
        # Verify execution belongs to organization
        query = (
            select(RuleViolation)
            .join(RuleExecution)
            .join(DQRule)
            .where(
                and_(
                    RuleViolation.execution_id == execution_id, DQRule.workspace_id == workspace_id
                )
            )
            .order_by(desc(RuleViolation.created_at))
            .offset(skip)
            .limit(limit)
        )

        result = self.db.execute(query)
        violations = result.scalars().all()

        return [self._violation_to_response(v) for v in violations]

    async def cancel_execution(self, execution_id: UUID, workspace_id: UUID) -> bool:
        """Cancel a running execution"""
        return await self.executor.cancel_execution(execution_id, workspace_id)

    # ========== Bulk Operations ==========

    async def bulk_execute(
        self, request: BulkExecuteRequest, workspace_id: UUID, executed_by: UUID
    ) -> BulkExecuteResponse:
        """Execute multiple rules"""
        results = []
        failed_count = 0

        for rule_id in request.rule_ids:
            try:
                exec_request = ExecuteRuleRequest(
                    execution_type=request.execution_type,
                    sample_only=request.sample_only,
                    sample_size=request.sample_size,
                )

                execution = await self.execute_rule(
                    rule_id=rule_id,
                    workspace_id=workspace_id,
                    request=exec_request,
                    executed_by=executed_by,
                )

                results.append(
                    {
                        "rule_id": str(rule_id),
                        "execution_id": str(execution.id),
                        "status": execution.status,
                        "success": True,
                    }
                )

            except Exception as e:
                logger.error(f"Failed to execute rule {rule_id} in bulk: {str(e)}")
                failed_count += 1
                results.append(
                    {"rule_id": str(rule_id), "status": "failed", "error": str(e), "success": False}
                )

        return BulkExecuteResponse(
            total=len(request.rule_ids),
            successful=len(request.rule_ids) - failed_count,
            failed=failed_count,
            results=results,
        )

    # ========== Statistics & Summary ==========

    async def get_execution_summary(
        self, workspace_id: UUID, rule_id: UUID | None = None, days: int = 30
    ) -> ExecutionSummary:
        """Get execution summary statistics"""
        from datetime import timedelta

        since = datetime.utcnow() - timedelta(days=days)

        query = (
            select(RuleExecution)
            .join(DQRule)
            .where(and_(DQRule.workspace_id == workspace_id, RuleExecution.created_at >= since))
        )

        if rule_id:
            query = query.where(RuleExecution.rule_id == rule_id)

        result = self.db.execute(query)
        executions = result.scalars().all()

        total = len(executions)
        passed = sum(
            1
            for e in executions
            if e.status == ExecutionStatus.COMPLETED
            and (e.pass_rate or 0) >= (e.rule.pass_threshold or 100)
        )
        failed = sum(
            1
            for e in executions
            if e.status == ExecutionStatus.FAILED
            or ((e.pass_rate or 0) < (e.rule.pass_threshold or 100))
        )
        running = sum(1 for e in executions if e.status == ExecutionStatus.RUNNING)

        avg_duration = None
        if executions and any(e.duration_seconds for e in executions):
            durations = [e.duration_seconds for e in executions if e.duration_seconds]
            avg_duration = sum(durations) / len(durations) if durations else None

        avg_pass_rate = None
        if executions and any(e.pass_rate for e in executions):
            pass_rates = [float(e.pass_rate) for e in executions if e.pass_rate is not None]
            avg_pass_rate = sum(pass_rates) / len(pass_rates) if pass_rates else None

        return ExecutionSummary(
            total_executions=total,
            passed=passed,
            failed=failed,
            running=running,
            avg_duration_seconds=avg_duration,
            avg_pass_rate=avg_pass_rate,
        )

    # ========== Scheduling (Placeholder) ==========

    async def schedule_rule(
        self, rule_id: UUID, workspace_id: UUID, schedule: ScheduleConfig
    ) -> RuleResponse:
        """Set up a schedule for rule execution"""
        # This will be implemented with Celery Beat integration
        update = UpdateRuleRequest(schedule=schedule)
        return await self.update_rule(rule_id, workspace_id, update)

    async def unschedule_rule(self, rule_id: UUID, workspace_id: UUID) -> RuleResponse:
        """Remove schedule from rule"""
        update = UpdateRuleRequest(schedule=None)
        return await self.update_rule(rule_id, workspace_id, update)

    # ========== Helper Methods ==========

    def _to_response(self, rule: DQRule) -> RuleResponse:
        """Convert DQRule model to RuleResponse schema"""
        return RuleResponse(
            id=str(rule.id),
            workspace_id=str(rule.workspace_id),
            data_source_id=str(rule.data_source_id) if rule.data_source_id else None,
            name=rule.name,
            description=rule.description,
            category=rule.category,
            rule_type=rule.rule_type,
            canonical_rule=rule.canonical_rule,
            compiled_sql=rule.compiled_sql,
            compiled_spark=rule.compiled_spark,
            target_schema=rule.target_schema,
            target_table=rule.target_table,
            target_columns=rule.target_columns,
            status=rule.status,
            is_active=rule.is_active,
            schedule=rule.schedule,
            threshold_config=rule.threshold_config,
            notification_config=rule.notification_config,
            tags=rule.tags,
            metadata=rule.meta_data,
            created_by=str(rule.created_by) if rule.created_by else None,
            updated_by=str(rule.updated_by) if rule.updated_by else None,
            owner_user_id=str(rule.owner_user_id) if rule.owner_user_id else None,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )

    def _execution_to_response(self, execution: RuleExecution) -> ExecutionResponse:
        """Convert RuleExecution model to ExecutionResponse schema"""
        return ExecutionResponse(
            id=str(execution.id),
            rule_id=str(execution.rule_id),
            execution_type=execution.execution_type,
            status=execution.status,
            started_at=execution.started_at,
            completed_at=execution.completed_at,
            duration_seconds=execution.duration_seconds,
            rows_scanned=execution.rows_scanned,
            rows_passed=execution.rows_passed,
            rows_failed=execution.rows_failed,
            pass_rate=float(execution.pass_rate) if execution.pass_rate else None,
            error_message=execution.error_message,
            error_details=execution.error_details,
            result_details=execution.result_details,
            execution_params=getattr(execution, "execution_params", None),
            environment=getattr(execution, "environment", None),
            executed_by=str(execution.executed_by) if execution.executed_by else None,
            created_at=execution.created_at,
        )

    def _violation_to_response(self, violation: RuleViolation) -> ViolationResponse:
        """Convert RuleViolation model to ViolationResponse schema"""
        return ViolationResponse(
            id=str(violation.id),
            execution_id=str(violation.execution_id),
            row_identifier=violation.row_identifier,
            row_number=violation.row_number,
            violation_details=violation.violation_details or {},
            severity=violation.severity,
            category=violation.category,
            is_sample=bool(violation.is_sample),
            metadata=None,
            created_at=violation.created_at,
        )
