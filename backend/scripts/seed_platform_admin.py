#!/usr/bin/env python3
"""Seed (or update) a platform_admin user.

Usage (inside the backend container):

    python /app/scripts/seed_platform_admin.py \
        --email admin@example.com \
        --password <your-password> \
        --full-name "Platform Admin"

The password is hashed using the same SHA-256 -> bcrypt pipeline as
``app.models.user.User.set_password`` so the resulting hash is a valid
login credential.

Idempotent: if a user with the email already exists, their
``password_hash``, ``platform_role``, ``status`` and ``email_verified``
are updated in place. ``tenant_id`` stays NULL (platform admins are
tenant-agnostic).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from uuid import uuid4

import bcrypt
import psycopg2

# Make `app` importable so we can read settings.DATABASE_URL.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings  # noqa: E402


def _hash_password(password: str) -> str:
    """Mirror ``User.set_password``: SHA-256 then bcrypt(rounds=12)."""
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(sha.encode("utf-8"), salt).decode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a platform_admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default=None)
    args = parser.parse_args()

    email = args.email.strip().lower()
    pw_hash = _hash_password(args.password)

    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    row = cur.fetchone()

    if row:
        user_id = row[0]
        cur.execute(
            """
            UPDATE users
               SET password_hash  = %s,
                   full_name      = COALESCE(%s, full_name),
                   email_verified = TRUE,
                   status         = 'active',
                   platform_role  = 'platform_admin',
                   updated_at     = NOW()
             WHERE id = %s
            """,
            (pw_hash, args.full_name, user_id),
        )
        action = "updated"
    else:
        user_id = uuid4()
        cur.execute(
            """
            INSERT INTO users
                (id, email, password_hash, full_name, email_verified,
                 status, platform_role, created_at, updated_at)
            VALUES
                (%s, %s, %s, %s, TRUE, 'active', 'platform_admin', NOW(), NOW())
            """,
            (str(user_id), email, pw_hash, args.full_name),
        )
        action = "created"

    cur.close()
    conn.close()

    print(f"\u2713 platform_admin {action}: {email} (id={user_id})")
    print("  Password set. You can log in at /login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
