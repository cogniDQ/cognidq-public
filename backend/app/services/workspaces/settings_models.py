"""
F003 — Workspace Settings domain models
=========================================

Defines pure Python dataclasses for the five policy domains stored in
``control.workspace_settings``.  No database or HTTP dependencies exist here;
every layer from repository to API uses these objects.

Design notes
------------
* All models use ``@dataclass(slots=True, frozen=True)`` (Python ≥ 3.10) for
  memory efficiency and immutability enforcement.
* ``WorkspaceSettings.with_defaults()`` returns a NEW instance (since the
  dataclass is frozen) with any NULL policy fields replaced by the module-level
  built-in default constants.
* ``WorkspaceSettingsUpdate`` is intentionally NOT frozen — it is populated
  field-by-field from the validated PATCH request body.
* All Optional JSONB fields are typed as ``Optional[<Policy>]``; ``None``
  means "the database stores NULL — use built-in defaults on read".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.services.incidents.auto_incident_models import (
    SHIPPING_DEFAULT_INCIDENT_POLICY,
    IncidentPolicy,
)

# ─────────────────────────────────────────────────────────────────────────────
# Policy sub-models
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class LLMConfig:
    """LLM provider configuration for workspace-level AI features."""

    provider: str  # "openai", "azure_openai", "anthropic"
    api_key_encrypted: str  # Fernet-encrypted API key (stored as base64 string)
    model: str  # e.g. "gpt-4o", "gpt-3.5-turbo"
    temperature: float  # 0.0 – 2.0
    max_tokens: int  # 1 – 16000


@dataclass(slots=True, frozen=True)
class SeverityPolicy:
    """Labels for the four issue severity levels (TDD §3.3)."""

    critical_label: str
    major_label: str
    minor_label: str
    informational_label: str


@dataclass(slots=True, frozen=True)
class SLAPolicy:
    """SLA resolution targets in hours (TDD §3.3).

    ``informational_hours`` may be None when no SLA is defined for informational
    issues.
    """

    critical_hours: int
    major_hours: int
    minor_hours: int
    informational_hours: int | None


@dataclass(slots=True, frozen=True)
class NamingConstraint:
    """Naming constraints for a single domain (datasets or rules) (TDD §3.3).

    All fields are optional constraints; ``None`` means no constraint is
    applied for that field.  An empty ``NamingConstraint`` (all fields None)
    is valid and means "no constraints apply for this domain".
    """

    required_prefix: str | None
    required_suffix: str | None
    pattern: str | None
    max_length: int | None
    allow_special_characters: bool | None


@dataclass(slots=True, frozen=True)
class NamingStandards:
    """Naming standard constraints for the two data domains (TDD §3.3)."""

    datasets: NamingConstraint
    rules: NamingConstraint


# ─────────────────────────────────────────────────────────────────────────────
# Built-in default constants (TDD §3.4)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SEVERITY_POLICY = SeverityPolicy(
    critical_label="Critical",
    major_label="Major",
    minor_label="Minor",
    informational_label="Informational",
)

DEFAULT_SLA_POLICY = SLAPolicy(
    critical_hours=4,
    major_hours=24,
    minor_hours=72,
    informational_hours=None,
)

_EMPTY_NAMING_CONSTRAINT = NamingConstraint(
    required_prefix=None,
    required_suffix=None,
    pattern=None,
    max_length=None,
    allow_special_characters=None,
)

DEFAULT_NAMING_STANDARDS = NamingStandards(
    datasets=_EMPTY_NAMING_CONSTRAINT,
    rules=_EMPTY_NAMING_CONSTRAINT,
)


# ─────────────────────────────────────────────────────────────────────────────
# Top-level settings domain model
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True, frozen=True)
class WorkspaceSettings:
    """
    Domain model for a row in ``control.workspace_settings``.

    ``severity_policy``, ``sla_policy``, and ``naming_standards`` are ``None``
    when the database stores NULL.  Call ``with_defaults()`` to obtain a fully
    populated instance suitable for API serialisation.
    """

    workspace_id: UUID
    tenant_id: UUID
    default_timezone: str
    issue_grouping_policy: str
    updated_at: datetime
    # NULL in DB → use built-in defaults in service layer
    severity_policy: SeverityPolicy | None
    sla_policy: SLAPolicy | None
    naming_standards: NamingStandards | None
    # NULL when the row was created by the system trigger (no human actor)
    updated_by: UUID | None
    # F039 — Optional incident auto-creation policy (None → disabled default)
    incident_policy: IncidentPolicy | None = None
    # Workspace-level LLM provider configuration (None → use global env config)
    llm_config: LLMConfig | None = None

    def with_defaults(self) -> WorkspaceSettings:
        """Return a new instance with NULL policy fields replaced by built-in defaults.

        This method never mutates ``self`` (the dataclass is frozen). Any field
        that is already set (non-None) is preserved unchanged.
        """
        return WorkspaceSettings(
            workspace_id=self.workspace_id,
            tenant_id=self.tenant_id,
            default_timezone=self.default_timezone,
            issue_grouping_policy=self.issue_grouping_policy,
            updated_at=self.updated_at,
            updated_by=self.updated_by,
            severity_policy=(
                self.severity_policy
                if self.severity_policy is not None
                else DEFAULT_SEVERITY_POLICY
            ),
            sla_policy=(self.sla_policy if self.sla_policy is not None else DEFAULT_SLA_POLICY),
            naming_standards=(
                self.naming_standards
                if self.naming_standards is not None
                else DEFAULT_NAMING_STANDARDS
            ),
            incident_policy=(
                self.incident_policy
                if self.incident_policy is not None
                else SHIPPING_DEFAULT_INCIDENT_POLICY
            ),
            llm_config=self.llm_config,  # None means "use global env config"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Partial update carrier (mutable — populated from PATCH body)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class WorkspaceSettingsUpdate:
    """Carries the validated changes from a PATCH /settings request.

    All fields are Optional; only those present in the request body will be
    set (not None) by the service layer before passing to the repository.
    The repository only updates the columns whose corresponding field is not
    None.
    """

    default_timezone: str | None = None
    severity_policy: SeverityPolicy | None = None
    sla_policy: SLAPolicy | None = None
    issue_grouping_policy: str | None = None
    naming_standards: NamingStandards | None = None
    incident_policy: IncidentPolicy | None = None
    llm_config: LLMConfig | None = None
