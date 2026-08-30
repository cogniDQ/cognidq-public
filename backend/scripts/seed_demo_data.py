#!/usr/bin/env python3
"""Seed demo data for a fresh CogniDQ installation.

Creates the demo tenant, workspace, and users documented in
docs/getting-started.md.  Fully idempotent — safe to re-run.

Usage (inside the backend container):

    python /app/scripts/seed_demo_data.py

Or via Make:

    make seed
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from uuid import UUID

import bcrypt
import psycopg2
import psycopg2.extras

# Make `app` importable so we can read settings.DATABASE_URL.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Well-known UUIDs (deterministic so the script is idempotent across runs).
# ──────────────────────────────────────────────────────────────────────────────

# Platform bootstrap admin — same UUID hard-coded in 004_default_org_domain_team.sql
BOOTSTRAP_ADMIN_UUID = UUID("63cae557-c3bc-4442-8592-58205e772aa6")

DEMO_TENANT_UUID = UUID("10000000-1000-4000-8000-000000000001")
DEMO_WORKSPACE_UUID = UUID("20000000-2000-4000-8000-000000000002")

DEMO_TENANT_ADMIN_UUID = UUID("10000001-1000-4000-8000-000000000001")
DEMO_WS_ADMIN_UUID = UUID("20000001-2000-4000-8000-000000000001")
DEMO_STEWARD_UUID = UUID("20000002-2000-4000-8000-000000000002")
DEMO_VIEWER_UUID = UUID("20000003-2000-4000-8000-000000000003")

DEMO_PASSWORD = "change-me-strong-password"


def _hash_password(password: str) -> str:
    """Mirror ``User.set_password``: SHA-256 then bcrypt(rounds=12)."""
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(sha.encode("utf-8"), salt).decode("utf-8")


def _upsert_user(
    cur,
    *,
    user_id: UUID,
    email: str,
    full_name: str,
    platform_role: str | None,
    tenant_id: UUID | None,
) -> str:
    """Insert user if not present; update role/status if already exists."""
    pw_hash = _hash_password(DEMO_PASSWORD)
    cur.execute(
        """
        INSERT INTO users (
            id, email, password_hash, full_name,
            platform_role, tenant_id,
            status, email_verified,
            created_at, updated_at
        )
        VALUES (
            %s, %s, %s, %s,
            %s, %s,
            'ACTIVE', TRUE,
            NOW(), NOW()
        )
        ON CONFLICT (id) DO UPDATE
            SET password_hash  = EXCLUDED.password_hash,
                full_name      = EXCLUDED.full_name,
                platform_role  = EXCLUDED.platform_role,
                status         = 'ACTIVE',
                email_verified = TRUE,
                updated_at     = NOW()
        """,
        (
            str(user_id),
            email.strip().lower(),
            pw_hash,
            full_name,
            platform_role,
            str(tenant_id) if tenant_id else None,
        ),
    )
    return email


def _upsert_tenant(cur) -> None:
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug,
            status, region, plan,
            created_at, updated_at,
            created_by, updated_by, version
        )
        VALUES (
            %s, 'Demo Tenant', 'demo',
            'ACTIVE', 'eu-west', 'enterprise',
            NOW(), NOW(),
            %s, %s, 0
        )
        ON CONFLICT (tenant_id) DO NOTHING
        """,
        (str(DEMO_TENANT_UUID), str(BOOTSTRAP_ADMIN_UUID), str(BOOTSTRAP_ADMIN_UUID)),
    )


def _upsert_workspace(cur) -> None:
    # workspace_name_lower is GENERATED ALWAYS AS STORED (migration 041) —
    # must NOT be included in INSERT or UPDATE column lists.
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id,
            workspace_name, workspace_slug,
            default_timezone, status,
            created_at, updated_at,
            created_by, updated_by, version
        )
        VALUES (
            %s, %s,
            'Demo Workspace', 'demo-workspace',
            'UTC', 'ACTIVE',
            NOW(), NOW(),
            %s, %s, 0
        )
        ON CONFLICT (workspace_id) DO NOTHING
        """,
        (
            str(DEMO_WORKSPACE_UUID),
            str(DEMO_TENANT_UUID),
            str(BOOTSTRAP_ADMIN_UUID),
            str(BOOTSTRAP_ADMIN_UUID),
        ),
    )


def _upsert_workspace_role(cur, *, workspace_id: UUID, user_id: UUID, role_name: str) -> None:
    cur.execute(
        """
        INSERT INTO control.workspace_role_assignments
            (workspace_id, user_id, role_name, granted_by, granted_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (workspace_id, user_id) DO UPDATE
            SET role_name  = EXCLUDED.role_name,
                granted_at = NOW()
        """,
        (str(workspace_id), str(user_id), role_name, str(BOOTSTRAP_ADMIN_UUID)),
    )


def main() -> int:
    print("CogniDQ demo seed — starting …\n")

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()
    except Exception as exc:
        print(f"✗  Cannot connect to database: {exc}", file=sys.stderr)
        print(
            "   Make sure the stack is running and migrations have been applied.", file=sys.stderr
        )
        return 1

    try:
        # ── 0. Ensure pgcrypto is available (used by some migrations) ──
        cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

        # ── 1. Platform admin ──────────────────────────────────────────
        print("Seeding platform admin …")
        pw_hash = _hash_password(DEMO_PASSWORD)
        cur.execute(
            """
            INSERT INTO users (
                id, email, password_hash, full_name,
                platform_role, tenant_id,
                status, email_verified, created_at, updated_at
            )
            VALUES (
                %s, 'admin@example.com', %s, 'Platform Admin',
                'platform_admin', NULL,
                'ACTIVE', TRUE, NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE
                SET password_hash  = EXCLUDED.password_hash,
                    platform_role  = 'platform_admin',
                    status         = 'ACTIVE',
                    email_verified = TRUE,
                    updated_at     = NOW()
            """,
            (str(BOOTSTRAP_ADMIN_UUID), pw_hash),
        )
        # Also upsert by email in case the ID row exists under a different email.
        cur.execute(
            """
            INSERT INTO users (
                id, email, password_hash, full_name,
                platform_role, tenant_id,
                status, email_verified, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(), 'admin@example.com', %s, 'Platform Admin',
                'platform_admin', NULL,
                'ACTIVE', TRUE, NOW(), NOW()
            )
            ON CONFLICT (email) DO UPDATE
                SET password_hash  = EXCLUDED.password_hash,
                    platform_role  = 'platform_admin',
                    status         = 'ACTIVE',
                    email_verified = TRUE,
                    updated_at     = NOW()
            """,
            (pw_hash,),
        )
        print("  ✓  admin@example.com  (platform_admin)")

        # ── 2. Demo tenant ────────────────────────────────────────────
        print("\nSeeding demo tenant …")
        _upsert_tenant(cur)
        print("  ✓  Demo Tenant  (id=10000000-…)")

        # ── 3. Tenant admin user ──────────────────────────────────────
        _upsert_user(
            cur,
            user_id=DEMO_TENANT_ADMIN_UUID,
            email="tenant.admin@example.com",
            full_name="Tenant Admin",
            platform_role="tenant_admin",
            tenant_id=DEMO_TENANT_UUID,
        )
        print("  ✓  tenant.admin@example.com  (tenant_admin)")

        # ── 4. Demo workspace ─────────────────────────────────────────
        print("\nSeeding demo workspace …")
        _upsert_workspace(cur)
        print("  ✓  Demo Workspace  (id=20000000-…)")

        # ── 5. Workspace-scoped users ─────────────────────────────────
        print("\nSeeding workspace users …")
        _upsert_user(
            cur,
            user_id=DEMO_WS_ADMIN_UUID,
            email="ws.admin@example.com",
            full_name="Workspace Admin",
            platform_role=None,
            tenant_id=DEMO_TENANT_UUID,
        )
        _upsert_workspace_role(
            cur,
            workspace_id=DEMO_WORKSPACE_UUID,
            user_id=DEMO_WS_ADMIN_UUID,
            role_name="workspace_administrator",
        )
        print("  ✓  ws.admin@example.com  (workspace_administrator)")

        _upsert_user(
            cur,
            user_id=DEMO_STEWARD_UUID,
            email="steward@example.com",
            full_name="Data Steward",
            platform_role=None,
            tenant_id=DEMO_TENANT_UUID,
        )
        _upsert_workspace_role(
            cur,
            workspace_id=DEMO_WORKSPACE_UUID,
            user_id=DEMO_STEWARD_UUID,
            role_name="data_steward",
        )
        print("  ✓  steward@example.com  (data_steward)")

        _upsert_user(
            cur,
            user_id=DEMO_VIEWER_UUID,
            email="viewer@example.com",
            full_name="Governance Viewer",
            platform_role=None,
            tenant_id=DEMO_TENANT_UUID,
        )
        _upsert_workspace_role(
            cur,
            workspace_id=DEMO_WORKSPACE_UUID,
            user_id=DEMO_VIEWER_UUID,
            role_name="governance_viewer",
        )
        print("  ✓  viewer@example.com  (governance_viewer)")

        conn.commit()

    except Exception as exc:
        conn.rollback()
        print(f"\n✗  Seed failed: {exc}", file=sys.stderr)
        print("\nMake sure migrations have been applied first:", file=sys.stderr)
        print("   docker compose exec backend python scripts/run_migrations.py", file=sys.stderr)
        cur.close()
        conn.close()
        return 1

    cur.close()
    conn.close()

    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓  Demo seed complete.  Open http://localhost:5173 and sign in:

   Role                Email                         Password
   ──────────────────  ────────────────────────────  ──────────────────────────────
   Platform admin      admin@example.com             change-me-strong-password
   Tenant admin        tenant.admin@example.com      change-me-strong-password
   Workspace admin     ws.admin@example.com          change-me-strong-password
   Data steward        steward@example.com           change-me-strong-password
   Governance viewer   viewer@example.com            change-me-strong-password

   ⚠  These passwords are for local demo use only.
      Never expose this stack to the internet without hardening.
      See docs/production-hardening.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
