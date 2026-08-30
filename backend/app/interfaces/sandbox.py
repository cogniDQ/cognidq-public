"""
F134 — Demo Sandbox Provisioning
Protocol interfaces used as dependency-injection contracts.

These are pure Python protocols (structural subtyping). They carry no business
logic; concrete implementations live in dedicated modules.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class SandboxFeatureGateProtocol(Protocol):
    """
    Contract for the feature-gate dependency injected into sandbox-user routes.

    Returns the set of feature flags that are active for a given sandbox tenant,
    and exposes helper predicates for the most-common gate checks.
    """

    def get_flags(self, tenant_id: UUID) -> dict[str, Any]:
        """Return the full flags dict for the given tenant's access profile."""
        ...

    def is_destructive_operations_disabled(self, tenant_id: UUID) -> bool:
        """True when sandbox policy disables delete/truncate operations."""
        ...

    def is_external_integrations_disabled(self, tenant_id: UUID) -> bool:
        """True when sandbox policy disables external webhook/ticketing integrations."""
        ...

    def is_platform_admin_hidden(self, tenant_id: UUID) -> bool:
        """True when platform-admin UI elements should be hidden for the tenant."""
        ...


@runtime_checkable
class TemplateSeederProtocol(Protocol):
    """
    Contract for demo-template content seeders.

    Each seeder is responsible for creating the synthetic content (datasets,
    rules, flows, issues, glossary terms, dashboard) in the sandbox workspace.
    """

    #: The canonical template ID this seeder handles (e.g. ``"general_dq"``).
    template_id: str

    def seed(self, tenant_id: UUID, workspace_id: UUID) -> None:
        """
        Populate the given sandbox workspace with template content.

        Must be idempotent: safe to call twice on the same workspace.
        Raises ``SeedingError`` on unrecoverable failure.
        """
        ...
