"""
Seed qa.tenantadmin@example.com as a first-class tenant_admin for the
analytics-tenant (QA Acme). Idempotent.

Run:
    docker exec -i dq-backend-1 python /app/qa_seed_tenant_admin.py
"""

import os
import sys

sys.path.insert(0, "/app")

import hashlib

import bcrypt
import psycopg2
import psycopg2.extras

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/dataquality_db")
TENANT_ID = "1496b2dd-1623-4eff-a316-9303fee2153f"  # QA Acme
EMAIL = "qa.tenantadmin@example.com"
NAME = "QA Tenant Admin"
PW = "change-me-strong-password"


def hashpw(pw: str) -> str:
    h = hashlib.sha256(pw.encode()).hexdigest()
    return bcrypt.hashpw(h.encode(), bcrypt.gensalt(rounds=12)).decode()


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ph = hashpw(PW)

    cur.execute("SELECT id FROM users WHERE email=%s", (EMAIL,))
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE users SET password_hash=%s, full_name=%s,
                   platform_role='tenant_admin', tenant_id=%s,
                   status='ACTIVE', email_verified=TRUE, updated_at=NOW()
             WHERE email=%s
            """,
            (ph, NAME, TENANT_ID, EMAIL),
        )
        print(f"updated  {EMAIL}  pw={PW}  platform_role=tenant_admin  tenant_id={TENANT_ID}")
    else:
        cur.execute(
            """
            INSERT INTO users (email, password_hash, full_name, platform_role,
                               tenant_id, status, email_verified, created_at, updated_at)
            VALUES (%s,%s,%s,'tenant_admin',%s,'ACTIVE',TRUE,NOW(),NOW())
            """,
            (EMAIL, ph, NAME, TENANT_ID),
        )
        print(f"created  {EMAIL}  pw={PW}  platform_role=tenant_admin  tenant_id={TENANT_ID}")

    cur.execute(
        "SELECT email, platform_role, tenant_id, status FROM users WHERE email=%s",
        (EMAIL,),
    )
    print(cur.fetchone())
    conn.close()


if __name__ == "__main__":
    main()
