#!/usr/bin/env python3
"""Seed demo content into the Demo Workspace for a fresh CogniDQ installation.

The Demo Workspace itself (and the RBAC QA tenant/users it lives under)
is created by migration `052_seed_rbac_qa_users.sql` + `0005_consolidate_
demo_into_rbac_qa.py` — this script only adds ready-to-explore demo
content on top of it: a live connection, datasets, glossary terms, DQ
rules, a flow, and one REAL flow execution. Fully idempotent — safe to
re-run.

Usage (inside the backend container):

    python /app/scripts/seed_demo_data.py

Or via Make:

    make seed
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_DNS, UUID, uuid5

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

# The Demo Workspace is the RBAC QA tenant/workspace, renamed by migration
# 0005_consolidate_into_rbac_qa — seeded by 052_seed_rbac_qa_users.sql.
DEMO_TENANT_UUID = UUID("33333333-3333-4333-8333-333333333333")
DEMO_WORKSPACE_UUID = UUID("44444444-4444-4444-8444-444444444444")

DEMO_PASSWORD = "change-me-strong-password"


def _demo_uid(name: str) -> UUID:
    """Mirror GeneralDQSeeder's deterministic UUID5 scheme."""
    return uuid5(NAMESPACE_DNS, f"{DEMO_WORKSPACE_UUID}:{name}")


def _hash_password(password: str) -> str:
    """Mirror ``User.set_password``: SHA-256 then bcrypt(rounds=12)."""
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(sha.encode("utf-8"), salt).decode("utf-8")


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

        # ── 2. Demo Workspace (RBAC QA tenant/workspace) ───────────────
        # Created by migrations 052_seed_rbac_qa_users.sql +
        # 0005_consolidate_into_rbac_qa — nothing to seed here, just
        # confirm it exists before layering demo content on top.
        cur.execute(
            "SELECT 1 FROM control.workspaces WHERE workspace_id = %s",
            (str(DEMO_WORKSPACE_UUID),),
        )
        if cur.fetchone() is None:
            raise RuntimeError(
                "Demo Workspace not found — run `alembic upgrade head` first "
                "(it is seeded by migrations 052 and 0005)."
            )
        print("\n  ✓  Demo Workspace  (id=44444444-…, data_steward: qa.datasteward@rbac-qa.test)")

        conn.commit()

        # ── 3. Demo source tables (schema `demo`) ──────────────────────
        print("\nSeeding demo source tables (schema `demo`) …")
        _create_demo_tables(cur)
        conn.commit()
        print("  ✓  demo.customers / demo.orders / demo.products")

    except Exception as exc:
        conn.rollback()
        print(f"\n✗  Seed failed: {exc}", file=sys.stderr)
        print("\nMake sure migrations have been applied first:", file=sys.stderr)
        print("   docker compose exec backend alembic upgrade head", file=sys.stderr)
        cur.close()
        conn.close()
        return 1

    cur.close()
    conn.close()

    # ── 4. Demo content (datasets, rules, glossary, flow, real run) ────
    print("\nSeeding demo content …")
    try:
        _seed_demo_content()
    except Exception as exc:
        print(f"\n✗  Demo content seeding failed: {exc}", file=sys.stderr)
        print("   Users and workspace were seeded; you can still log in.", file=sys.stderr)
        return 1

    print("""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓  Demo seed complete.  Open http://localhost:5173 and sign in:

   Role                Email                           Password
   ──────────────────  ──────────────────────────────  ──────────────────────────
   Platform admin      admin@example.com               change-me-strong-password
   Tenant admin        qa.tenantadmin@rbac-qa.test      change-me-strong-password
   Data steward        qa.datasteward@rbac-qa.test      change-me-strong-password

   The Demo Workspace comes pre-loaded with a live connection,
   datasets, glossary terms, DQ rules, a flow, and one real run.
   (Note: the platform admin only sees it after a tenant admin grants
   temporary support access — log in as the tenant admin or data
   steward above to explore it directly.)

   ⚠  These passwords are for local demo use only.
      Never expose this stack to the internet without hardening.
      See docs/production-hardening.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Demo source tables — real Postgres tables with deliberate DQ problems.
# ──────────────────────────────────────────────────────────────────────────────


def _create_demo_tables(cur) -> None:
    """(Re)create the `demo` schema tables the demo flow runs against."""
    cur.execute("CREATE SCHEMA IF NOT EXISTS demo")
    cur.execute("DROP TABLE IF EXISTS demo.customers, demo.orders, demo.products")

    cur.execute("""
        CREATE TABLE demo.customers (
            id          TEXT,
            email       TEXT,
            first_name  TEXT,
            last_name   TEXT,
            country_code TEXT,
            created_at  TIMESTAMPTZ
        )
    """)
    cur.execute("""
        INSERT INTO demo.customers VALUES
        ('c-0001', 'alice@acme.io',       'Alice', 'Smith',  'US', '2025-09-01 10:00:00+00'),
        ('c-0002', 'bob@example.com',     'Bob',   'Jones',  'FR', '2025-09-03 11:30:00+00'),
        ('c-0003', 'carol@example.com',   'Carol', 'Patel',  'DE', '2025-09-05 09:15:00+00'),
        ('c-0004', NULL,                  'Dan',   'Müller', 'GB', '2025-09-07 16:45:00+00'),
        ('c-0005', 'not-an-email',        'Eve',   'Brown',  'MA', '2025-09-10 08:05:00+00'),
        ('c-0006', 'frank@example.com',   'Frank', 'Silva',  'US', '2025-09-12 12:00:00+00'),
        ('c-0007', NULL,                  'Grace', 'Kim',    'KR', '2025-09-15 14:20:00+00'),
        ('c-0008', 'heidi@example.com',   'Heidi', 'Novak',  'CZ', '2025-09-18 10:10:00+00'),
        ('c-0008', 'heidi.dup@example.com','Heidi','Novak',  'CZ', '2025-09-18 10:11:00+00'),
        ('c-0010', 'ivan@example.com',    'Ivan',  'Popov',  'BG', '2025-09-21 17:00:00+00')
    """)

    cur.execute("""
        CREATE TABLE demo.orders (
            id           TEXT,
            customer_id  TEXT,
            total_amount NUMERIC(10,2),
            status       TEXT,
            ordered_at   TIMESTAMPTZ
        )
    """)
    cur.execute("""
        INSERT INTO demo.orders VALUES
        ('o-0001', 'c-0001',  19.99, 'paid',     '2025-09-02 09:12:00+00'),
        ('o-0002', 'c-0002',  45.00, 'pending',  '2025-09-04 14:55:00+00'),
        ('o-0003', 'c-0003',   0.00, 'paid',     '2025-09-06 10:00:00+00'),
        ('o-0004', 'c-0004',  -3.50, 'refunded', '2025-09-08 11:30:00+00'),
        ('o-0005', 'c-0005', 120.00, NULL,       '2025-09-11 13:00:00+00'),
        ('o-0006', 'c-0006',  75.25, 'paid',     '2025-09-13 15:45:00+00'),
        ('o-0007', 'c-0008',  32.10, NULL,       '2025-09-19 09:30:00+00'),
        ('o-0008', 'c-0010',  58.60, 'shipped',  '2025-09-22 16:20:00+00')
    """)

    cur.execute("""
        CREATE TABLE demo.products (
            id       TEXT,
            name     TEXT,
            price    NUMERIC(10,2),
            category TEXT,
            active   BOOLEAN
        )
    """)
    cur.execute("""
        INSERT INTO demo.products VALUES
        ('p-0001', 'Widget A',    9.99, 'Tools',   TRUE),
        ('p-0002', 'Widget B',   19.50, 'Tools',   TRUE),
        ('p-0003', 'Gadget Pro',  0.00, 'Gadgets', TRUE),
        ('p-0004', 'Gizmo Mini', 14.75, 'Gadgets', FALSE),
        ('p-0005', NULL,          4.20, 'Misc',    TRUE)
    """)


# ──────────────────────────────────────────────────────────────────────────────
# Demo content — reuses the general_dq sandbox template seeder, then wires a
# real credentialed connection + an executable flow and triggers one real run.
# ──────────────────────────────────────────────────────────────────────────────


def _seed_demo_content() -> None:
    from app.models.database import SessionLocal
    from app.services.data_sources import credential_service
    from app.services.demo.templates.general_dq.seeder import GeneralDQSeeder
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # 4a. Template content: datasets, fields, rules, glossary, issues …
        GeneralDQSeeder(db).seed(DEMO_TENANT_UUID, DEMO_WORKSPACE_UUID)
        db.commit()
        print("  ✓  datasets, rules, glossary, issues (template: general_dq)")

        ds_id = _demo_uid("demo_data_source")
        flow_id = _demo_uid("flow_nightly_dq")

        # 4b. Point the template datasets at the real `demo` schema tables.
        db.execute(
            text(
                "UPDATE control.datasets SET schema_name = 'demo' "
                "WHERE workspace_id = :wid AND seed_source = 'template:general_dq'"
            ),
            {"wid": str(DEMO_WORKSPACE_UUID)},
        )

        # 4c. Give the demo connection real credentials (the app's own DB) so
        #     flow executions can actually connect.
        parsed = urlparse(settings.DATABASE_URL)
        creds = {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "database": (parsed.path or "/").lstrip("/"),
            "username": parsed.username,
            "password": parsed.password,
        }
        cred_id = _demo_uid("demo_data_source_credentials")
        db.execute(
            text("""
                INSERT INTO control.data_source_credentials
                    (credential_id, data_source_id, source_type, encrypted_payload,
                     created_at, created_by)
                VALUES (:cid, :dsid, 'postgresql', :payload, NOW(), :uid)
                ON CONFLICT (credential_id) DO UPDATE
                    SET encrypted_payload = EXCLUDED.encrypted_payload,
                        superseded_at = NULL
            """),
            {
                "cid": str(cred_id),
                "dsid": str(ds_id),
                "payload": credential_service.encrypt(creds),
                "uid": str(BOOTSTRAP_ADMIN_UUID),
            },
        )
        db.execute(
            text(
                "UPDATE control.data_sources SET credential_reference = :cid "
                "WHERE data_source_id = :dsid"
            ),
            {"cid": str(cred_id), "dsid": str(ds_id)},
        )

        # 4d. Make the connection visible on the workspace connections list.
        db.execute(
            text("""
                INSERT INTO control.workspace_connection_assignments
                    (connection_id, workspace_id, assigned_at, assigned_by)
                VALUES (:cid, :wid, NOW(), :uid)
                ON CONFLICT (connection_id, workspace_id) DO NOTHING
            """),
            {
                "cid": str(ds_id),
                "wid": str(DEMO_WORKSPACE_UUID),
                "uid": str(BOOTSTRAP_ADMIN_UUID),
            },
        )

        # 4e. Replace the template's placeholder flow definition with an
        #     executable source → checks graph (same shape the UI builder saves).
        flow_def = {
            "nodes": [
                {
                    "id": "source_customers",
                    "type": "source",
                    "label": "demo.customers",
                    "config": {
                        "data_source_id": str(ds_id),
                        "schema_name": "demo",
                        "table_name": "customers",
                    },
                    "position": {"x": 80, "y": 200},
                },
                {
                    "id": "check_email_completeness",
                    "type": "check",
                    "label": "customers.email — Not Null",
                    "checkType": "completeness",
                    "config": {"checkType": "completeness", "columns": ["email"]},
                    "position": {"x": 420, "y": 100},
                },
                {
                    "id": "check_id_uniqueness",
                    "type": "check",
                    "label": "customers.id — Unique",
                    "checkType": "uniqueness",
                    "config": {"checkType": "uniqueness", "columns": ["id"]},
                    "position": {"x": 420, "y": 300},
                },
            ],
            "connections": [
                {"id": "conn_1", "from": "source_customers", "to": "check_email_completeness"},
                {"id": "conn_2", "from": "source_customers", "to": "check_id_uniqueness"},
            ],
            "metadata": {"seed_source": "template:general_dq"},
        }
        db.execute(
            text(
                "UPDATE public.dq_flows SET flow_definition = CAST(:def AS JSONB), "
                "updated_at = NOW() WHERE id = :fid"
            ),
            {"def": json.dumps(flow_def), "fid": str(flow_id)},
        )
        db.commit()
        print("  ✓  live connection + executable flow (Nightly DQ Sweep)")

        # 4f. One REAL flow execution so reports/results show genuine data.
        already_ran = db.execute(
            text(
                "SELECT 1 FROM public.flow_executions "
                "WHERE flow_id = :fid AND execution_type = 'manual' LIMIT 1"
            ),
            {"fid": str(flow_id)},
        ).fetchone()
        if already_ran:
            print("  ✓  real flow run already present — skipping")
        else:
            from app.services.flows.service import FlowService

            execution = asyncio.run(
                FlowService().execute_flow(
                    db=db,
                    flow_id=flow_id,
                    workspace_id=DEMO_WORKSPACE_UUID,
                    user_id=BOOTSTRAP_ADMIN_UUID,
                )
            )
            db.commit()
            print(f"  ✓  real flow run finished — status: {execution.status}")
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
