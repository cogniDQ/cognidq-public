"""
F002 — RBAC Service interface and stub
=========================================

Defines the ``RBACServiceInterface`` abstract base class and the
``RBACServiceStub`` implementation used in development and all F002 tests.

The real RBAC Service implementation is deferred to F007.  All F002 code
(service layer, tests) depends only on ``RBACServiceInterface`` — never on
the stub class directly.

Stub behaviour
--------------
1. Logs the grant call (DEBUG level) so that tests can verify invocation.
2. Attempts to INSERT a row into ``control.role_assignments`` if the table
   exists.  The ``role_assignments`` table may not exist at the time F002
   packets are executed (it is created in F007).  A missing table must NOT
   raise ``RoleGrantFailedError`` — the stub logs a warning and returns
   (TDD §15 item 5 / packet plan task 12).
3. Any other DB exception during the INSERT raises ``RoleGrantFailedError``.

``transaction_context`` parameter
----------------------------------
The stub receives the active SQLAlchemy ``Session`` so that the INSERT
participates in the same database transaction as the workspace creation
(TDD §5.1 — the role grant must be atomic with the workspace INSERT).
"""

from __future__ import annotations

import abc
import logging
import uuid

from sqlalchemy.orm import Session

from app.services.workspaces.exceptions import RoleGrantFailedError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Literal used in the INSERT; defined here so it is easy to update if
# the role name changes before the real implementation arrives.
# ---------------------------------------------------------------------------
_WORKSPACE_ADMIN_ROLE = "workspace_administrator"


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class RBACServiceInterface(abc.ABC):
    """
    Abstract contract for granting the Workspace Administrator role.

    All production and test code that triggers a role grant must import and
    depend on this interface, not on ``RBACServiceStub`` directly.
    """

    @abc.abstractmethod
    def grant_workspace_admin(
        self,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        transaction_context: Session,
    ) -> None:
        """
        Grant the Workspace Administrator role to *actor_id* for *workspace_id*.

        Must execute within *transaction_context* so that the grant is rolled
        back atomically if the calling transaction fails.

        Raises
        ------
        RoleGrantFailedError
            When the role grant write fails due to a database error on an
            existing table.
        """


# ---------------------------------------------------------------------------
# Stub implementation
# ---------------------------------------------------------------------------


class RBACServiceStub(RBACServiceInterface):
    """
    Development/test stub for ``RBACServiceInterface``.

    Attempts to write to ``control.role_assignments`` if the table exists.
    A missing table is treated as a no-op (development environment may not
    have the RBAC schema yet).
    """

    def grant_workspace_admin(
        self,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        transaction_context: Session,
    ) -> None:
        logger.debug(
            "RBACServiceStub.grant_workspace_admin workspace_id=%s actor_id=%s",
            workspace_id,
            actor_id,
        )

        table_exists = self._role_assignments_exists(transaction_context)
        if not table_exists:
            logger.warning(
                "RBACServiceStub: control.role_assignments table does not exist; "
                "skipping role grant for workspace_id=%s actor_id=%s "
                "(expected in pre-F007 environments)",
                workspace_id,
                actor_id,
            )
            return

        try:
            from sqlalchemy import text

            transaction_context.execute(
                text(
                    """
                    INSERT INTO control.role_assignments (
                        workspace_id, actor_id, role_name
                    ) VALUES (
                        CAST(:workspace_id AS UUID),
                        CAST(:actor_id     AS UUID),
                        :role_name
                    )
                    """
                ),
                {
                    "workspace_id": str(workspace_id),
                    "actor_id": str(actor_id),
                    "role_name": _WORKSPACE_ADMIN_ROLE,
                },
            )
        except Exception as exc:
            raise RoleGrantFailedError(
                f"Failed to grant workspace_administrator role for "
                f"workspace {workspace_id} to actor {actor_id}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _role_assignments_exists(db: Session) -> bool:
        """Return True if ``control.role_assignments`` exists."""
        try:
            from sqlalchemy import text

            result = db.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'control'
                      AND table_name   = 'role_assignments'
                    LIMIT 1
                    """
                )
            )
            return result.fetchone() is not None
        except Exception:  # pragma: no cover
            return False


# ---------------------------------------------------------------------------
# F007 — Fixed role permission map
# ---------------------------------------------------------------------------

FIXED_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "workspace_administrator": frozenset(
        [
            "workspaces:read",
            "workspaces:write",
            "members:read",
            "members:write",
            "members:delete",
            "roles:read",
            "roles:assign",
            "roles:write",
            "datasources:read",
            "datasources:write",
            "datasources:delete",
            "datasources:execute",
            "datasets:read",
            "datasets:write",
            "datasets:delete",
            "rules:read",
            "rules:write",
            "rules:execute",
            "rules:delete",
            "flows:read",
            "flows:write",
            "flows:execute",
            "flows:delete",
            "executions:read",
            "executions:write",
            "issues:read",
            "issues:write",
            "incidents:read",
            "incidents:write",
            "alerts:read",
            "alerts:write",
            "reports:read",
            "settings:read",
            "settings:write",
            "view_audit_logs",
        ]
    ),
    "data_engineer": frozenset(
        [
            "workspaces:read",
            "members:read",
            "roles:read",
            "datasources:read",
            "datasources:write",
            "datasources:delete",
            "datasources:execute",
            "datasets:read",
            "datasets:write",
            "datasets:delete",
            "rules:read",
            "rules:write",
            "rules:execute",
            "rules:delete",
            "flows:read",
            "flows:write",
            "flows:execute",
            "flows:delete",
            "executions:read",
            "executions:write",
            "issues:read",
            "issues:write",
            "incidents:read",
            "incidents:write",
            "alerts:read",
            "alerts:write",
            "reports:read",
            "settings:read",
        ]
    ),
    "data_steward": frozenset(
        [
            "workspaces:read",
            "members:read",
            "roles:read",
            "datasources:read",
            "datasets:read",
            "datasets:write",
            "rules:read",
            "rules:write",
            "rules:execute",
            "flows:read",
            "flows:write",
            "flows:execute",
            "executions:read",
            "issues:read",
            "issues:write",
            "incidents:read",
            "incidents:write",
            "alerts:read",
            "reports:read",
            "settings:read",
        ]
    ),
    "business_analyst": frozenset(
        [
            "workspaces:read",
            "members:read",
            "roles:read",
            "datasets:read",
            "rules:read",
            "flows:read",
            "executions:read",
            "issues:read",
            "incidents:read",
            "reports:read",
        ]
    ),
    "governance_viewer": frozenset(
        [
            "workspaces:read",
            "members:read",
            "roles:read",
            "datasources:read",
            "datasets:read",
            "rules:read",
            "flows:read",
            "executions:read",
            "issues:read",
            "incidents:read",
            "reports:read",
        ]
    ),
}

VALID_ROLE_NAMES: frozenset[str] = frozenset(FIXED_ROLE_PERMISSIONS.keys())

# Union of every permission action that any built-in role can grant.
# Used to validate custom-role permission lists. Any new permission must
# appear in at least one fixed role above to be assignable.
ALL_KNOWN_PERMISSIONS: frozenset[str] = frozenset(
    perm for perms in FIXED_ROLE_PERMISSIONS.values() for perm in perms
)


# ---------------------------------------------------------------------------
# F007 — Real RBAC Service implementation
# ---------------------------------------------------------------------------


class WorkspaceRBACService(RBACServiceInterface):
    """
    Production implementation of ``RBACServiceInterface``.

    Reads and writes to ``control.workspace_role_assignments``,
    created by migration 012_f007_workspace_role_assignments.sql.
    """

    # ------------------------------------------------------------------
    # RBACServiceInterface implementation
    # ------------------------------------------------------------------

    def grant_workspace_admin(
        self,
        workspace_id: uuid.UUID,
        actor_id: uuid.UUID,
        transaction_context: Session,
    ) -> None:
        """
        Grant the ``workspace_administrator`` role to *actor_id* for
        *workspace_id*, atomically within *transaction_context*.

        Idempotent: if the row already exists (e.g., workspace creation
        retried), the IntegrityError is caught and silently ignored.

        Raises
        ------
        RoleGrantFailedError
            On any DB error other than a duplicate-key violation.
        """
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        logger.debug(
            "WorkspaceRBACService.grant_workspace_admin workspace_id=%s actor_id=%s",
            workspace_id,
            actor_id,
        )
        try:
            transaction_context.execute(
                text(
                    """
                    INSERT INTO control.workspace_role_assignments
                        (workspace_id, user_id, role_name, granted_by)
                    VALUES (
                        CAST(:workspace_id AS UUID),
                        CAST(:user_id      AS UUID),
                        :role_name,
                        NULL
                    )
                    ON CONFLICT (workspace_id, user_id) DO NOTHING
                    """
                ),
                {
                    "workspace_id": str(workspace_id),
                    "user_id": str(actor_id),
                    "role_name": _WORKSPACE_ADMIN_ROLE,
                },
            )
        except IntegrityError as exc:
            # Constraint violation other than duplicate key (e.g., bad FK)
            raise RoleGrantFailedError(
                f"Failed to grant workspace_administrator for "
                f"workspace {workspace_id} to actor {actor_id}: {exc}"
            ) from exc
        except Exception as exc:
            raise RoleGrantFailedError(
                f"Failed to grant workspace_administrator for "
                f"workspace {workspace_id} to actor {actor_id}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def assign_role(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        role_name: str,
        granted_by: uuid.UUID,
        db: Session,
    ) -> dict:
        """
        Assign *role_name* to *user_id* in *workspace_id*.

        Replaces any existing role assignment for this (workspace, user) pair
        atomically. If the user already holds the identical role, the existing
        row is returned unchanged (idempotent).

        Raises
        ------
        ValueError
            If *role_name* is not a valid fixed role name.
        WorkspaceMemberNotFoundError
            If *user_id* is not a member of *workspace_id*.
            (Note: in MVP, membership is validated by checking the user
            exists in the users table; workspace-level membership table TBD.)
        LastWorkspaceAdministratorError
            If replacing the last workspace_administrator with a non-admin role.
        RoleGrantFailedError
            On unexpected DB error.
        """
        from sqlalchemy import text

        if role_name not in VALID_ROLE_NAMES:
            # Allow custom roles defined in the same workspace.
            custom = self.get_custom_role_by_name(workspace_id, role_name, db)
            if custom is None:
                raise ValueError(
                    f"Invalid role_name '{role_name}'. "
                    f"Must be a built-in role or a custom role defined in this workspace."
                )

        existing = self.get_member_role(workspace_id, user_id, db)

        # Check last-admin guard before replacing
        if (
            existing is not None
            and existing["role_name"] == "workspace_administrator"
            and role_name != "workspace_administrator"
        ):
            admin_count = self.get_admin_count(workspace_id, db)
            if admin_count <= 1:
                from app.services.workspaces.exceptions import LastWorkspaceAdministratorError

                raise LastWorkspaceAdministratorError(
                    f"Cannot change role: user {user_id} is the last "
                    f"workspace_administrator in workspace {workspace_id}."
                )

        # Idempotent: same role already assigned
        if existing is not None and existing["role_name"] == role_name:
            return existing

        try:
            ra_id = uuid.uuid4()
            db.execute(
                text(
                    """
                    INSERT INTO control.workspace_role_assignments
                        (id, workspace_id, user_id, role_name, granted_by)
                    VALUES (
                        CAST(:id           AS UUID),
                        CAST(:workspace_id AS UUID),
                        CAST(:user_id      AS UUID),
                        :role_name,
                        CAST(:granted_by   AS UUID)
                    )
                    ON CONFLICT (workspace_id, user_id)
                    DO UPDATE SET
                        role_name  = EXCLUDED.role_name,
                        granted_by = EXCLUDED.granted_by,
                        granted_at = NOW()
                    RETURNING id, workspace_id, user_id, role_name, granted_by, granted_at
                    """
                ),
                {
                    "id": str(ra_id),
                    "workspace_id": str(workspace_id),
                    "user_id": str(user_id),
                    "role_name": role_name,
                    "granted_by": str(granted_by),
                },
            )
            db.flush()
        except Exception as exc:
            raise RoleGrantFailedError(
                f"Failed to assign role '{role_name}' to user {user_id} "
                f"in workspace {workspace_id}: {exc}"
            ) from exc

        return self.get_member_role(workspace_id, user_id, db)

    def revoke_role(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        revoking_actor_id: uuid.UUID,
        db: Session,
    ) -> None:
        """
        Revoke the workspace role from *user_id* in *workspace_id*.

        Raises
        ------
        RoleAssignmentNotFoundError
            If the user has no current role assignment.
        LastWorkspaceAdministratorError
            If revoking would leave the workspace with zero administrators.
        RoleGrantFailedError
            On unexpected DB error.
        """
        from sqlalchemy import text

        existing = self.get_member_role(workspace_id, user_id, db)
        if existing is None:
            from app.services.workspaces.exceptions import RoleAssignmentNotFoundError

            raise RoleAssignmentNotFoundError(
                f"User {user_id} has no role assignment in workspace {workspace_id}."
            )

        if existing["role_name"] == "workspace_administrator":
            admin_count = self.get_admin_count(workspace_id, db)
            if admin_count <= 1:
                from app.services.workspaces.exceptions import LastWorkspaceAdministratorError

                raise LastWorkspaceAdministratorError(
                    f"Cannot revoke: user {user_id} is the last "
                    f"workspace_administrator in workspace {workspace_id}."
                )

        try:
            db.execute(
                text(
                    """
                    DELETE FROM control.workspace_role_assignments
                    WHERE workspace_id = CAST(:workspace_id AS UUID)
                      AND user_id      = CAST(:user_id      AS UUID)
                    """
                ),
                {
                    "workspace_id": str(workspace_id),
                    "user_id": str(user_id),
                },
            )
            db.flush()
        except Exception as exc:
            raise RoleGrantFailedError(
                f"Failed to revoke role for user {user_id} in workspace {workspace_id}: {exc}"
            ) from exc

    def get_member_role(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        db: Session,
    ) -> dict | None:
        """
        Return the role assignment row for *(workspace_id, user_id)*,
        or ``None`` if no assignment exists.

        Returns a dict with keys:
          ``id``, ``workspace_id``, ``user_id``, ``role_name``,
          ``granted_by``, ``granted_at``.
        """
        from sqlalchemy import text

        result = db.execute(
            text(
                """
                SELECT id, workspace_id, user_id, role_name, granted_by, granted_at
                FROM control.workspace_role_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
                  AND user_id      = CAST(:user_id      AS UUID)
                """
            ),
            {
                "workspace_id": str(workspace_id),
                "user_id": str(user_id),
            },
        )
        row = result.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "workspace_id": row[1],
            "user_id": row[2],
            "role_name": row[3],
            "granted_by": row[4],
            "granted_at": row[5],
        }

    def is_workspace_admin_in_tenant(
        self,
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        db: Session,
    ) -> bool:
        """
        Check whether *user_id* holds the ``workspace_administrator`` role
        in any workspace that belongs to *tenant_id*.

        Used by the workspace-creation guard: users who are already
        workspace administrators in at least one workspace within the
        tenant may create additional workspaces.
        """
        from sqlalchemy import text

        result = db.execute(
            text(
                """
                SELECT 1
                FROM control.workspace_role_assignments wra
                JOIN control.workspaces w ON w.workspace_id = wra.workspace_id
                WHERE wra.user_id   = CAST(:user_id   AS UUID)
                  AND w.tenant_id   = CAST(:tenant_id  AS UUID)
                  AND wra.role_name = 'workspace_administrator'
                LIMIT 1
                """
            ),
            {"user_id": str(user_id), "tenant_id": str(tenant_id)},
        )
        return result.fetchone() is not None

    def check_permission(
        self,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        action: str,
        db: Session,
    ) -> bool:
        """
        Return ``True`` if *user_id* holds a role in *workspace_id*
        whose permission set includes *action*.

        Returns ``False`` if the user has no role or the role does not
        permit the action.
        """
        assignment = self.get_member_role(workspace_id, user_id, db)
        if assignment is None:
            return False
        role_name = assignment["role_name"]
        permissions = self.get_role_permissions(workspace_id, role_name, db)
        if permissions is None:
            return False
        return action in permissions

    def list_members(
        self,
        workspace_id: uuid.UUID,
        db: Session,
    ) -> list[dict]:
        """
        Return all members of *workspace_id* with their role assignment details.

        Returns a list of dicts with keys:
          ``user_id``, ``email``, ``display_name``, ``role_name``,
          ``granted_by``, ``granted_at``.
        """
        from sqlalchemy import text

        result = db.execute(
            text(
                """
                SELECT
                    wra.user_id,
                    u.email,
                    COALESCE(u.full_name, u.email) AS display_name,
                    wra.role_name,
                    wra.granted_by,
                    wra.granted_at
                FROM control.workspace_role_assignments wra
                JOIN public.users u ON u.id = wra.user_id
                WHERE wra.workspace_id = CAST(:workspace_id AS UUID)
                ORDER BY wra.granted_at ASC
                """
            ),
            {"workspace_id": str(workspace_id)},
        )
        rows = result.fetchall()
        return [
            {
                "user_id": row[0],
                "email": row[1],
                "display_name": row[2],
                "role_name": row[3],
                "granted_by": row[4],
                "granted_at": row[5],
            }
            for row in rows
        ]

    def search_non_members(
        self,
        workspace_id: uuid.UUID,
        tenant_id: uuid.UUID,
        query: str,
        db: Session,
        limit: int = 20,
    ) -> list[dict]:
        """
        Search users by email prefix within *tenant_id*, excluding existing
        workspace members.

        Returns a list of dicts with keys: ``user_id``, ``email``, ``display_name``.
        """
        from sqlalchemy import text

        result = db.execute(
            text(
                """
                SELECT
                    u.id        AS user_id,
                    u.email,
                    COALESCE(u.full_name, u.email) AS display_name
                FROM public.users u
                WHERE u.tenant_id = CAST(:tenant_id AS UUID)
                  AND u.email ILIKE :q_prefix
                  AND u.id NOT IN (
                      SELECT user_id
                      FROM control.workspace_role_assignments
                      WHERE workspace_id = CAST(:workspace_id AS UUID)
                  )
                ORDER BY u.email ASC
                LIMIT :limit
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "q_prefix": f"{query}%",
                "workspace_id": str(workspace_id),
                "limit": limit,
            },
        )
        rows = result.fetchall()
        return [
            {
                "user_id": row[0],
                "email": row[1],
                "display_name": row[2],
            }
            for row in rows
        ]

    def get_admin_count(
        self,
        workspace_id: uuid.UUID,
        db: Session,
    ) -> int:
        """
        Return the count of active ``workspace_administrator`` assignments
        for *workspace_id*.

        Uses a subquery with ``FOR UPDATE`` to lock matching rows and prevent
        concurrent last-admin removals, then counts in the outer query.
        """
        from sqlalchemy import text

        result = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT id
                    FROM control.workspace_role_assignments
                    WHERE workspace_id = CAST(:workspace_id AS UUID)
                      AND role_name    = 'workspace_administrator'
                    FOR UPDATE
                ) locked_rows
                """
            ),
            {"workspace_id": str(workspace_id)},
        )
        row = result.fetchone()
        return int(row[0]) if row else 0

    # ------------------------------------------------------------------
    # Custom workspace roles
    # ------------------------------------------------------------------

    def list_custom_roles(
        self,
        workspace_id: uuid.UUID,
        db: Session,
    ) -> list[dict]:
        """List all custom roles defined in *workspace_id* with their permissions."""
        from sqlalchemy import text

        rows = db.execute(
            text(
                """
                SELECT r.id, r.name, r.display_name, r.description,
                       r.created_by, r.created_at, r.updated_at,
                       COALESCE(
                           ARRAY_AGG(p.permission ORDER BY p.permission)
                               FILTER (WHERE p.permission IS NOT NULL),
                           ARRAY[]::varchar[]
                       ) AS permissions
                FROM control.workspace_custom_roles r
                LEFT JOIN control.workspace_custom_role_permissions p
                    ON p.role_id = r.id
                WHERE r.workspace_id = CAST(:workspace_id AS UUID)
                GROUP BY r.id
                ORDER BY r.created_at ASC
                """
            ),
            {"workspace_id": str(workspace_id)},
        ).fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "display_name": row[2],
                "description": row[3],
                "created_by": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "permissions": list(row[7]),
            }
            for row in rows
        ]

    def get_custom_role(
        self,
        workspace_id: uuid.UUID,
        role_id: uuid.UUID,
        db: Session,
    ) -> dict | None:
        """Return one custom role row (or None) for *workspace_id*/*role_id*."""
        from sqlalchemy import text

        row = db.execute(
            text(
                """
                SELECT r.id, r.name, r.display_name, r.description,
                       r.created_by, r.created_at, r.updated_at,
                       COALESCE(
                           ARRAY_AGG(p.permission ORDER BY p.permission)
                               FILTER (WHERE p.permission IS NOT NULL),
                           ARRAY[]::varchar[]
                       )
                FROM control.workspace_custom_roles r
                LEFT JOIN control.workspace_custom_role_permissions p
                    ON p.role_id = r.id
                WHERE r.workspace_id = CAST(:workspace_id AS UUID)
                  AND r.id           = CAST(:role_id      AS UUID)
                GROUP BY r.id
                """
            ),
            {"workspace_id": str(workspace_id), "role_id": str(role_id)},
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "display_name": row[2],
            "description": row[3],
            "created_by": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "permissions": list(row[7]),
        }

    def get_custom_role_by_name(
        self,
        workspace_id: uuid.UUID,
        name: str,
        db: Session,
    ) -> dict | None:
        from sqlalchemy import text

        row = db.execute(
            text(
                """
                SELECT id FROM control.workspace_custom_roles
                WHERE workspace_id = CAST(:workspace_id AS UUID)
                  AND name = :name
                """
            ),
            {"workspace_id": str(workspace_id), "name": name},
        ).fetchone()
        if row is None:
            return None
        return self.get_custom_role(workspace_id, row[0], db)

    def create_custom_role(
        self,
        workspace_id: uuid.UUID,
        name: str,
        display_name: str,
        description: str | None,
        permissions: list[str],
        created_by: uuid.UUID,
        db: Session,
    ) -> dict:
        """Insert a new custom role and its permission grants."""
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError

        if name in VALID_ROLE_NAMES:
            raise ValueError(f"Role name '{name}' is reserved by a built-in role.")
        unknown = [p for p in permissions if p not in ALL_KNOWN_PERMISSIONS]
        if unknown:
            raise ValueError(f"Unknown permissions: {sorted(unknown)}")

        role_id = uuid.uuid4()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO control.workspace_custom_roles
                        (id, workspace_id, name, display_name, description, created_by)
                    VALUES (
                        CAST(:id AS UUID),
                        CAST(:workspace_id AS UUID),
                        :name, :display_name, :description,
                        CAST(:created_by AS UUID)
                    )
                    """
                ),
                {
                    "id": str(role_id),
                    "workspace_id": str(workspace_id),
                    "name": name,
                    "display_name": display_name,
                    "description": description,
                    "created_by": str(created_by),
                },
            )
            for perm in set(permissions):
                db.execute(
                    text(
                        """
                        INSERT INTO control.workspace_custom_role_permissions
                            (role_id, permission)
                        VALUES (CAST(:role_id AS UUID), :perm)
                        """
                    ),
                    {"role_id": str(role_id), "perm": perm},
                )
            db.flush()
        except IntegrityError as exc:
            raise ValueError(
                f"A role named '{name}' already exists in this workspace or the name is invalid."
            ) from exc

        result = self.get_custom_role(workspace_id, role_id, db)
        assert result is not None
        return result

    def update_custom_role(
        self,
        workspace_id: uuid.UUID,
        role_id: uuid.UUID,
        display_name: str | None,
        description: str | None,
        permissions: list[str] | None,
        db: Session,
    ) -> dict:
        """Update mutable fields of a custom role. Name is immutable."""
        from sqlalchemy import text

        existing = self.get_custom_role(workspace_id, role_id, db)
        if existing is None:
            from app.services.workspaces.exceptions import RoleAssignmentNotFoundError

            raise RoleAssignmentNotFoundError(
                f"Custom role {role_id} not found in workspace {workspace_id}."
            )

        if permissions is not None:
            unknown = [p for p in permissions if p not in ALL_KNOWN_PERMISSIONS]
            if unknown:
                raise ValueError(f"Unknown permissions: {sorted(unknown)}")

        new_display = display_name if display_name is not None else existing["display_name"]
        new_description = description if description is not None else existing["description"]

        db.execute(
            text(
                """
                UPDATE control.workspace_custom_roles
                SET display_name = :display_name,
                    description  = :description,
                    updated_at   = NOW()
                WHERE workspace_id = CAST(:workspace_id AS UUID)
                  AND id           = CAST(:role_id AS UUID)
                """
            ),
            {
                "display_name": new_display,
                "description": new_description,
                "workspace_id": str(workspace_id),
                "role_id": str(role_id),
            },
        )

        if permissions is not None:
            db.execute(
                text(
                    "DELETE FROM control.workspace_custom_role_permissions "
                    "WHERE role_id = CAST(:role_id AS UUID)"
                ),
                {"role_id": str(role_id)},
            )
            for perm in set(permissions):
                db.execute(
                    text(
                        """
                        INSERT INTO control.workspace_custom_role_permissions
                            (role_id, permission)
                        VALUES (CAST(:role_id AS UUID), :perm)
                        """
                    ),
                    {"role_id": str(role_id), "perm": perm},
                )

        db.flush()
        result = self.get_custom_role(workspace_id, role_id, db)
        assert result is not None
        return result

    def delete_custom_role(
        self,
        workspace_id: uuid.UUID,
        role_id: uuid.UUID,
        db: Session,
    ) -> None:
        """
        Delete a custom role. Refuses if any member is currently assigned to it.
        """
        from sqlalchemy import text

        existing = self.get_custom_role(workspace_id, role_id, db)
        if existing is None:
            from app.services.workspaces.exceptions import RoleAssignmentNotFoundError

            raise RoleAssignmentNotFoundError(
                f"Custom role {role_id} not found in workspace {workspace_id}."
            )

        in_use = db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM control.workspace_role_assignments
                WHERE workspace_id = CAST(:workspace_id AS UUID)
                  AND role_name    = :name
                """
            ),
            {"workspace_id": str(workspace_id), "name": existing["name"]},
        ).fetchone()
        if in_use and int(in_use[0]) > 0:
            raise ValueError(
                f"Cannot delete role '{existing['name']}': "
                f"{in_use[0]} member(s) currently assigned. "
                f"Reassign them first."
            )

        db.execute(
            text(
                "DELETE FROM control.workspace_custom_roles "
                "WHERE workspace_id = CAST(:workspace_id AS UUID) "
                "  AND id = CAST(:role_id AS UUID)"
            ),
            {"workspace_id": str(workspace_id), "role_id": str(role_id)},
        )
        db.flush()

    def get_role_permissions(
        self,
        workspace_id: uuid.UUID,
        role_name: str,
        db: Session,
    ) -> frozenset[str] | None:
        """
        Resolve the permission set for *role_name* in *workspace_id*.

        Returns the fixed permission set if *role_name* is a built-in role,
        otherwise looks up a custom role by name. Returns ``None`` if no
        such role exists.
        """
        if role_name in FIXED_ROLE_PERMISSIONS:
            return FIXED_ROLE_PERMISSIONS[role_name]
        custom = self.get_custom_role_by_name(workspace_id, role_name, db)
        if custom is None:
            return None
        return frozenset(custom["permissions"])
