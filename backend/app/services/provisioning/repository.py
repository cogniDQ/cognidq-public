"""
Tenant Provisioning — Repository Layer
========================================

All SQL operations specific to the provisioning workflow.
Reuses control.tenants, control.workspaces, and public.users tables.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL: tenant INSERT (same as tenant repo but with provisioning_status)
# ---------------------------------------------------------------------------

_INSERT_TENANT_SQL = text("""
    INSERT INTO control.tenants (
        tenant_id,
        tenant_name,
        tenant_slug,
        status,
        status_reason,
        region,
        plan,
        service_start_date,
        tenant_notes,
        provisioning_status,
        created_by,
        updated_by,
        version
    ) VALUES (
        CAST(:tenant_id AS UUID),
        :tenant_name,
        :tenant_slug,
        CAST(:status AS control.tenant_status_enum),
        :status_reason,
        CAST(:region AS control.tenant_region_enum),
        CAST(:plan   AS control.tenant_plan_enum),
        :service_start_date,
        :tenant_notes,
        CAST(:provisioning_status AS control.provisioning_status_enum),
        CAST(:created_by AS UUID),
        CAST(:updated_by AS UUID),
        0
    )
    RETURNING
        tenant_id::text,
        tenant_name,
        tenant_slug,
        status::text,
        status_reason,
        region::text,
        plan::text,
        service_start_date,
        tenant_notes,
        provisioning_status::text,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text
""")

# ---------------------------------------------------------------------------
# SQL: check tenant name/slug uniqueness
# ---------------------------------------------------------------------------

_CHECK_TENANT_NAME_SQL = text("""
    SELECT 1 FROM control.tenants
    WHERE tenant_name_lower = LOWER(TRIM(:name))
    LIMIT 1
""")

_CHECK_TENANT_SLUG_SQL = text("""
    SELECT 1 FROM control.tenants
    WHERE tenant_slug = :slug
    LIMIT 1
""")

# ---------------------------------------------------------------------------
# SQL: check user email uniqueness
# ---------------------------------------------------------------------------

_CHECK_EMAIL_SQL = text("""
    SELECT 1 FROM users
    WHERE LOWER(email) = LOWER(:email)
    LIMIT 1
""")

_FIND_USER_BY_EMAIL_SQL = text("""
    SELECT
        id::text          AS user_id,
        email,
        full_name,
        platform_role,
        tenant_id::text   AS tenant_id
    FROM users
    WHERE LOWER(email) = LOWER(:email)
    LIMIT 1
""")

# ---------------------------------------------------------------------------
# SQL: workspace INSERT
# ---------------------------------------------------------------------------

_INSERT_WORKSPACE_SQL = text("""
    INSERT INTO control.workspaces (
        workspace_id,
        tenant_id,
        workspace_name,
        workspace_slug,
        description,
        default_timezone,
        status,
        status_reason,
        created_at,
        updated_at,
        created_by,
        updated_by,
        version
    ) VALUES (
        CAST(:workspace_id  AS UUID),
        CAST(:tenant_id     AS UUID),
        :workspace_name,
        :workspace_slug,
        :description,
        :default_timezone,
        CAST(:status AS control.workspace_status_enum),
        :status_reason,
        :created_at,
        :updated_at,
        CAST(:created_by AS UUID),
        CAST(:updated_by AS UUID),
        :version
    )
    RETURNING
        workspace_id::text,
        tenant_id::text,
        workspace_name,
        workspace_slug,
        status::text,
        created_at,
        updated_at,
        created_by::text,
        updated_by::text
""")

# ---------------------------------------------------------------------------
# SQL: user INSERT
# ---------------------------------------------------------------------------

_INSERT_USER_SQL = text("""
    INSERT INTO users (
        id,
        email,
        password_hash,
        full_name,
        email_verified,
        status,
        platform_role,
        tenant_id,
        created_at,
        updated_at
    ) VALUES (
        CAST(:user_id AS UUID),
        :email,
        :password_hash,
        :full_name,
        :email_verified,
        :status,
        :platform_role,
        CAST(:tenant_id AS UUID),
        NOW(),
        NOW()
    )
    RETURNING
        id::text,
        email,
        full_name,
        status,
        tenant_id::text,
        created_at
""")

# ---------------------------------------------------------------------------
# SQL: password reset token INSERT
# ---------------------------------------------------------------------------

_INSERT_PASSWORD_RESET_SQL = text("""
    INSERT INTO password_resets (
        id,
        user_id,
        token,
        expires_at,
        used,
        created_at
    ) VALUES (
        CAST(:reset_id AS UUID),
        CAST(:user_id AS UUID),
        :token,
        :expires_at,
        FALSE,
        NOW()
    )
    RETURNING id::text, token, expires_at
""")

# ---------------------------------------------------------------------------
# SQL: provisioning log INSERT
# ---------------------------------------------------------------------------

_INSERT_PROVISIONING_LOG_SQL = text("""
    INSERT INTO control.tenant_provisioning_logs (
        log_id,
        tenant_id,
        step_name,
        step_order,
        status,
        started_at,
        completed_at,
        error_message,
        step_data,
        actor_id,
        actor_role
    ) VALUES (
        CAST(:log_id AS UUID),
        CAST(:tenant_id AS UUID),
        :step_name,
        :step_order,
        :status,
        :started_at,
        :completed_at,
        :error_message,
        CAST(:step_data AS JSONB),
        CAST(:actor_id AS UUID),
        :actor_role
    )
""")

# ---------------------------------------------------------------------------
# SQL: update tenant provisioning_status
# ---------------------------------------------------------------------------

_UPDATE_PROVISIONING_STATUS_SQL = text("""
    UPDATE control.tenants
    SET provisioning_status = CAST(:provisioning_status AS control.provisioning_status_enum),
        updated_at = NOW()
    WHERE tenant_id = CAST(:tenant_id AS UUID)
""")

# ---------------------------------------------------------------------------
# SQL: tenant audit log INSERT
# ---------------------------------------------------------------------------

_INSERT_TENANT_AUDIT_SQL = text("""
    INSERT INTO control.tenant_audit_logs (
        log_id,
        tenant_id,
        event_type,
        actor_id,
        actor_role,
        previous_data,
        new_data,
        occurred_at,
        reason
    ) VALUES (
        CAST(:log_id AS UUID),
        CAST(:tenant_id AS UUID),
        :event_type,
        CAST(:actor_id AS UUID),
        :actor_role,
        NULL,
        CAST(:new_data AS JSONB),
        NOW(),
        :reason
    )
""")

# ---------------------------------------------------------------------------
# SQL: RBAC role grant (workspace_administrator)
#
# The canonical table is control.workspace_role_assignments (see migration
# 012_f007_workspace_role_assignments.sql). Legacy code referenced a
# non-existent control.role_assignments — that caused BUG-001 to partially
# fail even after the provisioning_status column was added.
# ---------------------------------------------------------------------------

_GRANT_WORKSPACE_ADMIN_SQL = text("""
    INSERT INTO control.workspace_role_assignments (
        workspace_id, user_id, role_name, granted_by
    ) VALUES (
        CAST(:workspace_id AS UUID),
        CAST(:user_id      AS UUID),
        :role_name,
        CAST(:granted_by   AS UUID)
    )
    ON CONFLICT (workspace_id, user_id) DO NOTHING
""")

# ---------------------------------------------------------------------------
# SQL: list provisioning logs for a tenant
# ---------------------------------------------------------------------------

_LIST_PROVISIONING_LOGS_SQL = text("""
    SELECT
        log_id::text,
        tenant_id::text,
        step_name,
        step_order,
        status,
        started_at,
        completed_at,
        error_message,
        step_data,
        actor_id::text,
        actor_role,
        created_at
    FROM control.tenant_provisioning_logs
    WHERE tenant_id = CAST(:tenant_id AS UUID)
    ORDER BY step_order ASC
""")

# ---------------------------------------------------------------------------
# SQL: load existing tenant for re-provisioning
# ---------------------------------------------------------------------------

_FIND_TENANT_BY_ID_SQL = text("""
    SELECT
        tenant_id::text     AS tenant_id,
        tenant_name,
        tenant_slug,
        status::text        AS status,
        region::text        AS region,
        plan::text          AS plan,
        provisioning_status::text AS provisioning_status,
        created_at
    FROM control.tenants
    WHERE tenant_id = CAST(:tenant_id AS UUID)
    LIMIT 1
""")


# ---------------------------------------------------------------------------
# Repository class
# ---------------------------------------------------------------------------


class ProvisioningRepository:
    """All provisioning-related DB operations."""

    @staticmethod
    def check_tenant_name_exists(db: Session, name: str) -> bool:
        row = db.execute(_CHECK_TENANT_NAME_SQL, {"name": name}).fetchone()
        return row is not None

    @staticmethod
    def check_tenant_slug_exists(db: Session, slug: str) -> bool:
        row = db.execute(_CHECK_TENANT_SLUG_SQL, {"slug": slug}).fetchone()
        return row is not None

    @staticmethod
    def check_email_exists(db: Session, email: str) -> bool:
        row = db.execute(_CHECK_EMAIL_SQL, {"email": email}).fetchone()
        return row is not None

    @staticmethod
    def find_user_by_email(db: Session, email: str) -> Any | None:
        """Return the row for the user with this email, or None."""
        return db.execute(_FIND_USER_BY_EMAIL_SQL, {"email": email}).fetchone()

    @staticmethod
    def insert_tenant(db: Session, params: dict[str, Any]) -> Any:
        result = db.execute(_INSERT_TENANT_SQL, params)
        return result.fetchone()

    @staticmethod
    def insert_workspace(db: Session, params: dict[str, Any]) -> Any:
        result = db.execute(_INSERT_WORKSPACE_SQL, params)
        return result.fetchone()

    @staticmethod
    def insert_user(db: Session, params: dict[str, Any]) -> Any:
        result = db.execute(_INSERT_USER_SQL, params)
        return result.fetchone()

    @staticmethod
    def insert_password_reset(db: Session, params: dict[str, Any]) -> Any:
        result = db.execute(_INSERT_PASSWORD_RESET_SQL, params)
        return result.fetchone()

    @staticmethod
    def insert_provisioning_log(db: Session, params: dict[str, Any]) -> None:
        db.execute(_INSERT_PROVISIONING_LOG_SQL, params)

    @staticmethod
    def update_provisioning_status(db: Session, tenant_id: str, status: str) -> None:
        db.execute(
            _UPDATE_PROVISIONING_STATUS_SQL,
            {"tenant_id": tenant_id, "provisioning_status": status},
        )

    @staticmethod
    def insert_tenant_audit_log(db: Session, params: dict[str, Any]) -> None:
        db.execute(_INSERT_TENANT_AUDIT_SQL, params)

    @staticmethod
    def grant_workspace_admin(db: Session, workspace_id: str, actor_id: str) -> None:
        """Grant workspace_administrator role in control.workspace_role_assignments.

        ``actor_id`` maps to ``user_id`` and ``granted_by`` in the target table
        (self-grant during provisioning).  Idempotent — ON CONFLICT DO NOTHING.
        """
        db.execute(
            _GRANT_WORKSPACE_ADMIN_SQL,
            {
                "workspace_id": workspace_id,
                "user_id": actor_id,
                "role_name": "workspace_administrator",
                "granted_by": actor_id,
            },
        )

    @staticmethod
    def list_provisioning_logs(db: Session, tenant_id: str) -> list:
        result = db.execute(_LIST_PROVISIONING_LOGS_SQL, {"tenant_id": tenant_id})
        return [dict(row._mapping) for row in result.fetchall()]

    @staticmethod
    def find_tenant_by_id(db: Session, tenant_id: str) -> Any | None:
        """Return a row with id/name/slug/status/region/plan/provisioning_status
        for an existing tenant, or ``None`` when not found."""
        return db.execute(_FIND_TENANT_BY_ID_SQL, {"tenant_id": tenant_id}).fetchone()
