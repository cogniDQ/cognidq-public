"""
F134 P07 — Sandbox Provisioning Service

Core provisioning logic for creating a sandbox tenant/workspace/user and
seeding demo content. Designed to be called from the Celery task; also
directly testable without Celery.

Transaction boundary (per FR-022):
  INSIDE  transaction: tenant + workspace + user + role + sandbox_environment
  OUTSIDE transaction: template seeder (idempotent, can be retried)
  AFTER:  provisioning_job status update + invitation email
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.demo.template_seeder_service import TemplateSeederService
from app.services.sandbox.access_profile_repository import AccessProfileRepository
from app.services.sandbox.demo_request_repository import DemoRequestRepository
from app.services.sandbox.provisioning_job_repository import ProvisioningJobRepository
from app.services.sandbox.sandbox_environment_repository import SandboxEnvironmentRepository

logger = logging.getLogger(__name__)

# Sandbox tenant defaults
_SANDBOX_PLAN = "starter"
_SANDBOX_REGION = "us-east"
_SANDBOX_STATUS = "active"


def emit_sandbox_approved_email(
    request_row: dict,
    invitation_token: str,
) -> None:  # noqa: ARG001
    """
    Fire-and-forget approved email stub.
    Will be wired to real email dispatcher in a later packet.
    """
    logger.info(
        "STUB: sandbox_approved email would be sent to %s",
        request_row.get("work_email"),
    )


class ProvisioningError(RuntimeError):
    """Raised when provisioning fails unrecoverably after retries."""


class SandboxProvisioningService:
    """
    Orchestrates full sandbox provisioning for a demo_request_id.

    Parameters
    ----------
    db :
        SQLAlchemy session — must be a real session (not autocommit).
    invitation_secret :
        HMAC secret used to sign invitation tokens. Read from
        ``settings.JWT_SECRET_KEY`` in the Celery task caller.
    """

    def __init__(
        self,
        db: Session,
        *,
        invitation_secret: str,
        request_repo: DemoRequestRepository | None = None,
        job_repo: ProvisioningJobRepository | None = None,
        env_repo: SandboxEnvironmentRepository | None = None,
        profile_repo: AccessProfileRepository | None = None,
        seeder_service: TemplateSeederService | None = None,
    ) -> None:
        self._db = db
        self._invitation_secret = invitation_secret
        self._request_repo = request_repo or DemoRequestRepository(db)
        self._job_repo = job_repo or ProvisioningJobRepository(db)
        self._env_repo = env_repo or SandboxEnvironmentRepository(db)
        self._profile_repo = profile_repo or AccessProfileRepository(db)
        self._seeder_service = seeder_service or TemplateSeederService(db)

    # ── Public API ────────────────────────────────────────────────────────

    def provision(self, *, job_id: UUID) -> dict:
        """
        Execute full provisioning for the given ``job_id``.

        Returns the sandbox_environment row on success.
        Raises ``ProvisioningError`` on unrecoverable failure.

        Idempotency: if a sandbox_environment already exists for the
        demo_request_id, returns the existing row immediately.
        """
        job = self._job_repo.find_by_id(job_id)
        if job is None:
            raise ProvisioningError(f"Provisioning job {job_id} not found.")

        request_id = UUID(job["demo_request_id"])
        request_row = self._request_repo.find_by_id(request_id)
        if request_row is None:
            raise ProvisioningError(f"Demo request {request_id} not found.")

        # Idempotency: check for existing sandbox environment
        existing_env = self._find_existing_env(request_id)
        if existing_env:
            logger.info("provision: sandbox already exists for request %s — skipping.", request_id)
            return existing_env

        template_id: str = request_row.get("template_id") or "general_dq"
        access_profile_code: str = request_row.get("access_profile_code") or "mvp_default"
        duration_days: int = request_row.get("duration_days") or 7

        profile_row = self._profile_repo.find_by_code(access_profile_code)
        if profile_row is None:
            raise ProvisioningError(f"Access profile '{access_profile_code}' not found.")
        profile_id = UUID(str(profile_row["id"]))

        # Mark job as started
        self._job_repo.update(
            job_id=job_id,
            status="running",
            set_started_at=True,
            increment_attempt=1,
        )

        try:
            sandbox_env = self._run_provisioning_transaction(
                request_row=request_row,
                profile_id=profile_id,
                template_id=template_id,
                duration_days=duration_days,
                job_id=job_id,
            )
        except Exception as exc:
            logger.exception("provision: transaction failed for request %s", request_id)
            self._job_repo.update(
                job_id=job_id,
                status="failed",
                set_finished_at=True,
                last_error=str(exc),
            )
            raise ProvisioningError(str(exc)) from exc

        # Outside transaction: seed template content
        try:
            self._seeder_service.seed(
                template_id,
                UUID(sandbox_env["tenant_id"]),
                UUID(sandbox_env["workspace_id"]),
            )
        except Exception as exc:
            logger.warning(
                "provision: seeder failed for sandbox %s — marking job failed: %s",
                sandbox_env["id"],
                exc,
            )
            self._job_repo.update(
                job_id=job_id,
                status="failed",
                set_finished_at=True,
                last_error=f"seeder: {exc}",
            )
            raise ProvisioningError(f"Template seeder failed: {exc}") from exc

        # Mark job succeeded
        self._job_repo.update(
            job_id=job_id,
            status="succeeded",
            set_finished_at=True,
        )

        # Mark sandbox as active
        self._env_repo.update_status(
            sandbox_id=UUID(sandbox_env["id"]),
            status="active",
            set_provisioned_at=True,
        )

        # Generate invitation token and emit email stub
        user_id = sandbox_env.get("user_id") or ""
        token = self._sign_invitation(user_id, request_row["work_email"])
        emit_sandbox_approved_email(request_row, token)

        sandbox_env["invitation_token"] = token
        return sandbox_env

    # ── Private: core transaction ─────────────────────────────────────────

    def _run_provisioning_transaction(
        self,
        *,
        request_row: dict,
        profile_id: UUID,
        template_id: str,
        duration_days: int,
        job_id: UUID,
    ) -> dict:
        """
        Creates tenant, workspace, user, role assignment, and sandbox_environment
        in a single atomic transaction. Returns sandbox_environment dict.
        """
        now = datetime.now(UTC)
        request_id = UUID(request_row["id"])
        work_email = request_row["work_email"]
        first_name = request_row["first_name"]
        last_name = request_row["last_name"]
        company = request_row["company_name"]

        tenant_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        slug = _make_slug(company, tenant_id)

        # 1. Create tenant (type='sandbox')
        self._db.execute(
            text("""
                INSERT INTO control.tenants (
                    tenant_id, tenant_name, tenant_slug,
                    status, region, plan,
                    created_by, updated_by, version, tenant_type
                ) VALUES (
                    :tenant_id, :tenant_name, :tenant_slug,
                    CAST(:status AS control.tenant_status_enum),
                    CAST(:region AS control.tenant_region_enum),
                    CAST(:plan AS control.tenant_plan_enum),
                    :created_by, :updated_by, 0, 'sandbox'
                )
            """),
            {
                "tenant_id": str(tenant_id),
                "tenant_name": f"{company} Sandbox",
                "tenant_slug": slug,
                "status": _SANDBOX_STATUS,
                "region": _SANDBOX_REGION,
                "plan": _SANDBOX_PLAN,
                "created_by": str(tenant_id),
                "updated_by": str(tenant_id),
            },
        )

        # 2. Create workspace
        self._db.execute(
            text("""
                INSERT INTO control.workspaces (
                    workspace_id, tenant_id, workspace_name,
                    workspace_name_lower, workspace_slug,
                    description, default_timezone, status, status_reason,
                    created_at, updated_at, created_by, updated_by, version
                ) VALUES (
                    :workspace_id, :tenant_id, :workspace_name,
                    LOWER(:workspace_name), :workspace_slug,
                    :description, 'UTC',
                    CAST('active' AS control.workspace_status_enum),
                    NULL, :now, :now,
                    :created_by, :created_by, 0
                )
            """),
            {
                "workspace_id": str(workspace_id),
                "tenant_id": str(tenant_id),
                "workspace_name": "Demo Workspace",
                "workspace_slug": f"demo-{str(workspace_id)[:8]}",
                "description": "Auto-provisioned demo workspace.",
                "now": now,
                "created_by": str(tenant_id),
            },
        )

        # 3. Create user (status='invited', no password)
        self._db.execute(
            text("""
                INSERT INTO users (
                    id, email, full_name, email_verified,
                    status, tenant_id, created_at, updated_at
                ) VALUES (
                    :user_id, :email, :full_name, FALSE,
                    'invited', :tenant_id, :now, :now
                )
            """),
            {
                "user_id": str(user_id),
                "email": work_email,
                "full_name": f"{first_name} {last_name}",
                "tenant_id": str(tenant_id),
                "now": now,
            },
        )

        # 4. Workspace role assignment (sandbox_admin)
        self._db.execute(
            text("""
                INSERT INTO control.workspace_role_assignments (
                    id, workspace_id, user_id, role_name, granted_at
                ) VALUES (
                    :id, :workspace_id, :user_id, 'sandbox_admin', :now
                )
            """),
            {
                "id": str(uuid4()),
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
                "now": now,
            },
        )

        # 5. Sandbox environment row
        expires_at = now + timedelta(days=duration_days)
        env_row = self._env_repo.create(
            demo_request_id=request_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            template_id=template_id,
            access_profile_id=profile_id,
            expires_at=expires_at,
        )
        env_row["user_id"] = str(user_id)

        # 6. Update provisioning job with sandbox_id
        self._job_repo.update(
            job_id=job_id,
            sandbox_id=UUID(env_row["id"]),
        )

        return env_row

    # ── Private: helpers ──────────────────────────────────────────────────

    def _find_existing_env(self, request_id: UUID) -> dict | None:
        row = self._db.execute(
            text("""
                SELECT id::text, demo_request_id::text, tenant_id::text,
                       workspace_id::text, status, expires_at
                FROM control.sandbox_environments
                WHERE demo_request_id = CAST(:rid AS UUID)
                  AND status NOT IN ('deleted', 'archived')
                LIMIT 1
            """),
            {"rid": str(request_id)},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _sign_invitation(self, user_id: str, email: str) -> str:
        from app.services.sandbox.invitation import generate_invitation_token

        return generate_invitation_token(
            user_id=user_id,
            email=email,
            secret=self._invitation_secret,
        )


def _make_slug(company: str, uid: UUID) -> str:
    """Create a unique, URL-safe slug from company name + UUID suffix."""
    base = re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-")[:30]
    suffix = str(uid)[:8]
    return f"{base}-{suffix}"
