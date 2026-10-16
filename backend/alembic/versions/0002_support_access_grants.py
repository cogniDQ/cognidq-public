"""Add control.support_access_grants — ephemeral tenant-granted platform_admin access.

Revision ID: 0002_support_access_grants
Revises: 0001_baseline
Create Date: 2026-10-16

A tenant_admin grants time-limited, audited access to platform_admin for
their own tenant (or a single workspace within it). platform_admin has no
standing cross-tenant access to workspace/tenant content without one of
these grants being active.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_support_access_grants"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS control.support_access_grants (
            id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
            tenant_id           UUID        NOT NULL,
            workspace_id        UUID        NULL,
            granted_by_user_id  UUID        NOT NULL,
            reason              VARCHAR(500) NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at          TIMESTAMPTZ NOT NULL,
            revoked_at          TIMESTAMPTZ NULL,
            revoked_by_user_id  UUID        NULL,

            CONSTRAINT pk_support_access_grants PRIMARY KEY (id),
            CONSTRAINT fk_support_access_grants_tenant
                FOREIGN KEY (tenant_id) REFERENCES control.tenants (tenant_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_support_access_grants_workspace
                FOREIGN KEY (workspace_id) REFERENCES control.workspaces (workspace_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_support_access_grants_granted_by
                FOREIGN KEY (granted_by_user_id) REFERENCES users (id),
            CONSTRAINT fk_support_access_grants_revoked_by
                FOREIGN KEY (revoked_by_user_id) REFERENCES users (id),
            CONSTRAINT chk_support_access_grants_expiry
                CHECK (expires_at > created_at)
        );

        CREATE INDEX IF NOT EXISTS idx_support_access_grants_tenant_expiry
            ON control.support_access_grants (tenant_id, expires_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control.support_access_grants;")
