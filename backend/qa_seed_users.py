"""
QA onboarding seed script.
Creates/resets test users used by the New Customer Onboarding QA run.

Passwords are stored via User.set_password (sha256 -> bcrypt).
Run INSIDE the backend container:
    docker exec -i dq-backend-1 python /app/../qa_seed_users.py
or mount and run.
"""

import os
import sys

sys.path.insert(0, "/app")

import hashlib

import bcrypt
import psycopg2
import psycopg2.extras

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/dataquality_db")

USERS = [
    # (email, full_name, password, platform_role, tenant_id, status)
    (
        "admin@example.com",
        "Platform Admin",
        "change-me-strong-password",
        "platform_admin",
        "8062ed84-5660-4470-833c-f748ed0a7481",
        "ACTIVE",
    ),
    (
        "qa.wsadmin@example.com",
        "QA Workspace Admin",
        "change-me-strong-password",
        None,
        None,
        "ACTIVE",
    ),
    (
        "qa.member@example.com",
        "QA Workspace Member",
        "change-me-strong-password",
        None,
        None,
        "ACTIVE",
    ),
    (
        "qa.outsider@example.com",
        "QA Other Tenant User",
        "change-me-strong-password",
        None,
        None,
        "ACTIVE",
    ),
    # Note: qa.owner is intentionally NOT seeded here; provisioning creates it.
]


def hashpw(pw: str) -> str:
    h = hashlib.sha256(pw.encode()).hexdigest()
    return bcrypt.hashpw(h.encode(), bcrypt.gensalt(rounds=12)).decode()


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    for email, name, pw, prole, tid, status in USERS:
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
                       status=%s,
                       email_verified=TRUE,
                       updated_at=NOW()
                 WHERE email=%s
                """,
                (ph, name, prole, tid, status, email),
            )
            print(f"updated  {email}  pw={pw}")
        else:
            cur.execute(
                """
                INSERT INTO users (email, password_hash, full_name, platform_role, tenant_id, status, email_verified, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,TRUE,NOW(),NOW())
                """,
                (email, ph, name, prole, tid, status),
            )
            print(f"created  {email}  pw={pw}")

    cur.execute(
        "SELECT email, platform_role, tenant_id, status, email_verified FROM users ORDER BY created_at"
    )
    print("\n--- USERS ---")
    for r in cur.fetchall():
        print(r)

    conn.close()


if __name__ == "__main__":
    main()
