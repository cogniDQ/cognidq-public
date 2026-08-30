"""
qa_seed_rbac_users.py — Seed the RBAC-QA tenant, workspace and one test user
per role. Companion to migration 052_seed_rbac_qa_users.sql for live DBs that
were already migrated past 052 (migrations are not re-applied incrementally).

Run inside the backend container:
    docker exec -i dq-backend-1 python /app/../qa_seed_rbac_users.py
or with the project venv:
    python qa_seed_rbac_users.py

Idempotent: every INSERT uses ON CONFLICT / WHERE NOT EXISTS. Re-running
refreshes the password hashes for the seeded accounts so credentials stay
in lockstep with documentation/TEST_CREDENTIALS.md.
"""
from __future__ import annotations

import hashlib
import os
import sys
from typing import List, Optional, Tuple

import bcrypt
import psycopg2
import psycopg2.extras


DB_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@db:5432/dataquality_db"
)

# Constants — keep in sync with backend/scripts/migrations/052_seed_rbac_qa_users.sql.
RBAC_QA_TENANT_ID = "33333333-3333-4333-8333-333333333333"
RBAC_QA_WORKSPACE_ID = "44444444-4444-4444-8444-444444444444"
GRANTED_BY_USER_ID = "63cae557-c3bc-4442-8592-58205e772aa6"  # bootstrap admin

# (user_id, email, full_name, password, platform_role, tenant_id, workspace_role)
USERS: List[Tuple[str, str, str, str, Optional[str], Optional[str], Optional[str]]] = [
    (
        "50000001-0000-4000-8000-000000000001",
        "qa.platformadmin@dq.test",
        "QA Platform Admin",
        "change-me-strong-password",
        "platform_admin",
        None,
        None,
    ),
    (
        "50000002-0000-4000-8000-000000000002",
        "qa.platformviewer@dq.test",
        "QA Platform Viewer",
        "change-me-strong-password",
        "platform_viewer",
        None,
        None,
    ),
    (
        "50000003-0000-4000-8000-000000000003",
        "qa.tenantadmin@rbac-qa.test",
        "QA Tenant Admin",
        "change-me-strong-password",
        "tenant_admin",
        RBAC_QA_TENANT_ID,
        None,
    ),
    (
        "50000004-0000-4000-8000-000000000004",
        "qa.wsadmin@rbac-qa.test",
        "QA Workspace Administrator",
        "change-me-strong-password",
        None,
        RBAC_QA_TENANT_ID,
        "workspace_administrator",
    ),
    (
        "50000005-0000-4000-8000-000000000005",
        "qa.dataengineer@rbac-qa.test",
        "QA Data Engineer",
        "change-me-strong-password",
        None,
        RBAC_QA_TENANT_ID,
        "data_engineer",
    ),
    (
        "50000006-0000-4000-8000-000000000006",
        "qa.datasteward@rbac-qa.test",
        "QA Data Steward",
        "change-me-strong-password",
        None,
        RBAC_QA_TENANT_ID,
        "data_steward",
    ),
    (
        "50000007-0000-4000-8000-000000000007",
        "qa.analyst@rbac-qa.test",
        "QA Business Analyst",
        "change-me-strong-password",
        None,
        RBAC_QA_TENANT_ID,
        "business_analyst",
    ),
    (
        "50000008-0000-4000-8000-000000000008",
        "qa.viewer@rbac-qa.test",
        "QA Governance Viewer",
        "change-me-strong-password",
        None,
        RBAC_QA_TENANT_ID,
        "governance_viewer",
    ),
]


def hashpw(pw: str) -> str:
    """Match User.set_password: bcrypt(sha256_hex(pw), rounds=12)."""
    h = hashlib.sha256(pw.encode()).hexdigest()
    return bcrypt.hashpw(h.encode(), bcrypt.gensalt(rounds=12)).decode()


def upsert_tenant_and_workspace(cur) -> None:
    cur.execute(
        """
        INSERT INTO control.tenants (
            tenant_id, tenant_name, tenant_slug, status,
            region, plan, created_at, updated_at,
            created_by, updated_by, version
        ) VALUES (
            %s, 'RBAC QA', 'rbac-qa', 'active',
            'eu-west', 'enterprise', NOW(), NOW(),
            %s, %s, 0
        )
        ON CONFLICT (tenant_id) DO NOTHING
        """,
        (RBAC_QA_TENANT_ID, GRANTED_BY_USER_ID, GRANTED_BY_USER_ID),
    )
    cur.execute(
        """
        INSERT INTO control.workspaces (
            workspace_id, tenant_id, workspace_name,
            workspace_slug, default_timezone, status,
            created_at, updated_at, created_by, updated_by, version
        ) VALUES (
            %s, %s, 'RBAC QA Workspace',
            'rbac-qa-workspace', 'UTC', 'active',
            NOW(), NOW(), %s, %s, 0
        )
        ON CONFLICT (workspace_id) DO NOTHING
        """,
        (
            RBAC_QA_WORKSPACE_ID,
            RBAC_QA_TENANT_ID,
            GRANTED_BY_USER_ID,
            GRANTED_BY_USER_ID,
        ),
    )


def upsert_user(cur, user_id, email, full_name, pw, platform_role, tenant_id) -> None:
    ph = hashpw(pw)
    cur.execute("SELECT id FROM users WHERE email=%s", (email,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE users
               SET password_hash=%s,
                   full_name=%s,
                   platform_role=%s,
                   tenant_id=%s,
                   status='ACTIVE',
                   email_verified=TRUE,
                   updated_at=NOW()
             WHERE email=%s
            """,
            (ph, full_name, platform_role, tenant_id, email),
        )
        print(f"updated  {email}  pw={pw}")
    else:
        cur.execute(
            """
            INSERT INTO users (
                id, email, password_hash, full_name,
                platform_role, tenant_id, status,
                email_verified, created_at, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,'ACTIVE',TRUE,NOW(),NOW())
            """,
            (user_id, email, ph, full_name, platform_role, tenant_id),
        )
        print(f"created  {email}  pw={pw}")


def upsert_workspace_role(cur, user_id: str, role_name: str) -> None:
    cur.execute(
        """
        INSERT INTO control.workspace_role_assignments
            (workspace_id, user_id, role_name, granted_by, granted_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (workspace_id, user_id) DO UPDATE
           SET role_name = EXCLUDED.role_name,
               granted_by = EXCLUDED.granted_by,
               granted_at = NOW()
        """,
        (RBAC_QA_WORKSPACE_ID, user_id, role_name, GRANTED_BY_USER_ID),
    )


def main() -> int:
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    upsert_tenant_and_workspace(cur)

    for uid, email, name, pw, prole, tid, wsrole in USERS:
        upsert_user(cur, uid, email, name, pw, prole, tid)
        if wsrole:
            upsert_workspace_role(cur, uid, wsrole)

    cur.execute(
        """
        SELECT u.email, u.platform_role, u.tenant_id, u.status, u.email_verified,
               wra.role_name AS workspace_role
          FROM users u
          LEFT JOIN control.workspace_role_assignments wra
                 ON wra.user_id = u.id
                AND wra.workspace_id = %s
         WHERE u.email LIKE 'qa.%%@%%'
         ORDER BY u.email
        """,
        (RBAC_QA_WORKSPACE_ID,),
    )
    print("\n--- RBAC QA USERS ---")
    for r in cur.fetchall():
        print(r)

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
