"""Remove all workspaces except the Demo Workspace.

Revision ID: 0004_remove_extra_workspaces
Revises: 0003_seed_default_tenant_admin
Create Date: 2026-10-16

The seed data accumulated four workspaces beyond the one meant to carry the
product demo: the orphaned "Default Workspace" (only ever reachable via
platform_admin's old cross-tenant bypass, now removed), and two ad-hoc
"corp"/"test" workspaces created by admin@example.com while testing the UI.
Keep only "Demo Workspace" (20000000-2000-4000-8000-000000000002, owned by
steward@example.com) so a fresh deploy has one clean, unambiguous demo
environment instead of several empty/orphaned ones.

Deletes in FK-safe order: audit logs and legacy roles rows (NO ACTION/
RESTRICT on workspace_id) → datasets (RESTRICT on data_source_id) →
data_sources → workspaces (cascades flows/rules/issues/teams/role
assignments/settings/etc.) → the Default Tenant → the tenant_admin seeded
for it in 0003.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_remove_extra_workspaces"
down_revision: Union[str, None] = "0003_seed_default_tenant_admin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_IDS = (
    "00000000-0000-0000-0000-000000000020",  # Default Workspace (orphaned)
    "d15991c1-5056-4d54-9bb9-21dc3cfe7d55",  # "corp" (ad-hoc test workspace)
    "42f3a2b8-6722-420a-bd1d-2ec4f689d8fd",  # "test" (ad-hoc test workspace)
)
_DEFAULT_TENANT_ID = "8062ed84-5660-4470-833c-f748ed0a7481"


def upgrade() -> None:
    ws_list = ", ".join(f"'{w}'" for w in _WORKSPACE_IDS)
    op.execute(
        f"""
        DELETE FROM control.support_access_grants WHERE tenant_id = '{_DEFAULT_TENANT_ID}';
        DELETE FROM control.workspace_audit_logs
            WHERE tenant_id = '{_DEFAULT_TENANT_ID}' OR workspace_id IN ({ws_list});
        DELETE FROM roles WHERE workspace_id IN ({ws_list});
        DELETE FROM control.datasets WHERE workspace_id IN ({ws_list});
        DELETE FROM control.data_sources
            WHERE workspace_id IN ({ws_list}) OR tenant_id = '{_DEFAULT_TENANT_ID}';
        DELETE FROM control.workspaces WHERE workspace_id IN ({ws_list});
        DELETE FROM control.tenants WHERE tenant_id = '{_DEFAULT_TENANT_ID}';
        DELETE FROM users WHERE email = 'tenant-admin@example.com';
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "This data cleanup is not reversible. Restore the database from a backup instead."
    )
