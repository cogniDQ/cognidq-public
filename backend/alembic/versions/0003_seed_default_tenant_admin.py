"""Seed a tenant_admin for the Default Tenant (mirrors scripts/migrations/058).

Revision ID: 0003_seed_default_tenant_admin
Revises: 0002_support_access_grants
Create Date: 2026-10-16

The "Default Tenant" / "Default Workspace" seeded by legacy migration 027b
had no tenant_admin and no workspace members — only platform_admin's old
unconditional cross-tenant bypass could ever reach it. Now that
platform_admin requires a tenant-admin-issued support access grant, that
workspace became permanently unreachable with no one able to grant access
into it. Seed a real tenant_admin so it's reachable the same way every
other client tenant now works.

On a fresh database this row is also created by
``scripts/migrations/058_seed_default_tenant_admin.sql`` (replayed by the
0001 baseline's dynamic glob at upgrade time) — this revision exists so
already-migrated databases (where 0001 is already applied and won't re-scan
that directory) pick it up too. Both are idempotent; whichever runs first
wins.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_seed_default_tenant_admin"
down_revision: Union[str, None] = "0002_support_access_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO users (id, email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
        SELECT '70000000-0000-4000-8000-000000000001'::uuid,
               'tenant-admin@example.com',
               crypt(encode(digest('change-me-strong-password','sha256'),'hex'), gen_salt('bf', 12)),
               'Default Tenant Admin',
               'tenant_admin',
               '8062ed84-5660-4470-833c-f748ed0a7481',
               'ACTIVE', TRUE, NOW(), NOW()
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'tenant-admin@example.com');
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE email = 'tenant-admin@example.com';")
