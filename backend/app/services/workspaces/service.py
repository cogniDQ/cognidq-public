"""
Workspace Service Layer — F002 P04

Orchestrates workspace operations combining validation, repository, RBAC, and audit.
All database operations execute within a single transaction.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.audit.models import AuditEntry
from app.services.audit.service import AuditService as _AuditService
from app.services.workspaces.exceptions import (
    DuplicateNameError,
    ForbiddenTransitionError,
    LastActiveWorkspaceError,
    TenantNotActiveError,
    TenantNotFoundError,
    WorkspaceArchivedError,
    WorkspaceNotFoundError,
    WorkspaceValidationError,
)
from app.services.workspaces.metrics import (
    emit_workspace_detail_count_query_failure,
    emit_workspace_detail_request_count,
    emit_workspace_list_request_count,
    emit_workspace_status_change_failure,
    emit_workspace_update_failure,
)
from app.services.workspaces.models import (
    Workspace,
    WorkspaceStatus,
)
from app.services.workspaces.rbac import RBACServiceInterface
from app.services.workspaces.registry import (
    DatasetRegistryInterface,
    DatasetRegistryStub,
    MemberRegistryInterface,
    MemberRegistryStub,
)
from app.services.workspaces.repository import (
    AuditLogRepository,
    AuditLogWriter,
    TenantRepository,
    WorkspaceRepository,
)
from app.services.workspaces.validation import (
    ValidationResult,
    normalize_workspace_name,
    validate_create_payload,
    validate_status_reason,
)

logger = logging.getLogger(__name__)


class WorkspaceService:
    """
    Business logic for workspace operations.

    Implements the 3-write atomic transaction pattern:
    1. Validate Tenant status (active)
    2. INSERT workspace
    3. Grant workspace_administrator role
    4. Write audit log entry

    All operations execute within a single database transaction provided by the caller.
    """

    def __init__(
        self,
        workspace_repo: WorkspaceRepository,
        tenant_repo: TenantRepository,
        audit_writer: AuditLogWriter,
        rbac_service: RBACServiceInterface,
        dataset_registry: DatasetRegistryInterface | None = None,
        member_registry: MemberRegistryInterface | None = None,
        audit_log_repo: AuditLogRepository | None = None,
        audit_service: _AuditService | None = None,
    ):
        """
        Initialize service with repository dependencies.

        Args:
            workspace_repo: Repository for workspace persistence
            tenant_repo: Repository for tenant lookups
            audit_writer: Writer for audit log entries (legacy F002)
            rbac_service: RBAC service for role grants
            dataset_registry: Registry for dataset counts (defaults to stub returning 0)
            member_registry: Registry for member counts (defaults to stub returning 0)
            audit_log_repo: Repository for audit log reads (defaults to new instance)
            audit_service: F052 generic audit service (defaults to new instance)
        """
        self.workspace_repo = workspace_repo
        self.tenant_repo = tenant_repo
        self.audit_writer = audit_writer
        self.rbac_service = rbac_service
        self.dataset_registry: DatasetRegistryInterface = dataset_registry or DatasetRegistryStub()
        self.member_registry: MemberRegistryInterface = member_registry or MemberRegistryStub()
        self.audit_log_repo: AuditLogRepository = audit_log_repo or AuditLogRepository()
        self.audit_service: _AuditService = audit_service or _AuditService()

    def create_workspace(
        self,
        db: Session,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        actor_role: str,
        raw_payload: dict[str, Any],
        request_id: uuid.UUID | None = None,
        source_ip: str | None = None,
    ) -> Workspace:
        """
        Create a new workspace with atomic 3-write transaction.

        Flow per TDD §5.2 Flow A:
        1. Validate payload (pure validation - no DB)
        2. Check Tenant exists and is active
        3. INSERT workspace row
        4. Grant workspace_administrator role to actor
        5. Write audit log entry

        All database writes execute within the provided Session transaction.
        If any step fails, the entire transaction is rolled back by the caller.

        Args:
            db: Active SQLAlchemy session (transaction context)
            tenant_id: Tenant UUID from JWT token
            actor_id: Actor UUID from JWT token
            actor_role: Actor role from JWT token
            raw_payload: Unvalidated request JSON payload
            request_id: Optional request ID for audit log
            source_ip: Optional source IP for audit log

        Returns:
            Workspace: Created workspace with all fields populated

        Raises:
            ValidationError: If payload validation fails (handled by controller)
            TenantNotFoundError: If tenant does not exist → HTTP 404
            TenantNotActiveError: If tenant is not active → HTTP 422
            DuplicateNameError: If workspace name already exists → HTTP 422
            DuplicateSlugError: If workspace slug already exists → HTTP 422
            RoleGrantFailedError: If role grant fails → HTTP 500
            AuditWriteFailedError: If audit write fails → HTTP 500
        """
        logger.info("create_workspace started: tenant_id=%s actor_id=%s", tenant_id, actor_id)

        # Step 1: Validate payload (pure function - no DB access)
        validation_result: ValidationResult = validate_create_payload(raw_payload)

        # Controller should handle validation errors, but defend here
        if not validation_result.is_valid:
            logger.warning(
                "create_workspace validation failed: tenant_id=%s errors=%s",
                tenant_id,
                validation_result.errors,
            )
            # This should not happen - controller should catch validation errors
            # But if it does, let it propagate as generic exception
            raise ValueError(f"Validation failed: {validation_result.errors}")

        normalized = validation_result.normalized_payload

        # Step 2: Check Tenant exists and is active
        # Raises TenantNotFoundError if not found
        tenant = self.tenant_repo.find_tenant_by_id(db, tenant_id)

        if tenant["status"] != "active":
            logger.warning(
                "create_workspace blocked: tenant_id=%s status=%s", tenant_id, tenant["status"]
            )
            raise TenantNotActiveError(
                f"Tenant {tenant_id} is not active (status={tenant['status']})"
            )

        # Step 3: Build Workspace domain model
        # Apply UTC default if timezone not provided
        default_timezone = normalized.get("default_timezone", "UTC")

        # Generate lowercase name for uniqueness constraint
        workspace_name_lower = normalized["workspace_name"].lower()

        now = datetime.now(UTC)

        workspace = Workspace(
            tenant_id=tenant_id,
            workspace_name=normalized["workspace_name"],
            workspace_name_lower=workspace_name_lower,
            workspace_slug=normalized["workspace_slug"],
            description=normalized.get("description"),
            default_timezone=default_timezone,
            status=WorkspaceStatus.active,
            status_reason=None,
            created_at=now,
            updated_at=now,
            created_by=actor_id,
            updated_by=actor_id,
            version=0,
        )

        # Step 4: INSERT workspace
        # Raises DuplicateNameError or DuplicateSlugError on conflict
        created_workspace = self.workspace_repo.insert_workspace(db, workspace)

        logger.info(
            "workspace inserted: workspace_id=%s tenant_id=%s name=%s",
            created_workspace.workspace_id,
            tenant_id,
            created_workspace.workspace_name,
        )

        # Step 5: Grant workspace_administrator role
        # Raises RoleGrantFailedError on failure
        self.rbac_service.grant_workspace_admin(
            workspace_id=created_workspace.workspace_id,
            actor_id=actor_id,
            transaction_context=db,
        )

        logger.info(
            "role granted: workspace_id=%s actor_id=%s role=workspace_administrator",
            created_workspace.workspace_id,
            actor_id,
        )

        # Step 6: Write audit log entry via F052 AuditService
        # Build new_data dict (exclude workspace_name_lower and version per TDD §9.3)
        new_data = {
            "workspace_id": str(created_workspace.workspace_id),
            "tenant_id": str(created_workspace.tenant_id),
            "workspace_name": created_workspace.workspace_name,
            "workspace_slug": created_workspace.workspace_slug,
            "description": created_workspace.description,
            "default_timezone": created_workspace.default_timezone,
            "status": created_workspace.status.value,
            "status_reason": created_workspace.status_reason,
            "created_at": created_workspace.created_at.isoformat(),
            "updated_at": created_workspace.updated_at.isoformat(),
            "created_by": str(created_workspace.created_by),
            "updated_by": str(created_workspace.updated_by),
        }

        audit_entry = AuditEntry(
            tenant_id=tenant_id,
            action_type="workspace_created",
            target_entity_type="workspace",
            target_entity_id=created_workspace.workspace_id,
            after_state=new_data,
            actor_type="user",
            actor_role=actor_role,
            workspace_id=created_workspace.workspace_id,
            actor_id=actor_id,
            before_state=None,
            request_id=request_id,
            source_ip=source_ip,
        )

        # Raises AuditWriteFailedError on failure
        self.audit_service.write(db, audit_entry)

        logger.info(
            "audit log written: workspace_id=%s action_type=workspace_created",
            created_workspace.workspace_id,
        )

        logger.info(
            "create_workspace completed: workspace_id=%s tenant_id=%s",
            created_workspace.workspace_id,
            tenant_id,
        )

        return created_workspace

    def update_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        raw_payload: dict,
        request_id: str | None = None,
        source_ip: str | None = None,
    ) -> Workspace | None:
        """
        Update workspace metadata per TDD §5.2 Flow B (16 steps).

        Returns None if no-op detected (empty payload or all values identical).
        Raises WorkspaceNotFoundError, WorkspaceArchivedError, TenantNotFoundError,
        TenantNotActiveError, DuplicateNameError, AuditWriteFailedError.
        """
        logger.info(
            "update_workspace called: workspace_id=%s tenant_id=%s actor_id=%s",
            workspace_id,
            tenant_id,
            actor_id,
        )

        # --- FLOW B: Steps 1-16 ---

        # Step 1: Begin transaction (already in transaction context)
        # Step 2: SELECT FOR UPDATE with tenant isolation
        workspace = self.workspace_repo.find_by_id(
            db=db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            for_update=True,  # Pessimistic locking
        )
        if not workspace:
            logger.warning("update_workspace failed: workspace_id=%s not found", workspace_id)
            emit_workspace_update_failure("workspace_not_found")
            raise WorkspaceNotFoundError(
                f"Workspace {workspace_id} not found in tenant {tenant_id}"
            )

        # Step 3: Check workspace status
        if workspace.status == WorkspaceStatus.archived:
            logger.warning("update_workspace failed: workspace_id=%s is archived", workspace_id)
            emit_workspace_update_failure("workspace_archived")
            raise WorkspaceArchivedError(f"Cannot update archived workspace {workspace_id}")

        # Step 4: Check tenant status
        tenant = self.tenant_repo.find_tenant_by_id(db, tenant_id)
        if not tenant:
            logger.warning("update_workspace failed: tenant_id=%s not found", tenant_id)
            emit_workspace_update_failure("tenant_not_found")
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        if tenant["status"] != "active":
            logger.warning(
                "update_workspace failed: tenant_id=%s status=%s", tenant_id, tenant["status"]
            )
            emit_workspace_update_failure("tenant_not_active")
            raise TenantNotActiveError(f"Tenant {tenant_id} status is {tenant['status']}")

        # Step 5: Normalize incoming payload (already done by controller via validate_update_payload)
        # raw_payload is actually validation_result.normalized_payload from controller
        normalized_payload = raw_payload

        # Step 6: No-op detection - compare normalized values with current state
        if not normalized_payload:
            # Empty payload {} → no-op
            logger.info("update_workspace no-op: empty payload workspace_id=%s", workspace_id)
            return None

        has_changes = False
        for field, new_value in normalized_payload.items():
            current_value = getattr(workspace, field)
            if new_value != current_value:
                has_changes = True
                break

        if not has_changes:
            logger.info(
                "update_workspace no-op: all values identical workspace_id=%s", workspace_id
            )
            return None

        # Step 7: Validation already done by controller via validate_update_payload
        # raw_payload is already validated and normalized, skip redundant check

        # Step 8: Duplicate name check (only if workspace_name changed)
        if "workspace_name" in normalized_payload:
            new_name = normalized_payload["workspace_name"]
            if new_name != workspace.workspace_name:
                # Check for duplicate workspace_name_lower in same tenant
                normalized_lower = normalize_workspace_name(new_name).lower()
                query = text("""
                    SELECT workspace_id FROM control.workspaces
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                    AND workspace_name_lower = :name_lower
                    AND workspace_id != CAST(:workspace_id AS UUID)
                    LIMIT 1
                """)
                result = db.execute(
                    query,
                    {
                        "tenant_id": str(tenant_id),
                        "name_lower": normalized_lower,
                        "workspace_id": str(workspace_id),
                    },
                ).first()
                if result:
                    logger.warning(
                        "update_workspace failed: duplicate name workspace_id=%s name=%s",
                        workspace_id,
                        new_name,
                    )
                    emit_workspace_update_failure("duplicate_name")
                    raise DuplicateNameError(
                        f"Workspace name '{new_name}' already exists in tenant"
                    )

        # Step 9: Store previous state for audit log (only changed fields)
        previous_data = {}
        for field in normalized_payload.keys():
            previous_data[field] = getattr(workspace, field)

        # Step 10: Apply updates and increment version
        for field, new_value in normalized_payload.items():
            setattr(workspace, field, new_value)

        # Auto-maintain workspace_name_lower
        if "workspace_name" in normalized_payload:
            workspace.workspace_name_lower = normalized_payload["workspace_name"].lower()

        # Increment version for optimistic locking
        workspace.version += 1
        workspace.updated_at = datetime.utcnow()

        # Step 11: Update repository (persist changes)
        self.workspace_repo.update_workspace(db, workspace)

        logger.info(
            "workspace updated: workspace_id=%s version=%s",
            workspace.workspace_id,
            workspace.version,
        )

        # Step 12: Write audit log via F052 AuditService (only changed fields)
        audit_entry = AuditEntry(
            tenant_id=tenant_id,
            action_type="workspace_metadata_updated",
            target_entity_type="workspace",
            target_entity_id=workspace_id,
            after_state=normalized_payload,  # Only changed fields
            actor_type="user",
            actor_role="workspace_administrator",
            workspace_id=workspace_id,
            actor_id=actor_id,
            before_state=previous_data,  # Only changed fields
            request_id=request_id,
            source_ip=source_ip,
        )

        self.audit_service.write(db, audit_entry)

        logger.info(
            "audit log written: workspace_id=%s action_type=workspace_updated", workspace_id
        )

        # Step 13: Commit transaction (handled by caller)

        # Step 14: Compute updated_fields string for metric emission by caller
        # (comma-separated, alphabetically sorted per TDD §12.1)
        # Note: caller emits workspace_metadata_update_count after db.commit().
        updated_fields = ",".join(sorted(normalized_payload.keys()))

        # Step 15: Log success
        logger.info(
            "update_workspace completed: workspace_id=%s updated_fields=%s",
            workspace_id,
            updated_fields,
        )

        # Step 16: Return updated workspace
        return workspace

    # -----------------------------------------------------------------------
    # archive_workspace — Flow C (TDD §5.2)
    # -----------------------------------------------------------------------

    def archive_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        actor_role: str,
        raw_payload: dict,
        request_id: str | None = None,
        source_ip: str | None = None,
    ) -> Workspace:
        """
        Archive an active workspace (Flow C — 12 steps).

        Ordering rule (A-8): workspace status check is performed BEFORE
        status_reason validation.  An already-archived workspace returns
        HTTP 422 ``forbidden_transition`` even if ``status_reason`` is absent
        or invalid.

        Advisory lock (TDD §11.5): acquired on the Tenant namespace with
        ``pg_advisory_xact_lock(hashtext(:tenant_id))`` immediately after
        the ``SELECT FOR UPDATE`` row lock so that the active-workspace count
        is serialised against concurrent workspace creation requests.

        Raises
        ------
        WorkspaceNotFoundError       → HTTP 404
        ForbiddenTransitionError     → HTTP 422 forbidden_transition
        WorkspaceValidationError     → HTTP 422 (status_reason field errors)
        LastActiveWorkspaceError     → HTTP 409 last_active_workspace
        AuditWriteFailedError        → HTTP 500
        """
        logger.info(
            "archive_workspace called: workspace_id=%s tenant_id=%s actor_id=%s",
            workspace_id,
            tenant_id,
            actor_id,
        )

        # Step 1: begin transaction (already in context)

        # Step 2: SELECT FOR UPDATE with tenant isolation
        workspace = self.workspace_repo.find_by_id(
            db=db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            for_update=True,
        )
        if not workspace:
            raise WorkspaceNotFoundError(
                f"Workspace {workspace_id} not found in tenant {tenant_id}"
            )
        if workspace.status != WorkspaceStatus.active:
            logger.warning(
                "archive_workspace forbidden_transition: workspace_id=%s status=%s",
                workspace_id,
                workspace.status.value,
            )
            emit_workspace_status_change_failure("forbidden_transition")
            raise ForbiddenTransitionError(
                f"Workspace {workspace_id} is not active (current status="
                f"{workspace.status.value}). Only active workspaces can be archived."
            )

        # Acquire advisory lock on Tenant namespace (TDD §11.5)
        # Must be inside transaction, immediately after SELECT FOR UPDATE.
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:tenant_id))"),
            {"tenant_id": str(tenant_id)},
        )

        # Step 5: validate status_reason (after status check, per A-8)
        errors: list = []
        normalized_reason = validate_status_reason(raw_payload.get("status_reason"), errors)
        if errors:
            emit_workspace_status_change_failure("missing_reason")
            raise WorkspaceValidationError(errors)

        # read confirm_last_workspace (default False if absent)
        confirm_last_workspace = raw_payload.get("confirm_last_workspace", False)

        # Step 6: last-workspace guard
        active_count = self.workspace_repo.count_active_workspaces(db, tenant_id)
        if active_count == 1 and confirm_last_workspace is not True:
            logger.warning(
                "archive_workspace last_active_workspace: workspace_id=%s tenant_id=%s",
                workspace_id,
                tenant_id,
            )
            emit_workspace_status_change_failure("last_active_workspace")
            raise LastActiveWorkspaceError(
                f"Workspace {workspace_id} is the last active workspace in tenant {tenant_id}."
            )

        # Step 8: store previous state for audit
        previous_status_reason = workspace.status_reason

        # Step 8 continued: apply mutation
        now = datetime.now(UTC)
        workspace.status = WorkspaceStatus.archived
        workspace.status_reason = normalized_reason
        workspace.updated_at = now
        workspace.updated_by = actor_id
        workspace.version += 1

        # Step 9: persist via repository
        self.workspace_repo.update_workspace(db, workspace)

        logger.info(
            "workspace archived: workspace_id=%s version=%s",
            workspace.workspace_id,
            workspace.version,
        )

        # Step 10: write workspace_archived audit entry via F052 AuditService
        # previous_status_reason read from locked row before mutation (A-5)
        previous_data = {"status": "active", "status_reason": previous_status_reason}
        new_data = {"status": "archived", "status_reason": normalized_reason}

        audit_entry = AuditEntry(
            tenant_id=tenant_id,
            action_type="workspace_archived",
            target_entity_type="workspace",
            target_entity_id=workspace_id,
            after_state=new_data,
            actor_type="user",
            actor_role=actor_role,
            workspace_id=workspace_id,
            actor_id=actor_id,
            before_state=previous_data,
            request_id=request_id,
            source_ip=source_ip,
        )
        self.audit_service.write(db, audit_entry)

        logger.info(
            "audit log written: workspace_id=%s action_type=workspace_archived",
            workspace_id,
        )

        # Step 11: commit handled by caller

        # Caller (endpoint) emits workspace_status_change_success after commit.

        logger.info(
            "archive_workspace completed: workspace_id=%s tenant_id=%s",
            workspace_id,
            tenant_id,
        )

        return workspace

    # -----------------------------------------------------------------------
    # restore_workspace — Flow D (TDD §5.2)
    # -----------------------------------------------------------------------

    def restore_workspace(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        actor_role: str,
        request_id: str | None = None,
        source_ip: str | None = None,
    ) -> Workspace:
        """
        Restore an archived workspace (Flow D — 11 steps).

        No request body fields are required.  ``status_reason`` is cleared
        to exactly ``NULL`` on restoration (never ``""``).

        Raises
        ------
        WorkspaceNotFoundError   → HTTP 404
        ForbiddenTransitionError → HTTP 422 forbidden_transition
        TenantNotActiveError     → HTTP 422 tenant_not_active
        AuditWriteFailedError    → HTTP 500
        """
        logger.info(
            "restore_workspace called: workspace_id=%s tenant_id=%s actor_id=%s",
            workspace_id,
            tenant_id,
            actor_id,
        )

        # Step 1: begin transaction (already in context)

        # Step 2: SELECT FOR UPDATE with tenant isolation
        workspace = self.workspace_repo.find_by_id(
            db=db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            for_update=True,
        )
        if not workspace:
            raise WorkspaceNotFoundError(
                f"Workspace {workspace_id} not found in tenant {tenant_id}"
            )

        # Step 4: status check — must be archived
        if workspace.status != WorkspaceStatus.archived:
            logger.warning(
                "restore_workspace forbidden_transition: workspace_id=%s status=%s",
                workspace_id,
                workspace.status.value,
            )
            emit_workspace_status_change_failure("forbidden_transition")
            raise ForbiddenTransitionError(
                f"Workspace {workspace_id} is not archived (current status="
                f"{workspace.status.value}). Only archived workspaces can be restored."
            )

        # Step 5: check Tenant status (non-locking read inside transaction)
        tenant = self.tenant_repo.find_tenant_by_id(db, tenant_id)
        if not tenant:
            emit_workspace_status_change_failure("internal_error")
            raise TenantNotFoundError(f"Tenant {tenant_id} not found")

        if tenant["status"] != "active":
            logger.warning(
                "restore_workspace tenant_not_active: tenant_id=%s status=%s",
                tenant_id,
                tenant["status"],
            )
            emit_workspace_status_change_failure("tenant_not_active")
            raise TenantNotActiveError(
                f"Tenant {tenant_id} is not active (status={tenant['status']}). "
                "Cannot restore workspace."
            )

        # Step 8 prep: store prior status_reason for audit
        prior_status_reason = workspace.status_reason

        # Step 7: apply mutation — clear status_reason to NULL (never "")
        now = datetime.now(UTC)
        workspace.status = WorkspaceStatus.active
        workspace.status_reason = None
        workspace.updated_at = now
        workspace.updated_by = actor_id
        workspace.version += 1

        # Persist
        self.workspace_repo.update_workspace(db, workspace)

        logger.info(
            "workspace restored: workspace_id=%s version=%s",
            workspace.workspace_id,
            workspace.version,
        )

        # Step 8: write workspace_restored audit entry via F052 AuditService
        previous_data = {"status": "archived", "status_reason": prior_status_reason}
        new_data = {"status": "active", "status_reason": None}

        audit_entry = AuditEntry(
            tenant_id=tenant_id,
            action_type="workspace_restored",
            target_entity_type="workspace",
            target_entity_id=workspace_id,
            after_state=new_data,
            actor_type="user",
            actor_role=actor_role,
            workspace_id=workspace_id,
            actor_id=actor_id,
            before_state=previous_data,
            request_id=request_id,
            source_ip=source_ip,
        )
        self.audit_service.write(db, audit_entry)

        logger.info(
            "audit log written: workspace_id=%s action_type=workspace_restored",
            workspace_id,
        )

        # Step 9: commit handled by caller

        # Caller (endpoint) emits workspace_status_change_success after commit.

        logger.info(
            "restore_workspace completed: workspace_id=%s tenant_id=%s",
            workspace_id,
            tenant_id,
        )

        return workspace

    # -----------------------------------------------------------------------
    # list_workspaces — Flow E (TDD §4.6)
    # -----------------------------------------------------------------------

    def list_workspaces(
        self,
        db: Session,
        tenant_id: UUID | None,
        *,
        include_archived: bool = False,
        q: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 25,
        restrict_to_user_id: UUID | None = None,
    ) -> tuple[list[Workspace], int]:
        """
        Return a paginated, filtered, sorted list of workspaces for *tenant_id*.

        Delegates directly to the repository.  All parameter validation
        (sort_by allowlist, range checks) is performed at the controller
        layer before this method is called.

        Parameters
        ----------
        tenant_id:
            Scope results to this tenant (always from JWT for regular users).
            ``None`` for platform operators without a tenant claim — results
            span all tenants.
        include_archived:
            When ``True``, archived workspaces are included in results.
        q:
            Full-text search against ``workspace_name`` and ``workspace_slug``.
            Metacharacters are escaped.  Whitespace-only *q* is treated as
            absent by the repository.
        sort_by:
            Column to sort by; must be ``"created_at"`` or ``"updated_at"``.
        sort_dir:
            Sort direction; must be ``"asc"`` or ``"desc"``.
        page:
            1-based page number.
        page_size:
            Number of results per page (1–100 inclusive).

        Returns
        -------
        (workspaces, total_count)
        """
        emit_workspace_list_request_count()

        logger.info(
            "list_workspaces: tenant_id=%s include_archived=%s q=%r "
            "sort_by=%s sort_dir=%s page=%s page_size=%s",
            tenant_id,
            include_archived,
            q,
            sort_by,
            sort_dir,
            page,
            page_size,
        )

        return self.workspace_repo.list_workspaces(
            db=db,
            tenant_id=tenant_id,
            include_archived=include_archived,
            q=q,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
            restrict_to_user_id=restrict_to_user_id,
        )

    # -----------------------------------------------------------------------
    # get_workspace_detail — Flow F (TDD §4.7)
    # -----------------------------------------------------------------------

    def get_workspace_detail(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID | None,
    ) -> tuple[Workspace, int | None, int | None, list[dict]]:
        """
        Return full workspace detail with aggregate count fields.

        Fetches the workspace row (non-locking read), then issues two secondary
        count queries against the dataset registry and RBAC member registry.
        Count query failures are caught and converted to ``None`` values with a
        ``warnings`` entry per TDD §11.3.

        The detail endpoint MUST NOT fail when a count registry is down.

        Parameters
        ----------
        workspace_id:
            Target workspace UUID.
        tenant_id:
            Session tenant; enforces cross-tenant isolation (workspace belonging
            to a different tenant returns zero rows → 404).

        Returns
        -------
        (workspace, dataset_count, member_count, warnings)
            ``dataset_count`` and/or ``member_count`` are ``None`` when the
            respective registry is unavailable.  ``warnings`` is an empty list
            when all counts were retrieved successfully.

        Raises
        ------
        WorkspaceNotFoundError → HTTP 404
        """
        emit_workspace_detail_request_count()

        logger.info(
            "get_workspace_detail: workspace_id=%s tenant_id=%s",
            workspace_id,
            tenant_id,
        )

        # Non-locking read (no FOR UPDATE on read paths)
        workspace = self.workspace_repo.find_by_id(
            db=db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            for_update=False,
        )

        warnings: list[dict] = []
        dataset_count: int | None = None
        member_count: int | None = None

        # Dataset count — fall back to None on any error (TDD §11.3)
        try:
            dataset_count = self.dataset_registry.count_for_workspace(workspace_id)
        except Exception as exc:
            logger.warning(
                "dataset_count unavailable: workspace_id=%s err=%s",
                workspace_id,
                exc,
            )
            emit_workspace_detail_count_query_failure("dataset_count")
            warnings.append({"field": "dataset_count", "reason": "registry_unavailable"})

        # Member count — fall back to None on any error (TDD §11.3)
        try:
            member_count = self.member_registry.count_members_for_workspace(workspace_id)
        except Exception as exc:
            logger.warning(
                "member_count unavailable: workspace_id=%s err=%s",
                workspace_id,
                exc,
            )
            emit_workspace_detail_count_query_failure("member_count")
            warnings.append({"field": "member_count", "reason": "registry_unavailable"})

        logger.info(
            "get_workspace_detail completed: workspace_id=%s dataset_count=%s "
            "member_count=%s warnings=%s",
            workspace_id,
            dataset_count,
            member_count,
            len(warnings),
        )

        return workspace, dataset_count, member_count, warnings

    def list_audit_logs(
        self,
        db: Session,
        workspace_id: UUID,
        tenant_id: UUID | None,
        *,
        action_type: str | None = None,
        actor_id: UUID | None = None,
        from_date=None,
        to_date=None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list, int]:
        """
        Return a paginated list of audit log entries for a workspace.

        For Workspace Administrator callers, ``tenant_id`` should equal the
        actor's JWT tenant — the repository will add ``AND tenant_id = :tenant_id``
        for cross-tenant isolation, returning 0 rows (→ 404 at call site via
        the preceding workspace existence check) for cross-tenant access.

        For Platform Operator callers, pass ``tenant_id=None``; the workspace
        existence check uses ``find_by_id_any_tenant`` and the audit log query
        omits the tenant filter.

        Parameters
        ----------
        workspace_id:
            Target workspace UUID.
        tenant_id:
            Actor's JWT tenant UUID (WA callers); ``None`` for Platform Operators.
        action_type / actor_id / from_date / to_date:
            Optional filters; validated before this call by the controller.
        page / page_size:
            Pagination; validated by the controller.

        Returns
        -------
        (entries, total_count)

        Raises
        ------
        WorkspaceNotFoundError → HTTP 404
        """
        logger.info(
            "list_audit_logs: workspace_id=%s tenant_id=%s action_type=%s "
            "actor_id=%s page=%s page_size=%s",
            workspace_id,
            tenant_id,
            action_type,
            actor_id,
            page,
            page_size,
        )

        # Verify workspace exists (and enforce tenant isolation for WA callers).
        # find_by_id raises WorkspaceNotFoundError → HTTP 404 when not found or
        # cross-tenant.  find_by_id_any_tenant is used for Platform Operators.
        if tenant_id is not None:
            self.workspace_repo.find_by_id(
                db=db,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
                for_update=False,
            )
        else:
            self.workspace_repo.find_by_id_any_tenant(db=db, workspace_id=workspace_id)

        entries, total = self.audit_log_repo.list_audit_logs(
            db=db,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            action_type=action_type,
            actor_id=actor_id,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )

        logger.info(
            "list_audit_logs completed: workspace_id=%s total=%s returned=%s",
            workspace_id,
            total,
            len(entries),
        )

        return entries, total
