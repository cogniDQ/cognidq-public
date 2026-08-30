#!/usr/bin/env python3
"""One-shot bootstrap for a fresh local database.

Order:
    1. Run migration 001_auth.sql (creates ``users``).
    2. Seed the platform_admin user with the UUID hard-coded by
       migration 004 (so 004's FK references resolve).
    3. Run all remaining migration files in lexical order.
    4. Promote the seeded user to ``platform_role = 'platform_admin'``.

Usage::

    docker exec dq-backend-1 python /app/scripts/bootstrap_fresh_db.py \\
        --admin-email admin@example.com \\
        --admin-password <your-password> \\
        --admin-full-name "CogniDQ Admin"
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import bcrypt
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings  # noqa: E402

# UUID hard-coded in 004_default_org_domain_team.sql for the bootstrap user.
BOOTSTRAP_USER_UUID = "63cae557-c3bc-4442-8592-58205e772aa6"


def _hash_password(password: str) -> str:
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(sha.encode("utf-8"), salt).decode("utf-8")


def _exec_sql_file(cur, path: Path) -> None:
    print(f"  -> {path.name}")
    cur.execute(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", required=True)
    parser.add_argument("--admin-full-name", default=None)
    args = parser.parse_args()

    migrations_dir = Path(__file__).resolve().parent / "migrations"
    files = sorted(migrations_dir.glob("*.sql"))
    if not files:
        print("No migration files found.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    try:
        # 1. Apply 001_auth.sql so the users table exists.
        first = files[0]
        if not first.name.startswith("001_"):
            print(
                f"Expected first migration to start with '001_', got {first.name}",
                file=sys.stderr,
            )
            return 1
        print("Applying 001_auth.sql ...")
        _exec_sql_file(cur, first)

        # 2. Seed the bootstrap user before migration 004 runs (which has a
        # hard-coded FK to this user id).
        pw_hash = _hash_password(args.admin_password)
        print(f"Seeding bootstrap user {args.admin_email} (id={BOOTSTRAP_USER_UUID}) ...")
        cur.execute(
            """
            INSERT INTO users
                (id, email, password_hash, full_name, email_verified,
                 status, created_at, updated_at)
            VALUES
                (%s, %s, %s, %s, TRUE, 'active', NOW(), NOW())
            ON CONFLICT (email) DO UPDATE
                SET password_hash  = EXCLUDED.password_hash,
                    full_name      = COALESCE(EXCLUDED.full_name, users.full_name),
                    email_verified = TRUE,
                    status         = 'active',
                    updated_at     = NOW()
            """,
            (
                BOOTSTRAP_USER_UUID,
                args.admin_email.strip().lower(),
                pw_hash,
                args.admin_full_name,
            ),
        )

        # 3. Apply remaining migrations in order.
        print("Applying remaining migrations ...")
        for path in files[1:]:
            _exec_sql_file(cur, path)

        # 4. Promote the user to platform_admin (column added in 027/041).
        print("Promoting user to platform_admin ...")
        cur.execute(
            "UPDATE users SET platform_role = 'platform_admin' WHERE email = %s",
            (args.admin_email.strip().lower(),),
        )

        print("\n\u2713 Fresh DB bootstrap complete.")
        print(f"  Email:    {args.admin_email}")
        print(f"  Password: {args.admin_password}")
        print("  Role:     platform_admin")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
