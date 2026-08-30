"""
F002 — Typed exceptions for the Workspace bounded context
===========================================================

All exceptions inherit from ``WorkspaceError`` so that callers can catch the
base class if needed.  The HTTP/controller layer translates each exception to
the appropriate HTTP status code and error body as defined in TDD §4 and §5.1.

Exception catalogue
-------------------
``DuplicateNameError``
    Raised by ``WorkspaceRepository.insert_workspace`` when the database
    returns a unique-constraint violation on
    ``uq_workspaces_name_lower_per_tenant``.

``DuplicateSlugError``
    Raised by ``WorkspaceRepository.insert_workspace`` when the database
    returns a unique-constraint violation on
    ``uq_workspaces_slug_per_tenant``.

``WorkspaceNotFoundError``
    Raised by ``WorkspaceRepository.find_by_id`` when the query returns zero
    rows.  Also raised if the ``workspace_id`` belongs to a different tenant
    (tenant isolation is enforced by the ``AND tenant_id = :tenant_id``
    clause, so a cross-tenant lookup simply returns zero rows).

``TenantNotFoundError``
    Raised by ``TenantRepository.find_tenant_by_id`` when the tenant row is
    absent.

``TenantNotActiveError``
    Raised by the *service layer* (not the repository) after reading the
    tenant status and finding it is not ``active``.

``WorkspaceArchivedError``
    Raised by the *service layer* when attempting to update a workspace
    whose status is ``archived``.

``ForbiddenTransitionError``
    Raised by the *service layer* when a status transition is not permitted
    (e.g., archiving an already-archived workspace, restoring an active one).

``LastActiveWorkspaceError``
    Raised during archival when the workspace is the last active one in the
    Tenant and ``confirm_last_workspace`` is not strictly ``True``.

``WorkspaceValidationError``
    Raised by the *service layer* when field-level validation fails after
    a precondition check (i.e., status_reason validation post status-check).
    Carries the list of field-error dicts so the controller can format
    them as HTTP 422.

``RoleGrantFailedError``
    Raised by ``RBACServiceStub`` when the INSERT into ``role_assignments``
    fails with a DB exception on an **existing** table.

``AuditWriteFailedError``
    Raised by ``AuditLogWriter.write`` on any DB exception during the audit
    log INSERT.
"""

from __future__ import annotations


class WorkspaceError(Exception):
    """Base class for all Workspace bounded-context exceptions."""


class DuplicateNameError(WorkspaceError):
    """Workspace name (case-insensitive, tenant-scoped) already exists."""


class DuplicateSlugError(WorkspaceError):
    """Workspace slug (tenant-scoped) already exists."""


class WorkspaceNotFoundError(WorkspaceError):
    """Workspace not found or cross-tenant access attempted."""


class TenantNotFoundError(WorkspaceError):
    """Tenant row not found in the database."""


class TenantNotActiveError(WorkspaceError):
    """Tenant exists but its status is not ``active``."""


class WorkspaceArchivedError(WorkspaceError):
    """Workspace status is ``archived`` and mutation cannot proceed."""


class ForbiddenTransitionError(WorkspaceError):
    """Status transition not permitted in the workspace's current state."""


class LastActiveWorkspaceError(WorkspaceError):
    """Cannot archive: this is the last active workspace in the Tenant."""


class WorkspaceValidationError(WorkspaceError):
    """
    Field-level validation errors raised by the service layer after
    a precondition check (e.g., status_reason validation post status-check).

    Attributes
    ----------
    validation_errors : list[dict]
        List of field-error dicts compatible with ``format_validation_errors``.
    """

    def __init__(self, validation_errors: list) -> None:
        super().__init__("Validation failed")
        self.validation_errors = validation_errors


class RoleGrantFailedError(WorkspaceError):
    """RBAC role grant write failed with a database error."""


class AuditWriteFailedError(WorkspaceError):
    """Audit log write failed with a database error."""


# ─────────────────────────────────────────────────────────────────────────────
# F007 — RBAC exceptions
# ─────────────────────────────────────────────────────────────────────────────


class LastWorkspaceAdministratorError(WorkspaceError):
    """
    Raised when an operation would leave the workspace with zero
    ``workspace_administrator`` role assignments.

    Translates to HTTP 409 with error_code ``LAST_WORKSPACE_ADMINISTRATOR``.
    """


class WorkspaceMemberNotFoundError(WorkspaceError):
    """
    Raised when the target user is not an active member of the workspace.

    Translates to HTTP 404 with error_code ``WORKSPACE_MEMBER_NOT_FOUND``.
    """


class RoleAssignmentNotFoundError(WorkspaceError):
    """
    Raised when a role assignment is expected but does not exist.

    Translates to HTTP 404 with error_code ``ROLE_ASSIGNMENT_NOT_FOUND``.
    """
