"""Consolidate the demo environment into the RBAC QA workspace.

Revision ID: 0005_consolidate_into_rbac_qa
Revises: 0004_remove_extra_workspaces
Create Date: 2026-10-16

0004 trimmed seed data down to two workspaces: the dedicated "Demo
Workspace" (steward@example.com, tenant "Demo Tenant") used for the
product demo, and the "RBAC QA Workspace" (tenant "RBAC QA") used only
by the per-role QA login fixtures. Two separate demo-ish workspaces is
one too many for a fresh deploy to explain.

Keep a single workspace going forward: delete the dedicated Demo
Tenant/Workspace (and the demo content a prior `seed_demo_data.py` run
may have added to it — connection, credentials, datasets, rules, flow,
execution), and rename the RBAC QA Workspace to "Demo Workspace" so the
QA role fixtures and the pre-loaded demo content now live in the same
place. ``scripts/seed_demo_data.py`` is updated separately to seed its
content into the RBAC QA tenant/workspace instead.

The RBAC QA tenant itself keeps its name/slug ("RBAC QA" / `rbac-qa`)
and all eight per-role login fixtures — only the workspace is renamed.

Deletes in the same FK-safe order 0004 used, extended for the extra
demo content (connection credentials, glossary terms, tenant audit log
rows) this workspace may carry that the orphaned workspaces in 0004
never had:
  support access grants → tenant/workspace audit logs/legacy roles →
  glossary terms → datasets (cascades dataset_fields) → data source
  credentials → data sources (cascades workspace_connection_assignments)
  → workspace (cascades flows/flow_executions/rules/issues/dashboards/
    teams/role assignments/settings) → tenant → the steward user.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_consolidate_into_rbac_qa"
down_revision: Union[str, None] = "0004_remove_extra_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_DEMO_TENANT_ID = "10000000-1000-4000-8000-000000000001"
_OLD_DEMO_WORKSPACE_ID = "20000000-2000-4000-8000-000000000002"

_RBAC_QA_WORKSPACE_ID = "44444444-4444-4444-8444-444444444444"


def upgrade() -> None:
    op.execute(
        f"""
        DELETE FROM control.support_access_grants WHERE tenant_id = '{_OLD_DEMO_TENANT_ID}';
        DELETE FROM control.tenant_audit_logs WHERE tenant_id = '{_OLD_DEMO_TENANT_ID}';
        DELETE FROM control.workspace_audit_logs
            WHERE tenant_id = '{_OLD_DEMO_TENANT_ID}' OR workspace_id = '{_OLD_DEMO_WORKSPACE_ID}';
        DELETE FROM roles WHERE workspace_id = '{_OLD_DEMO_WORKSPACE_ID}';
        DELETE FROM control.metadata_term_index WHERE workspace_id = '{_OLD_DEMO_WORKSPACE_ID}';
        DELETE FROM control.datasets WHERE workspace_id = '{_OLD_DEMO_WORKSPACE_ID}';
        DELETE FROM control.data_source_credentials
            WHERE data_source_id IN (
                SELECT data_source_id FROM control.data_sources
                WHERE workspace_id = '{_OLD_DEMO_WORKSPACE_ID}' OR tenant_id = '{_OLD_DEMO_TENANT_ID}'
            );
        DELETE FROM control.data_sources
            WHERE workspace_id = '{_OLD_DEMO_WORKSPACE_ID}' OR tenant_id = '{_OLD_DEMO_TENANT_ID}';
        DELETE FROM control.workspaces WHERE workspace_id = '{_OLD_DEMO_WORKSPACE_ID}';
        DELETE FROM control.tenants WHERE tenant_id = '{_OLD_DEMO_TENANT_ID}';
        DELETE FROM users WHERE email = 'steward@example.com';

        UPDATE control.workspaces
            SET workspace_name = 'Demo Workspace',
                workspace_slug = 'demo-workspace'
            WHERE workspace_id = '{_RBAC_QA_WORKSPACE_ID}';
        """
    )


def downgrade() -> None:
    raise NotImplementedError(
        "This data cleanup is not reversible. Restore the database from a backup instead."
    )
