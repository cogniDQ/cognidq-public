"""
Tenant Provisioning — Service Layer
=====================================

Orchestrates the full tenant provisioning workflow in a single atomic
transaction with step-level logging and rollback on failure.

Provisioning Steps:
    1. Validate uniqueness (tenant name, slug, admin email)
    2. Create tenant record (status=active, provisioning_status=in_progress)
    3. Create default workspace
    4. Create admin user account (status=pending)
    5. Create password reset token (invitation flow)
    6. Grant workspace_administrator role to admin
    7. Write audit log entries
    8. Update provisioning_status to completed

Transaction safety:
    - All 8 steps execute within a single DB transaction
    - On any failure, the entire transaction is rolled back
    - Provisioning step logs are written for auditability
    - If rollback succeeds, provisioning_status is never persisted as completed
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import TenantAPIError
from app.services.provisioning import (
    ProvisionExistingTenantCommand,
    ProvisioningStepLog,
    ProvisionTenantCommand,
    ProvisionTenantResult,
)
from app.services.provisioning.repository import ProvisioningRepository

logger = logging.getLogger(__name__)

# Password reset token validity for invitation
_INVITATION_TOKEN_EXPIRY_HOURS = 72


def _hash_password(password: str) -> str:
    """Hash a password using SHA-256 + bcrypt (matching User.set_password)."""
    sha_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(sha_hash.encode("utf-8"), salt).decode("utf-8")


def _generate_secure_token() -> str:
    """Generate a cryptographically secure URL-safe token."""
    return secrets.token_urlsafe(48)


class ProvisioningService:
    """Executes the full tenant provisioning workflow."""

    @staticmethod
    def provision_tenant(
        db: Session,
        command: ProvisionTenantCommand,
    ) -> ProvisionTenantResult:
        """Execute the complete provisioning flow atomically.

        Steps:
            1. Pre-checks (uniqueness)
            2. Create tenant
            3. Create default workspace
            4. Create admin user
            5. Create invitation token (password reset)
            6. Grant workspace_administrator role
            7. Write audit logs + provisioning logs
            8. Mark provisioning complete

        All steps are in a single transaction. Failure at any point
        triggers a full rollback.

        Returns:
            ProvisionTenantResult with all created resource IDs.

        Raises:
            TenantAPIError(422): duplicate name/slug/email, validation errors
            TenantAPIError(500): unexpected database errors
        """
        repo = ProvisioningRepository
        steps: list[ProvisioningStepLog] = []
        now = datetime.now(UTC)

        # Generate all IDs upfront
        tenant_id = uuid.uuid4()
        workspace_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        reset_token_id = uuid.uuid4()
        audit_log_id = uuid.uuid4()

        try:
            # ──────────────────────────────────────────────────────────
            # Step 1: Uniqueness pre-checks
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="uniqueness_checks",
                step_order=1,
                status="pending",
                started_at=now,
            )
            steps.append(step)

            if repo.check_tenant_name_exists(db, command.tenant_name):
                step.status = "failed"
                step.error_message = "Duplicate tenant name"
                step.completed_at = datetime.now(UTC)
                raise TenantAPIError(
                    422,
                    "duplicate_name",
                    "A tenant with this name already exists.",
                )

            if repo.check_tenant_slug_exists(db, command.tenant_slug):
                step.status = "failed"
                step.error_message = "Duplicate tenant slug"
                step.completed_at = datetime.now(UTC)
                raise TenantAPIError(
                    422,
                    "duplicate_slug",
                    "A tenant with this slug already exists.",
                )

            # Email reuse policy:
            #   • platform_admin actor: an existing user may be reused as the
            #     tenant admin for the new tenant. We grant them the workspace
            #     admin role on the default workspace below and skip the
            #     create-user / password-reset steps. Their existing
            #     credentials remain valid.
            #   • All other actors: an existing email is rejected as before.
            existing_user_row = repo.find_user_by_email(db, command.admin_email)
            reuse_existing_user: bool = False
            if existing_user_row is not None:
                if command.actor_role == "platform_admin":
                    reuse_existing_user = True
                else:
                    step.status = "failed"
                    step.error_message = "Email already exists"
                    step.completed_at = datetime.now(UTC)
                    raise TenantAPIError(
                        422,
                        "duplicate_email",
                        "A user with this email address already exists.",
                        fields=[{"field": "admin_email", "reason": "Email already registered"}],
                    )

            step.status = "success"
            step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 2: Create tenant
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="create_tenant",
                step_order=2,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            tenant_row = repo.insert_tenant(
                db,
                {
                    "tenant_id": str(tenant_id),
                    "tenant_name": command.tenant_name,
                    "tenant_slug": command.tenant_slug,
                    "status": "active",
                    "status_reason": None,
                    "region": command.region,
                    "plan": command.plan,
                    "service_start_date": command.service_start_date,
                    "tenant_notes": command.tenant_notes,
                    "provisioning_status": "in_progress",
                    "created_by": str(command.actor_id),
                    "updated_by": str(command.actor_id),
                },
            )

            step.status = "success"
            step.step_data = {"tenant_id": str(tenant_id)}
            step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 3: Create default workspace
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="create_default_workspace",
                step_order=3,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            ws_now = datetime.now(UTC)
            repo.insert_workspace(
                db,
                {
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(tenant_id),
                    "workspace_name": command.workspace_name,
                    "workspace_slug": command.workspace_slug,
                    "description": f"Default workspace for {command.tenant_name}",
                    "default_timezone": "UTC",
                    "status": "active",
                    "status_reason": None,
                    "created_at": ws_now,
                    "updated_at": ws_now,
                    "created_by": str(command.actor_id),
                    "updated_by": str(command.actor_id),
                    "version": 0,
                },
            )

            step.status = "success"
            step.step_data = {"workspace_id": str(workspace_id)}
            step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 4: Create admin user (or reuse existing)
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="create_admin_user",
                step_order=4,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            if reuse_existing_user and existing_user_row is not None:
                # Reuse the existing user as the tenant admin. Don't touch
                # their credentials or platform_role; just record the link.
                admin_user_id = uuid.UUID(existing_user_row.user_id)
                step.status = "success"
                step.step_data = {
                    "user_id": str(admin_user_id),
                    "email": command.admin_email.lower().strip(),
                    "reused_existing_user": True,
                }
                step.completed_at = datetime.now(UTC)
            else:
                # Generate a secure temporary password (user will set their
                # own via the password reset / invitation token)
                temp_password = secrets.token_urlsafe(32)
                password_hash = _hash_password(temp_password)

                repo.insert_user(
                    db,
                    {
                        "user_id": str(admin_user_id),
                        "email": command.admin_email.lower().strip(),
                        "password_hash": password_hash,
                        "full_name": command.admin_full_name,
                        "email_verified": False,
                        # Stored as the SQLAlchemy enum NAME (uppercase) so that
                        # the User ORM model can read the row back without
                        # "value is not among the defined enum values" errors.
                        "status": "PENDING",
                        # Grant tenant_admin so the new admin can immediately
                        # access tenant member management / workspace creation.
                        "platform_role": "tenant_admin",
                        "tenant_id": str(tenant_id),
                    },
                )

                step.status = "success"
                step.step_data = {
                    "user_id": str(admin_user_id),
                    "email": command.admin_email.lower().strip(),
                }
                step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 5: Create invitation token (skipped for reused users)
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="create_invitation_token",
                step_order=5,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            invitation_token: str | None = None
            if reuse_existing_user:
                step.status = "skipped"
                step.step_data = {"reason": "existing_user"}
                step.completed_at = datetime.now(UTC)
            else:
                invitation_token = _generate_secure_token()
                expires_at = datetime.now(UTC) + timedelta(hours=_INVITATION_TOKEN_EXPIRY_HOURS)

                repo.insert_password_reset(
                    db,
                    {
                        "reset_id": str(reset_token_id),
                        "user_id": str(admin_user_id),
                        "token": invitation_token,
                        "expires_at": expires_at,
                    },
                )

                step.status = "success"
                step.step_data = {
                    "reset_token_id": str(reset_token_id),
                    "expires_at": expires_at.isoformat(),
                }
                step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 6: Grant workspace_administrator role
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="grant_workspace_admin_role",
                step_order=6,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            repo.grant_workspace_admin(
                db,
                workspace_id=str(workspace_id),
                actor_id=str(admin_user_id),
            )

            step.status = "success"
            step.step_data = {
                "workspace_id": str(workspace_id),
                "user_id": str(admin_user_id),
                "role": "workspace_administrator",
            }
            step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 7: Write audit logs
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="write_audit_logs",
                step_order=7,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            audit_payload = {
                "tenant_id": str(tenant_id),
                "tenant_name": command.tenant_name,
                "tenant_slug": command.tenant_slug,
                "region": command.region,
                "plan": command.plan,
                "workspace_id": str(workspace_id),
                "workspace_name": command.workspace_name,
                "admin_user_id": str(admin_user_id),
                "admin_email": command.admin_email.lower().strip(),
                "provisioned_by": str(command.actor_id),
            }

            repo.insert_tenant_audit_log(
                db,
                {
                    "log_id": str(audit_log_id),
                    "tenant_id": str(tenant_id),
                    "event_type": "tenant_provisioned",
                    "actor_id": str(command.actor_id),
                    "actor_role": command.actor_role,
                    "new_data": json.dumps(audit_payload),
                    "reason": "Automated tenant provisioning",
                },
            )

            step.status = "success"
            step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Step 8: Update provisioning status to completed
            # ──────────────────────────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="finalize_provisioning",
                step_order=8,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            repo.update_provisioning_status(db, str(tenant_id), "completed")

            step.status = "success"
            step.completed_at = datetime.now(UTC)

            # ──────────────────────────────────────────────────────────
            # Write provisioning step logs (all steps recorded)
            # ──────────────────────────────────────────────────────────
            for s in steps:
                repo.insert_provisioning_log(
                    db,
                    {
                        "log_id": str(uuid.uuid4()),
                        "tenant_id": str(tenant_id),
                        "step_name": s.step_name,
                        "step_order": s.step_order,
                        "status": s.status,
                        "started_at": s.started_at,
                        "completed_at": s.completed_at,
                        "error_message": s.error_message,
                        "step_data": json.dumps(s.step_data) if s.step_data else None,
                        "actor_id": str(command.actor_id),
                        "actor_role": command.actor_role,
                    },
                )

            # ──────────────────────────────────────────────────────────
            # Commit — atomic for all inserts
            # ──────────────────────────────────────────────────────────
            db.commit()

            logger.info(
                "Tenant provisioning completed: tenant_id=%s workspace_id=%s admin_user_id=%s",
                tenant_id,
                workspace_id,
                admin_user_id,
            )

            return ProvisionTenantResult(
                tenant_id=str(tenant_id),
                tenant_name=command.tenant_name,
                tenant_slug=command.tenant_slug,
                status="active",
                region=command.region,
                plan=command.plan,
                workspace_id=str(workspace_id),
                workspace_name=command.workspace_name,
                workspace_slug=command.workspace_slug,
                admin_user_id=str(admin_user_id),
                admin_email=command.admin_email.lower().strip(),
                admin_full_name=command.admin_full_name,
                provisioning_status="completed",
                steps=steps,
                created_at=tenant_row.created_at if tenant_row else None,
                password_reset_token=invitation_token,
            )

        except TenantAPIError:
            db.rollback()
            raise

        except IntegrityError as exc:
            db.rollback()
            logger.error(
                "IntegrityError during provisioning: %s",
                exc,
                exc_info=True,
            )
            # Map constraint violations to user-friendly errors
            orig = getattr(exc, "orig", None)
            pgcode = getattr(orig, "pgcode", "") if orig else ""
            constraint = getattr(getattr(orig, "diag", None), "constraint_name", "") or ""

            if pgcode == "23505":
                if "name" in constraint:
                    raise TenantAPIError(
                        422,
                        "duplicate_name",
                        "A tenant with this name already exists.",
                    ) from exc
                if "slug" in constraint:
                    raise TenantAPIError(
                        422,
                        "duplicate_slug",
                        "A tenant with this slug already exists.",
                    ) from exc
                if "email" in constraint:
                    raise TenantAPIError(
                        422,
                        "duplicate_email",
                        "A user with this email address already exists.",
                        fields=[{"field": "admin_email", "reason": "Email already registered"}],
                    ) from exc

            raise TenantAPIError(
                500,
                "provisioning_failed",
                "An unexpected error occurred during tenant provisioning.",
            ) from exc

        except Exception as exc:
            db.rollback()
            logger.exception("Unexpected error during tenant provisioning")
            raise TenantAPIError(
                500,
                "provisioning_failed",
                "An unexpected error occurred during tenant provisioning.",
            ) from exc

    @staticmethod
    def get_provisioning_status(
        db: Session,
        tenant_id: str,
    ) -> list[dict]:
        """Return provisioning step logs for a tenant.

        Returns:
            List of step log dicts ordered by step_order.
        """
        return ProvisioningRepository.list_provisioning_logs(db, tenant_id)

    # ------------------------------------------------------------------
    # Provision an *existing* tenant (BUG-PROVISION-EXISTING)
    # ------------------------------------------------------------------

    @staticmethod
    def provision_existing_tenant(
        db: Session,
        command: ProvisionExistingTenantCommand,
    ) -> ProvisionTenantResult:
        """Provision the default workspace + tenant admin against an
        already-created tenant row.

        Skips tenant creation (Step 2) and uniqueness checks for tenant
        name/slug. Reuses the same step semantics as :meth:`provision_tenant`
        for steps 3-8 so the audit/log story is identical.

        Raises:
            TenantAPIError(404): tenant does not exist
            TenantAPIError(409): tenant already provisioned
            TenantAPIError(422): duplicate admin email or slug collision
        """
        from app.services.provisioning import ProvisionExistingTenantCommand  # noqa: F401

        repo = ProvisioningRepository
        steps: list[ProvisioningStepLog] = []
        now = datetime.now(UTC)

        # ─── Resolve the existing tenant ──────────────────────────────
        tenant_row = repo.find_tenant_by_id(db, str(command.tenant_id))
        if tenant_row is None:
            raise TenantAPIError(404, "tenant_not_found", "Tenant not found.")
        if (tenant_row.provisioning_status or "").lower() == "completed":
            raise TenantAPIError(
                409,
                "tenant_already_provisioned",
                "This tenant has already been provisioned.",
            )
        if (tenant_row.status or "").lower() == "archived":
            raise TenantAPIError(
                409,
                "tenant_archived",
                "Cannot provision an archived tenant.",
            )

        tenant_name = tenant_row.tenant_name
        tenant_slug = tenant_row.tenant_slug
        region = tenant_row.region
        plan = tenant_row.plan

        workspace_id = uuid.uuid4()
        admin_user_id = uuid.uuid4()
        reset_token_id = uuid.uuid4()
        audit_log_id = uuid.uuid4()

        try:
            # ─── Step 1: email uniqueness pre-check ───────────────────
            step = ProvisioningStepLog(
                step_name="uniqueness_checks",
                step_order=1,
                status="pending",
                started_at=now,
            )
            steps.append(step)

            # Email reuse policy (see provision_tenant for rationale).
            existing_user_row = repo.find_user_by_email(db, command.admin_email)
            reuse_existing_user: bool = False
            if existing_user_row is not None:
                if command.actor_role == "platform_admin":
                    reuse_existing_user = True
                else:
                    step.status = "failed"
                    step.error_message = "Email already exists"
                    step.completed_at = datetime.now(UTC)
                    raise TenantAPIError(
                        422,
                        "duplicate_email",
                        "A user with this email address already exists.",
                        fields=[{"field": "admin_email", "reason": "Email already registered"}],
                    )

            step.status = "success"
            step.completed_at = datetime.now(UTC)

            # ─── Step 2: skipped (tenant already exists) ──────────────
            steps.append(
                ProvisioningStepLog(
                    step_name="create_tenant",
                    step_order=2,
                    status="skipped",
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    step_data={"tenant_id": str(command.tenant_id), "skipped": True},
                )
            )

            # Mark tenant as in-progress so the dashboard reflects state.
            repo.update_provisioning_status(db, str(command.tenant_id), "in_progress")

            # ─── Step 3: create default workspace ─────────────────────
            step = ProvisioningStepLog(
                step_name="create_default_workspace",
                step_order=3,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            ws_now = datetime.now(UTC)
            repo.insert_workspace(
                db,
                {
                    "workspace_id": str(workspace_id),
                    "tenant_id": str(command.tenant_id),
                    "workspace_name": command.workspace_name,
                    "workspace_slug": command.workspace_slug,
                    "description": f"Default workspace for {tenant_name}",
                    "default_timezone": "UTC",
                    "status": "active",
                    "status_reason": None,
                    "created_at": ws_now,
                    "updated_at": ws_now,
                    "created_by": str(command.actor_id),
                    "updated_by": str(command.actor_id),
                    "version": 0,
                },
            )

            step.status = "success"
            step.step_data = {"workspace_id": str(workspace_id)}
            step.completed_at = datetime.now(UTC)

            # ─── Step 4: create admin user (or reuse existing) ────────
            step = ProvisioningStepLog(
                step_name="create_admin_user",
                step_order=4,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            if reuse_existing_user and existing_user_row is not None:
                admin_user_id = uuid.UUID(existing_user_row.user_id)
                step.status = "success"
                step.step_data = {
                    "user_id": str(admin_user_id),
                    "email": command.admin_email.lower().strip(),
                    "reused_existing_user": True,
                }
                step.completed_at = datetime.now(UTC)
            else:
                temp_password = secrets.token_urlsafe(32)
                password_hash = _hash_password(temp_password)

                repo.insert_user(
                    db,
                    {
                        "user_id": str(admin_user_id),
                        "email": command.admin_email.lower().strip(),
                        "password_hash": password_hash,
                        "full_name": command.admin_full_name,
                        "email_verified": False,
                        "status": "PENDING",
                        "platform_role": "tenant_admin",
                        "tenant_id": str(command.tenant_id),
                    },
                )

                step.status = "success"
                step.step_data = {
                    "user_id": str(admin_user_id),
                    "email": command.admin_email.lower().strip(),
                }
                step.completed_at = datetime.now(UTC)

            # ─── Step 5: invitation token (skipped for reused users) ──
            step = ProvisioningStepLog(
                step_name="create_invitation_token",
                step_order=5,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            invitation_token: str | None = None
            if reuse_existing_user:
                step.status = "skipped"
                step.step_data = {"reason": "existing_user"}
                step.completed_at = datetime.now(UTC)
            else:
                invitation_token = _generate_secure_token()
                expires_at = datetime.now(UTC) + timedelta(hours=_INVITATION_TOKEN_EXPIRY_HOURS)

                repo.insert_password_reset(
                    db,
                    {
                        "reset_id": str(reset_token_id),
                        "user_id": str(admin_user_id),
                        "token": invitation_token,
                        "expires_at": expires_at,
                    },
                )

                step.status = "success"
                step.step_data = {
                    "reset_token_id": str(reset_token_id),
                    "expires_at": expires_at.isoformat(),
                }
                step.completed_at = datetime.now(UTC)

            # ─── Step 6: grant workspace_administrator role ───────────
            step = ProvisioningStepLog(
                step_name="grant_workspace_admin_role",
                step_order=6,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            repo.grant_workspace_admin(
                db,
                workspace_id=str(workspace_id),
                actor_id=str(admin_user_id),
            )

            step.status = "success"
            step.step_data = {
                "workspace_id": str(workspace_id),
                "user_id": str(admin_user_id),
                "role": "workspace_administrator",
            }
            step.completed_at = datetime.now(UTC)

            # ─── Step 7: audit log ────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="write_audit_logs",
                step_order=7,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            audit_payload = {
                "tenant_id": str(command.tenant_id),
                "tenant_name": tenant_name,
                "tenant_slug": tenant_slug,
                "region": region,
                "plan": plan,
                "workspace_id": str(workspace_id),
                "workspace_name": command.workspace_name,
                "admin_user_id": str(admin_user_id),
                "admin_email": command.admin_email.lower().strip(),
                "provisioned_by": str(command.actor_id),
                "mode": "existing_tenant",
            }

            repo.insert_tenant_audit_log(
                db,
                {
                    "log_id": str(audit_log_id),
                    "tenant_id": str(command.tenant_id),
                    "event_type": "tenant_provisioned",
                    "actor_id": str(command.actor_id),
                    "actor_role": command.actor_role,
                    "new_data": json.dumps(audit_payload),
                    "reason": "Manual provisioning of existing tenant",
                },
            )

            step.status = "success"
            step.completed_at = datetime.now(UTC)

            # ─── Step 8: finalize ─────────────────────────────────────
            step = ProvisioningStepLog(
                step_name="finalize_provisioning",
                step_order=8,
                started_at=datetime.now(UTC),
            )
            steps.append(step)

            repo.update_provisioning_status(db, str(command.tenant_id), "completed")

            step.status = "success"
            step.completed_at = datetime.now(UTC)

            # Persist provisioning step logs
            for s in steps:
                repo.insert_provisioning_log(
                    db,
                    {
                        "log_id": str(uuid.uuid4()),
                        "tenant_id": str(command.tenant_id),
                        "step_name": s.step_name,
                        "step_order": s.step_order,
                        "status": s.status,
                        "started_at": s.started_at,
                        "completed_at": s.completed_at,
                        "error_message": s.error_message,
                        "step_data": json.dumps(s.step_data) if s.step_data else None,
                        "actor_id": str(command.actor_id),
                        "actor_role": command.actor_role,
                    },
                )

            db.commit()

            logger.info(
                "Existing-tenant provisioning completed: tenant_id=%s workspace_id=%s admin_user_id=%s",
                command.tenant_id,
                workspace_id,
                admin_user_id,
            )

            return ProvisionTenantResult(
                tenant_id=str(command.tenant_id),
                tenant_name=tenant_name,
                tenant_slug=tenant_slug,
                status=tenant_row.status,
                region=region,
                plan=plan,
                workspace_id=str(workspace_id),
                workspace_name=command.workspace_name,
                workspace_slug=command.workspace_slug,
                admin_user_id=str(admin_user_id),
                admin_email=command.admin_email.lower().strip(),
                admin_full_name=command.admin_full_name,
                provisioning_status="completed",
                steps=steps,
                created_at=tenant_row.created_at,
                password_reset_token=invitation_token,
            )

        except TenantAPIError:
            db.rollback()
            raise

        except IntegrityError as exc:
            db.rollback()
            logger.error(
                "IntegrityError during existing-tenant provisioning: %s",
                exc,
                exc_info=True,
            )
            orig = getattr(exc, "orig", None)
            pgcode = getattr(orig, "pgcode", "") if orig else ""
            constraint = getattr(getattr(orig, "diag", None), "constraint_name", "") or ""
            if pgcode == "23505":
                if "slug" in constraint and "workspace" in constraint:
                    raise TenantAPIError(
                        422,
                        "duplicate_workspace_slug",
                        "A workspace with this slug already exists.",
                        fields=[{"field": "workspace_slug", "reason": "Slug already taken"}],
                    ) from exc
                if "email" in constraint:
                    raise TenantAPIError(
                        422,
                        "duplicate_email",
                        "A user with this email address already exists.",
                        fields=[{"field": "admin_email", "reason": "Email already registered"}],
                    ) from exc
            raise TenantAPIError(
                500,
                "provisioning_failed",
                "An unexpected error occurred during tenant provisioning.",
            ) from exc

        except Exception as exc:
            db.rollback()
            logger.exception("Unexpected error during existing-tenant provisioning")
            raise TenantAPIError(
                500,
                "provisioning_failed",
                "An unexpected error occurred during tenant provisioning.",
            ) from exc
