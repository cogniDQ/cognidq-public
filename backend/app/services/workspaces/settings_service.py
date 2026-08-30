"""
F003 — Workspace Settings Service
===================================

Business logic for reading and updating workspace default policies.

This module is responsible for:
  - Verifying workspace existence (with tenant scoping or cross-tenant bypass)
  - Loading or auto-creating the settings row (BR-08 fallback)
  - Applying built-in defaults for NULL policy fields
  - Detecting and writing mutations with audit trail (P05)

The service functions operate at the boundary between the API layer and
the repository/validation layers.  They do NOT own transaction boundaries
for the write path — the endpoint handler calls ``db.commit()`` after the
service returns successfully.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

import app.services.workspaces.settings_repository as _settings_repo
from app.api.v1.dependencies.workspace_auth import (
    PLATFORM_OPERATOR_ROLES,
    WorkspaceActorContext,
)
from app.services.incidents.auto_incident_models import IncidentPolicy
from app.services.workspaces.metrics import (
    emit_workspace_settings_noop,
    emit_workspace_settings_read_success,
    emit_workspace_settings_update_success,
)
from app.services.workspaces.models import WorkspaceAuditLog, WorkspaceStatus
from app.services.workspaces.repository import AuditLogWriter, WorkspaceRepository
from app.services.workspaces.settings_models import (
    LLMConfig,
    NamingConstraint,
    NamingStandards,
    SeverityPolicy,
    SLAPolicy,
    WorkspaceSettings,
    WorkspaceSettingsUpdate,
)
from app.services.workspaces.settings_validation import (
    detect_unknown_fields,
    is_empty_request,
    validate_settings_update_payload,
)

logger = logging.getLogger(__name__)

# Module-level singleton repositories (stateless; safe to share).
_workspace_repo = WorkspaceRepository()
_audit_writer = AuditLogWriter()


class UnknownFieldError(Exception):
    """Raised when the PATCH body contains unrecognised top-level keys."""

    def __init__(self, unknown: list[str]):
        self.unknown = unknown
        super().__init__(f"Unknown fields: {unknown}")


class EmptyRequestError(Exception):
    """Raised when the PATCH body contains no recognised policy field."""


def get_settings(
    db: Session,
    workspace_id: UUID,
    actor: WorkspaceActorContext,
) -> WorkspaceSettings:
    """Return the effective workspace settings for the given workspace.

    Flow (TDD §5.1 get_settings):
    1. Determine effective tenant_id: None for Platform Operators; actor's
       tenant_id for all workspace-scoped roles.
    2. Verify workspace exists — delegates to ``WorkspaceRepository.find_by_id``
       which raises ``WorkspaceNotFoundError`` if the row is absent or belongs to
       a different Tenant.
    3. Load settings row — ``SettingsRepository.find_by_workspace_id``.
    4. BR-08 fallback: if the settings row is missing (should not happen in
       normal operation because the DB trigger creates it on workspace creation),
       create a default row and return it.
    5. Apply ``with_defaults()`` so that NULL JSONB policy fields are replaced
       by the module-level built-in constants before the caller serialises.
    6. Return the fully-populated ``WorkspaceSettings``.

    Parameters
    ----------
    db:
        SQLAlchemy session (NOT yet committed by the caller for this read path).
    workspace_id:
        UUID of the target workspace.
    actor:
        Resolved JWT actor context (provides tenant_id and role).

    Raises
    ------
    WorkspaceNotFoundError
        When the workspace does not exist or belongs to a different Tenant
        (for non-Platform-Operator actors).
    """
    is_platform_operator = actor.actor_role in PLATFORM_OPERATOR_ROLES
    tenant_id: UUID | None = None if is_platform_operator else actor.tenant_id

    logger.debug(
        "get_settings: workspace_id=%s actor_id=%s role=%s is_po=%s",
        workspace_id,
        actor.actor_id,
        actor.actor_role,
        is_platform_operator,
    )

    # Step 2 — verify workspace exists (raises WorkspaceNotFoundError on miss)
    _workspace_repo.find_by_id(db, workspace_id, tenant_id=tenant_id)

    # Step 3 — load settings row
    settings = _settings_repo.find_by_workspace_id(db, workspace_id, tenant_id=tenant_id)

    if settings is None:
        # Step 4 — BR-08 fallback: create defaults and return
        logger.warning(
            "get_settings: settings row missing for workspace_id=%s — creating defaults",
            workspace_id,
        )
        effective_tenant_id = actor.tenant_id if tenant_id is None else tenant_id
        settings = _settings_repo.create_default(
            db,
            workspace_id,
            effective_tenant_id,
            "UTC",
        )
        db.commit()

    # Step 5 — apply built-in defaults for NULL JSONB policy columns
    result = settings.with_defaults()
    emit_workspace_settings_read_success()
    return result


# ---------------------------------------------------------------------------
# Helper: build WorkspaceSettingsUpdate from validated PATCH body
# ---------------------------------------------------------------------------


def _build_update(body: dict, current: WorkspaceSettings) -> WorkspaceSettingsUpdate:
    """Convert PATCH body dict → ``WorkspaceSettingsUpdate`` with only changed fields.

    Compares each present body field against the current stored value.
    Fields that are identical (normalised) are left as None so the repository
    skips them, achieving minimal-write no-op detection.
    """
    update = WorkspaceSettingsUpdate()

    if "timezone_policy" in body:
        new_tz = body["timezone_policy"].get("default_timezone")
        if new_tz != current.default_timezone:
            update.default_timezone = new_tz

    if "severity_policy" in body:
        sp_body = body["severity_policy"]
        new_sp = SeverityPolicy(
            critical_label=sp_body["critical_label"],
            major_label=sp_body["major_label"],
            minor_label=sp_body["minor_label"],
            informational_label=sp_body["informational_label"],
        )
        # current.severity_policy is never None after with_defaults()
        if new_sp != current.severity_policy:
            update.severity_policy = new_sp

    if "sla_policy" in body:
        sl_body = body["sla_policy"]
        new_sla = SLAPolicy(
            critical_hours=sl_body["critical_hours"],
            major_hours=sl_body["major_hours"],
            minor_hours=sl_body["minor_hours"],
            informational_hours=sl_body.get("informational_hours"),
        )
        if new_sla != current.sla_policy:
            update.sla_policy = new_sla

    if "issue_grouping_policy" in body:
        new_igp = body["issue_grouping_policy"]
        if new_igp != current.issue_grouping_policy:
            update.issue_grouping_policy = new_igp

    if "naming_standards" in body:
        ns_body = body["naming_standards"]

        def _nc(d: dict) -> NamingConstraint:
            return NamingConstraint(
                required_prefix=d.get("required_prefix"),
                required_suffix=d.get("required_suffix"),
                pattern=d.get("pattern"),
                max_length=d.get("max_length"),
                allow_special_characters=d.get("allow_special_characters"),
            )

        new_ns = NamingStandards(
            datasets=_nc(ns_body.get("datasets", {})),
            rules=_nc(ns_body.get("rules", {})),
        )
        if new_ns != current.naming_standards:
            update.naming_standards = new_ns

    if "llm_config" in body:
        from app.services.data_sources.credential_service import encrypt_string

        lc_body = body["llm_config"]
        api_key_encrypted = encrypt_string(lc_body["api_key"])
        new_lc = LLMConfig(
            provider=lc_body["provider"],
            api_key_encrypted=api_key_encrypted,
            model=lc_body["model"],
            temperature=lc_body.get("temperature", 0.0),
            max_tokens=lc_body.get("max_tokens", 4096),
        )
        # Always write — API key is re-encrypted each time so comparison is not meaningful
        update.llm_config = new_lc

    if "incident_policy" in body:
        ip_body = body["incident_policy"] or {}
        # Use existing policy as base for partial updates; fall back to the
        # current effective policy (which may be the shipping default if the
        # workspace has never customised it).
        base = current.incident_policy
        new_ip = IncidentPolicy(
            enabled=bool(ip_body.get("enabled", base.enabled if base else True)),
            min_severity=str(ip_body.get("min_severity", base.min_severity if base else "major")),
            recurrence_threshold=int(
                ip_body.get("recurrence_threshold", base.recurrence_threshold if base else 1)
            ),
            auto_priority=ip_body.get("auto_priority", base.auto_priority if base else None),
            auto_owner_user_id=ip_body.get(
                "auto_owner_user_id", base.auto_owner_user_id if base else None
            ),
        )
        if new_ip != current.incident_policy:
            update.incident_policy = new_ip

    return update


def _has_changes(update: WorkspaceSettingsUpdate) -> bool:
    """Return True if at least one field is not None."""
    return any(getattr(update, f.name) is not None for f in dataclasses.fields(update))


def _collect_changed_fields(update: WorkspaceSettingsUpdate) -> list[str]:
    return [f.name for f in dataclasses.fields(update) if getattr(update, f.name) is not None]


# ---------------------------------------------------------------------------
# update_settings  (TDD §5.1)
# ---------------------------------------------------------------------------


def update_settings(
    db: Session,
    workspace_id: UUID,
    body: dict,
    actor: WorkspaceActorContext,
    request_id: UUID | None = None,
    source_ip: str | None = None,
) -> WorkspaceSettings:
    """Apply a partial settings update with audit trail (TDD §5.1).

    Flow:
    1. Detect and reject unknown top-level keys.
    2. Reject empty request (no recognised keys).
    3. Verify workspace exists and belongs to actor's tenant.
    4. Reject archived workspaces.
    5. Validate the full payload.
    6. Load current settings (create defaults if missing).
    7. Compute changed fields via deep comparison.
    8. No-op: if nothing changed, return current settings without audit.
    9. Acquire SELECT FOR UPDATE lock + UPDATE.
    10. Write audit log inside the same transaction.
    11. Return updated settings with defaults applied.

    The caller (endpoint handler) calls ``db.commit()`` after this method
    returns successfully.

    Raises
    ------
    UnknownFieldError
    EmptyRequestError
    WorkspaceNotFoundError
    WorkspaceArchivedError (via exceptions.py alias WorkspaceArchivedError)
    WorkspaceAPIError (if validation fails)
    """
    from app.services.workspaces.exceptions import WorkspaceArchivedError

    # Step 1 — unknown fields
    unknown = detect_unknown_fields(body)
    if unknown:
        raise UnknownFieldError(unknown)

    # Step 2 — empty request
    if is_empty_request(body):
        raise EmptyRequestError()

    # Platform operators (platform_admin) can update settings across all tenants;
    # pass None so the repository performs a cross-tenant lookup.
    is_platform_operator = actor.actor_role in PLATFORM_OPERATOR_ROLES
    effective_tenant_id: UUID | None = None if is_platform_operator else actor.tenant_id

    # Step 3 — verify workspace (raises WorkspaceNotFoundError on miss)
    workspace = _workspace_repo.find_by_id(db, workspace_id, tenant_id=effective_tenant_id)

    # Step 4 — archived check
    if workspace.status == WorkspaceStatus.archived:
        raise WorkspaceArchivedError(
            f"Cannot update settings for archived workspace {workspace_id}."
        )

    # Step 5 — validate payload
    validation_result = validate_settings_update_payload(body)
    if not validation_result.is_valid:
        from app.services.workspaces.errors import WorkspaceAPIError

        fields = [
            {"field": e.field, "error_code": e.error_code, "message": e.message}
            for e in validation_result.errors
        ]
        raise WorkspaceAPIError(
            status_code=422,
            code=validation_result.errors[0].error_code,
            message=validation_result.errors[0].message,
            fields=fields,
        )

    # Step 6 — load current settings
    current = _settings_repo.find_by_workspace_id(db, workspace_id, tenant_id=effective_tenant_id)
    if current is None:
        # Use the actual workspace tenant_id (resolved from the workspace row) when creating defaults,
        # since for platform operators effective_tenant_id is None.
        settings_tenant_id = workspace.tenant_id if is_platform_operator else actor.tenant_id
        current = _settings_repo.create_default(db, workspace_id, settings_tenant_id, "UTC")

    current_with_defaults = current.with_defaults()

    # Step 7 — compute changed fields (compare against defaults-applied current)
    update = _build_update(body, current_with_defaults)

    # Step 8 — no-op
    if not _has_changes(update):
        logger.debug(
            "update_settings: no-op for workspace_id=%s (no actual changes)",
            workspace_id,
        )
        emit_workspace_settings_noop()
        return current_with_defaults

    # Step 9 — acquire lock + update
    # The repository's update_settings requires a non-None tenant_id; for platform
    # operators use the workspace's actual tenant_id (resolved in Step 3).
    repo_tenant_id = workspace.tenant_id if is_platform_operator else actor.tenant_id
    changed_fields = _collect_changed_fields(update)
    now = datetime.now(UTC)

    updated = _settings_repo.update_settings(
        db,
        workspace_id=workspace_id,
        tenant_id=repo_tenant_id,
        update=update,
        actor_id=actor.actor_id,
        now=now,
    )

    # Step 10 — audit log (same transaction)
    audit_tenant_id = workspace.tenant_id if is_platform_operator else actor.tenant_id
    _audit_writer.write(
        db,
        WorkspaceAuditLog(
            tenant_id=audit_tenant_id,
            workspace_id=workspace_id,
            action_type="workspace_settings_updated",
            actor_id=actor.actor_id,
            actor_role=actor.actor_role,
            new_data={
                "workspace_id": str(workspace_id),
                "changed_fields": changed_fields,
            },
            occurred_at=now,
            request_id=request_id,
            source_ip=source_ip,
        ),
    )

    # Step 11 — return with defaults applied
    emit_workspace_settings_update_success(",".join(sorted(changed_fields)))
    return updated.with_defaults()
