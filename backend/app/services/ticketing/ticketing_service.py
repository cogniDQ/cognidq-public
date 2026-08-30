"""
F060 — External Ticketing Integration Hooks — Service Layer
=============================================================

Provides two services:
  - TicketingConfigService  — CRUD for workspace-level ticketing integration configs
  - ExternalTicketService   — Link/unlink external tickets on issues and incidents
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.incident import Incident
from app.models.issue import Issue
from app.models.ticketing import TicketingIntegrationConfig

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TicketingConfigNotFoundError(Exception):
    """Raised when a ticketing config is not found."""


class TicketingConfigValidationError(Exception):
    """Raised when a ticketing config has invalid fields."""


class TicketingConfigConflictError(Exception):
    """Raised when a workspace already has a config for a given system_name."""


# ---------------------------------------------------------------------------
# Valid system names
# ---------------------------------------------------------------------------

VALID_SYSTEM_NAMES = frozenset({"jira", "linear", "github", "servicenow", "pagerduty", "custom"})


# ---------------------------------------------------------------------------
# TicketingConfigService
# ---------------------------------------------------------------------------


class TicketingConfigService:
    """CRUD operations for ticketing integration configs."""

    def create_config(
        self,
        db: Session,
        *,
        workspace_id: UUID,
        tenant_id: UUID,
        actor_id: UUID,
        system_name: str,
        display_name: str,
        base_url: str | None = None,
        project_key: str | None = None,
        default_issue_type: str | None = None,
        enabled: bool = True,
        config_json: dict | None = None,
    ) -> TicketingIntegrationConfig:
        if system_name not in VALID_SYSTEM_NAMES:
            raise TicketingConfigValidationError(
                f"Invalid system_name '{system_name}'. Must be one of: {sorted(VALID_SYSTEM_NAMES)}"
            )
        if not display_name or not display_name.strip():
            raise TicketingConfigValidationError("display_name must not be empty")

        # Check uniqueness: one config per workspace per system_name
        existing = self.get_config_by_system(db, workspace_id, system_name)
        if existing is not None:
            raise TicketingConfigConflictError(
                f"Workspace already has a ticketing config for system '{system_name}'"
            )

        cfg = TicketingIntegrationConfig(
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            system_name=system_name,
            display_name=display_name.strip(),
            base_url=base_url,
            project_key=project_key,
            default_issue_type=default_issue_type,
            enabled=enabled,
            config_json=config_json,
            created_by=actor_id,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return cfg

    def list_configs(self, db: Session, workspace_id: UUID) -> list[TicketingIntegrationConfig]:
        result = db.execute(
            select(TicketingIntegrationConfig)
            .where(TicketingIntegrationConfig.workspace_id == workspace_id)
            .order_by(TicketingIntegrationConfig.created_at)
        )
        return list(result.scalars().all())

    def get_config(
        self, db: Session, config_id: UUID, workspace_id: UUID
    ) -> TicketingIntegrationConfig | None:
        result = db.execute(
            select(TicketingIntegrationConfig).where(
                TicketingIntegrationConfig.id == config_id,
                TicketingIntegrationConfig.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    def get_config_by_system(
        self, db: Session, workspace_id: UUID, system_name: str
    ) -> TicketingIntegrationConfig | None:
        result = db.execute(
            select(TicketingIntegrationConfig).where(
                TicketingIntegrationConfig.workspace_id == workspace_id,
                TicketingIntegrationConfig.system_name == system_name,
            )
        )
        return result.scalar_one_or_none()

    def update_config(
        self,
        db: Session,
        *,
        config_id: UUID,
        workspace_id: UUID,
        display_name: str | None = None,
        base_url: str | None = None,
        project_key: str | None = None,
        default_issue_type: str | None = None,
        enabled: bool | None = None,
        config_json: dict | None = None,
    ) -> TicketingIntegrationConfig:
        cfg = self.get_config(db, config_id, workspace_id)
        if cfg is None:
            raise TicketingConfigNotFoundError(f"Config {config_id} not found")

        if display_name is not None:
            if not display_name.strip():
                raise TicketingConfigValidationError("display_name must not be empty")
            cfg.display_name = display_name.strip()
        if base_url is not None:
            cfg.base_url = base_url
        if project_key is not None:
            cfg.project_key = project_key
        if default_issue_type is not None:
            cfg.default_issue_type = default_issue_type
        if enabled is not None:
            cfg.enabled = enabled
        if config_json is not None:
            cfg.config_json = config_json

        db.commit()
        db.refresh(cfg)
        return cfg

    def delete_config(self, db: Session, config_id: UUID, workspace_id: UUID) -> bool:
        cfg = self.get_config(db, config_id, workspace_id)
        if cfg is None:
            return False
        db.delete(cfg)
        db.commit()
        return True


# ---------------------------------------------------------------------------
# ExternalTicketService
# ---------------------------------------------------------------------------


class ExternalTicketService:
    """Link and unlink external ticket references on issues and incidents."""

    def link_issue_ticket(
        self,
        db: Session,
        *,
        issue_id: UUID,
        workspace_id: UUID,
        external_ticket_id: str,
        external_ticket_url: str | None,
        external_system: str,
    ) -> Issue:
        """Attach external ticket reference to an issue."""
        result = db.execute(
            select(Issue).where(
                Issue.id == issue_id,
                Issue.workspace_id == workspace_id,
            )
        )
        issue = result.scalar_one_or_none()
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

        issue.external_ticket_id = external_ticket_id
        issue.external_ticket_url = external_ticket_url
        issue.external_system = external_system
        db.commit()
        db.refresh(issue)
        return issue

    def unlink_issue_ticket(self, db: Session, *, issue_id: UUID, workspace_id: UUID) -> Issue:
        """Remove external ticket reference from an issue."""
        result = db.execute(
            select(Issue).where(
                Issue.id == issue_id,
                Issue.workspace_id == workspace_id,
            )
        )
        issue = result.scalar_one_or_none()
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")

        issue.external_ticket_id = None
        issue.external_ticket_url = None
        issue.external_system = None
        db.commit()
        db.refresh(issue)
        return issue

    def link_incident_ticket(
        self,
        db: Session,
        *,
        incident_id: UUID,
        workspace_id: UUID,
        external_ticket_id: str,
        external_ticket_url: str | None,
        external_system: str,
    ) -> Incident:
        """Attach external ticket reference to an incident."""
        result = db.execute(
            select(Incident).where(
                Incident.id == incident_id,
                Incident.workspace_id == workspace_id,
            )
        )
        incident = result.scalar_one_or_none()
        if incident is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

        incident.external_ticket_id = external_ticket_id
        incident.external_ticket_url = external_ticket_url
        incident.external_system = external_system
        db.commit()
        db.refresh(incident)
        return incident

    def unlink_incident_ticket(
        self, db: Session, *, incident_id: UUID, workspace_id: UUID
    ) -> Incident:
        """Remove external ticket reference from an incident."""
        result = db.execute(
            select(Incident).where(
                Incident.id == incident_id,
                Incident.workspace_id == workspace_id,
            )
        )
        incident = result.scalar_one_or_none()
        if incident is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

        incident.external_ticket_id = None
        incident.external_ticket_url = None
        incident.external_system = None
        db.commit()
        db.refresh(incident)
        return incident
