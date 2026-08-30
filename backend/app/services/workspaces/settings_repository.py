"""
F003 — Workspace Settings repository
======================================

Provides raw SQL read/write operations against ``control.workspace_settings``.
Follows the same ``text()``-with-named-parameters pattern as ``repository.py``.

All JSONB columns are serialised via ``json.dumps()`` when writing and
deserialised via JSON parsing when reading.  Null JSONB columns are returned
as ``None`` in the domain model.

Module-level public functions (not class methods) mirror the pattern used in
``validation.py`` and keep the module import surface minimal.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.incidents.auto_incident_models import IncidentPolicy
from app.services.workspaces.settings_models import (
    LLMConfig,
    NamingConstraint,
    NamingStandards,
    SeverityPolicy,
    SLAPolicy,
    WorkspaceSettings,
    WorkspaceSettingsUpdate,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Custom exception
# ─────────────────────────────────────────────────────────────────────────────


class SettingsNotFoundError(Exception):
    """Raised when a workspace_settings row is expected but absent."""


# ─────────────────────────────────────────────────────────────────────────────
# SQL constants
# ─────────────────────────────────────────────────────────────────────────────

_SELECT_SETTINGS_COLS = """
    workspace_id::text,
    tenant_id::text,
    default_timezone,
    severity_policy,
    sla_policy,
    issue_grouping_policy,
    naming_standards,
    updated_at,
    updated_by::text,
    llm_config,
    incident_policy
"""

_FIND_BY_WORKSPACE_TENANT_SQL = f"""
    SELECT {_SELECT_SETTINGS_COLS}
    FROM control.workspace_settings
    WHERE workspace_id = CAST(:workspace_id AS UUID)
      AND tenant_id    = CAST(:tenant_id    AS UUID)
"""

_FIND_BY_WORKSPACE_ANY_TENANT_SQL = f"""
    SELECT {_SELECT_SETTINGS_COLS}
    FROM control.workspace_settings
    WHERE workspace_id = CAST(:workspace_id AS UUID)
"""

_FIND_BY_WORKSPACE_FOR_UPDATE_TENANT_SQL = f"""
    SELECT {_SELECT_SETTINGS_COLS}
    FROM control.workspace_settings
    WHERE workspace_id = CAST(:workspace_id AS UUID)
      AND tenant_id    = CAST(:tenant_id    AS UUID)
    FOR UPDATE
"""

_INSERT_DEFAULT_SETTINGS_SQL = f"""
    INSERT INTO control.workspace_settings (
        workspace_id,
        tenant_id,
        default_timezone,
        issue_grouping_policy,
        updated_at,
        updated_by
    ) VALUES (
        CAST(:workspace_id AS UUID),
        CAST(:tenant_id    AS UUID),
        :default_timezone,
        'one_per_execution',
        :updated_at,
        NULL
    )
    ON CONFLICT (workspace_id) DO NOTHING
    RETURNING {_SELECT_SETTINGS_COLS}
"""

# UPDATE is deliberately not built as a single parameterised string because only
# the columns present in the WorkspaceSettingsUpdate are written. The column set
# is determined at runtime from the update object. All values remain parameterised.


# ─────────────────────────────────────────────────────────────────────────────
# JSONB helpers (private)
# ─────────────────────────────────────────────────────────────────────────────


def _serialize_jsonb(value: object) -> str | None:
    """Serialise a policy object or dict to a JSON string for PostgreSQL binding."""
    if value is None:
        return None
    if isinstance(value, dict):
        return json.dumps(value)
    # Dataclass — convert to dict first
    import dataclasses

    return json.dumps(dataclasses.asdict(value))


def _deserialize_severity(raw) -> SeverityPolicy | None:
    if raw is None:
        return None
    d = raw if isinstance(raw, dict) else json.loads(raw)
    return SeverityPolicy(
        critical_label=d["critical_label"],
        major_label=d["major_label"],
        minor_label=d["minor_label"],
        informational_label=d["informational_label"],
    )


def _deserialize_sla(raw) -> SLAPolicy | None:
    if raw is None:
        return None
    d = raw if isinstance(raw, dict) else json.loads(raw)
    return SLAPolicy(
        critical_hours=d["critical_hours"],
        major_hours=d["major_hours"],
        minor_hours=d["minor_hours"],
        informational_hours=d.get("informational_hours"),
    )


def _deserialize_naming_constraint(d: dict) -> NamingConstraint:
    return NamingConstraint(
        required_prefix=d.get("required_prefix"),
        required_suffix=d.get("required_suffix"),
        pattern=d.get("pattern"),
        max_length=d.get("max_length"),
        allow_special_characters=d.get("allow_special_characters"),
    )


def _deserialize_naming_standards(raw) -> NamingStandards | None:
    if raw is None:
        return None
    d = raw if isinstance(raw, dict) else json.loads(raw)
    return NamingStandards(
        datasets=_deserialize_naming_constraint(d.get("datasets", {})),
        rules=_deserialize_naming_constraint(d.get("rules", {})),
    )


def _deserialize_llm_config(raw) -> LLMConfig | None:
    if raw is None:
        return None
    d = raw if isinstance(raw, dict) else json.loads(raw)
    return LLMConfig(
        provider=d.get("provider", "openai"),
        api_key_encrypted=d.get("api_key_encrypted", ""),
        model=d.get("model", "gpt-4o"),
        temperature=d.get("temperature", 0.0),
        max_tokens=d.get("max_tokens", 4096),
    )


def _deserialize_incident_policy(raw) -> IncidentPolicy | None:
    if raw is None:
        return None
    d = raw if isinstance(raw, dict) else json.loads(raw)
    auto_owner = d.get("auto_owner_user_id")
    return IncidentPolicy(
        enabled=bool(d.get("enabled", False)),
        min_severity=d.get("min_severity", "critical"),
        recurrence_threshold=int(d.get("recurrence_threshold", 1)),
        auto_priority=d.get("auto_priority"),
        auto_owner_user_id=uuid.UUID(auto_owner) if auto_owner else None,
    )


def _row_to_workspace_settings(row) -> WorkspaceSettings:
    """Map a DB row (tuple positional or mapping) to a WorkspaceSettings instance."""
    (
        workspace_id_str,
        tenant_id_str,
        default_timezone,
        severity_raw,
        sla_raw,
        issue_grouping_policy,
        naming_raw,
        updated_at,
        updated_by_str,
        llm_config_raw,
        incident_policy_raw,
    ) = row

    return WorkspaceSettings(
        workspace_id=uuid.UUID(workspace_id_str),
        tenant_id=uuid.UUID(tenant_id_str),
        default_timezone=default_timezone,
        issue_grouping_policy=issue_grouping_policy,
        updated_at=updated_at,
        updated_by=uuid.UUID(updated_by_str) if updated_by_str else None,
        severity_policy=_deserialize_severity(severity_raw),
        sla_policy=_deserialize_sla(sla_raw),
        naming_standards=_deserialize_naming_standards(naming_raw),
        llm_config=_deserialize_llm_config(llm_config_raw),
        incident_policy=_deserialize_incident_policy(incident_policy_raw),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public repository functions
# ─────────────────────────────────────────────────────────────────────────────


def find_by_workspace_id(
    db: Session,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
) -> WorkspaceSettings | None:
    """Return the settings row for a workspace, or None if not found.

    When ``tenant_id`` is None (Platform Operator), the tenant filter is
    omitted and the row is returned regardless of its tenant.
    When ``tenant_id`` is provided, cross-tenant isolation is enforced.
    """
    if tenant_id is None:
        sql = _FIND_BY_WORKSPACE_ANY_TENANT_SQL
        params = {"workspace_id": str(workspace_id)}
    else:
        sql = _FIND_BY_WORKSPACE_TENANT_SQL
        params = {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)}

    result = db.execute(text(sql), params)
    row = result.fetchone()
    return _row_to_workspace_settings(row) if row is not None else None


def create_default(
    db: Session,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    initial_timezone: str,
) -> WorkspaceSettings:
    """Create a default settings row for a workspace that has none.

    Uses ``ON CONFLICT DO NOTHING`` so a concurrent trigger-created row
    does not cause an error.  If the conflict fires and the row was not
    inserted, the function reads and returns the existing row.
    """
    now = datetime.now(UTC)
    result = db.execute(
        text(_INSERT_DEFAULT_SETTINGS_SQL),
        {
            "workspace_id": str(workspace_id),
            "tenant_id": str(tenant_id),
            "default_timezone": initial_timezone,
            "updated_at": now,
        },
    )
    row = result.fetchone()
    if row is not None:
        return _row_to_workspace_settings(row)
    # ON CONFLICT fired — row already existed; read it back
    existing = find_by_workspace_id(db, workspace_id, tenant_id)
    if existing is None:
        raise SettingsNotFoundError(
            f"Workspace settings for {workspace_id} not found after upsert."
        )
    return existing


def update_settings(
    db: Session,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID,
    update: WorkspaceSettingsUpdate,
    actor_id: uuid.UUID,
    now: datetime,
) -> WorkspaceSettings:
    """Apply a validated partial update to a workspace's settings row.

    Acquires a ``SELECT ... FOR UPDATE`` lock on the settings row before
    writing to prevent concurrent PATCH conflicts (TDD §5.3).

    Raises ``SettingsNotFoundError`` if no settings row exists for the lock
    query — the service layer must ensure the row exists before calling this.

    Only columns whose corresponding ``WorkspaceSettingsUpdate`` field is not
    None are included in the UPDATE SET clause.
    """
    # Lock the row
    result = db.execute(
        text(_FIND_BY_WORKSPACE_FOR_UPDATE_TENANT_SQL),
        {"workspace_id": str(workspace_id), "tenant_id": str(tenant_id)},
    )
    locked_row = result.fetchone()
    if locked_row is None:
        raise SettingsNotFoundError(
            f"Workspace settings for {workspace_id} not found during update lock."
        )

    # Build the SET clause from non-None update fields
    set_clauses = ["updated_at = :updated_at", "updated_by = CAST(:updated_by AS UUID)"]
    params: dict = {
        "workspace_id": str(workspace_id),
        "tenant_id": str(tenant_id),
        "updated_at": now,
        "updated_by": str(actor_id),
    }

    if update.default_timezone is not None:
        set_clauses.append("default_timezone = :default_timezone")
        params["default_timezone"] = update.default_timezone

    if update.severity_policy is not None:
        set_clauses.append("severity_policy = CAST(:severity_policy AS JSONB)")
        params["severity_policy"] = _serialize_jsonb(update.severity_policy)

    if update.sla_policy is not None:
        set_clauses.append("sla_policy = CAST(:sla_policy AS JSONB)")
        params["sla_policy"] = _serialize_jsonb(update.sla_policy)

    if update.issue_grouping_policy is not None:
        set_clauses.append("issue_grouping_policy = :issue_grouping_policy")
        params["issue_grouping_policy"] = update.issue_grouping_policy

    if update.naming_standards is not None:
        set_clauses.append("naming_standards = CAST(:naming_standards AS JSONB)")
        params["naming_standards"] = _serialize_jsonb(update.naming_standards)

    if update.llm_config is not None:
        set_clauses.append("llm_config = CAST(:llm_config AS JSONB)")
        params["llm_config"] = _serialize_jsonb(update.llm_config)

    if update.incident_policy is not None:
        ip = update.incident_policy
        set_clauses.append("incident_policy = CAST(:incident_policy AS JSONB)")
        params["incident_policy"] = json.dumps(
            {
                "enabled": ip.enabled,
                "min_severity": ip.min_severity,
                "recurrence_threshold": ip.recurrence_threshold,
                "auto_priority": ip.auto_priority,
                "auto_owner_user_id": str(ip.auto_owner_user_id) if ip.auto_owner_user_id else None,
            }
        )

    update_sql = f"""
        UPDATE control.workspace_settings
        SET {", ".join(set_clauses)}
        WHERE workspace_id = CAST(:workspace_id AS UUID)
          AND tenant_id    = CAST(:tenant_id    AS UUID)
        RETURNING {_SELECT_SETTINGS_COLS}
    """

    result = db.execute(text(update_sql), params)
    row = result.fetchone()
    if row is None:
        raise SettingsNotFoundError(
            f"Workspace settings for {workspace_id} not found after update."
        )
    return _row_to_workspace_settings(row)
