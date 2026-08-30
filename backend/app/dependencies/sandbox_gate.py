"""
F134 P08 — Sandbox Feature Gate

Provides `SandboxContext` (per-request cached dataclass) and the
`get_sandbox_context` FastAPI dependency that resolves it.

Usage
-----
    @router.delete("/datasets/{id}")
    async def delete_dataset(
        sandbox: SandboxContext = Depends(get_sandbox_context),
        ...
    ):
        sandbox.require_flag_false("destructive_operations_disabled")
        ...

Security constraints
--------------------
- The gate CANNOT be bypassed via headers or query parameters.
- `platform_admin` actors always receive a no-restriction SandboxContext.
- The sandbox lookup is cached on ``request.state.sandbox_context`` for the
  duration of the request (one DB read per request maximum).
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.v1.dependencies.tenant_auth import (
    ActorContext,
    TenantAPIError,
    get_actor_context,
)
from app.models.database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Onboarding step IDs (fixed set per TDD §4.14)
# ---------------------------------------------------------------------------

ONBOARDING_STEPS = (
    "view_dataset",
    "view_rule",
    "run_check",
    "open_issue",
    "view_dashboard",
    "create_rule",
)

# ---------------------------------------------------------------------------
# SQL: resolve sandbox context for an actor via workspace_role_assignments
# ---------------------------------------------------------------------------

_RESOLVE_SQL = text("""
    SELECT
        se.id::text           AS sandbox_id,
        se.status             AS sandbox_status,
        se.expires_at,
        se.tenant_id::text    AS tenant_id,
        se.workspace_id::text AS workspace_id,
        ap.flags
    FROM control.workspace_role_assignments wra
    JOIN control.workspaces w
        ON w.workspace_id = wra.workspace_id
    JOIN control.tenants t
        ON t.tenant_id = w.tenant_id
    JOIN control.sandbox_environments se
        ON se.tenant_id = t.tenant_id
    LEFT JOIN control.access_profiles ap
        ON ap.id = se.access_profile_id
    WHERE wra.user_id  = CAST(:user_id AS UUID)
      AND t.tenant_type = 'sandbox'
      AND se.status NOT IN ('deleted', 'archived')
    LIMIT 1
""")

# ---------------------------------------------------------------------------
# SandboxContext
# ---------------------------------------------------------------------------


@dataclass
class SandboxContext:
    """Holds the resolved sandbox feature flags for the current request.

    ``is_sandbox=False`` is returned for platform_admin actors and for any
    actor whose tenant is not a sandbox. No gate checks fire in that case.
    """

    is_sandbox: bool
    sandbox_id: UUID | None = None
    tenant_id: UUID | None = None
    workspace_id: UUID | None = None
    sandbox_status: str | None = None
    expires_at: datetime | None = None
    flags: dict[str, Any] = field(default_factory=dict)

    # ── Feature flag enforcement ──────────────────────────────────────────

    def require_flag_false(self, flag_name: str) -> None:
        """Raise HTTP 403 if *flag_name* is set in the sandbox access profile.

        Has no effect when ``is_sandbox=False`` (non-sandbox actors).

        Parameters
        ----------
        flag_name:
            One of ``"destructive_operations_disabled"``,
            ``"external_integrations_disabled"``, or
            ``"platform_admin_hidden"``.
        """
        if self.is_sandbox and self.flags.get(flag_name):
            raise TenantAPIError(
                status_code=403,
                code="sandbox_forbidden",
                message="Operation not available in the demo sandbox.",
                fields=[{"reason": flag_name}],
            )

    # ── Derived helpers ───────────────────────────────────────────────────

    @property
    def remaining_days(self) -> int:
        """Calendar days until sandbox expiry (0 if already expired)."""
        if not self.expires_at:
            return 0
        now = datetime.now(UTC)
        exp = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=UTC)
        total_seconds = (exp - now).total_seconds()
        return max(0, math.ceil(total_seconds / 86400))

    @property
    def is_expired(self) -> bool:
        return self.sandbox_status in ("expired", "suspended")


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def _load_sandbox_context(db: Session, actor_id: UUID) -> SandboxContext:
    """Run the DB lookup and return a SandboxContext.

    Returns ``SandboxContext(is_sandbox=False)`` when the actor has no
    associated sandbox environment.
    """
    row = db.execute(_RESOLVE_SQL, {"user_id": str(actor_id)}).fetchone()
    if row is None:
        return SandboxContext(is_sandbox=False)

    mapping = dict(row._mapping)
    raw_flags = mapping.get("flags") or {}
    # SQLAlchemy may return JSONB as dict or as str depending on driver
    if isinstance(raw_flags, str):
        try:
            raw_flags = json.loads(raw_flags)
        except (ValueError, TypeError):
            raw_flags = {}

    return SandboxContext(
        is_sandbox=True,
        sandbox_id=UUID(mapping["sandbox_id"]),
        tenant_id=UUID(mapping["tenant_id"]),
        workspace_id=UUID(mapping["workspace_id"]),
        sandbox_status=mapping.get("sandbox_status"),
        expires_at=mapping.get("expires_at"),
        flags=raw_flags,
    )


async def get_sandbox_context(
    request: Request,
    db: Session = Depends(get_db),
    actor: ActorContext = Depends(get_actor_context),
) -> SandboxContext:
    """FastAPI dependency — resolves the sandbox context for the current actor.

    Resolution rules:
    - ``platform_admin`` → always returns ``SandboxContext(is_sandbox=False)``.
    - All other roles → looks up sandbox_environments via workspace_role_assignments.
    - Result is cached on ``request.state.sandbox_context`` for re-use within
      the same request lifecycle (avoids multiple DB round-trips for chained
      depends).
    """
    if actor.actor_role == "platform_admin":
        return SandboxContext(is_sandbox=False)

    cached: SandboxContext | None = getattr(request.state, "sandbox_context", None)
    if cached is not None:
        return cached

    ctx = _load_sandbox_context(db, actor.actor_id)
    request.state.sandbox_context = ctx
    return ctx
