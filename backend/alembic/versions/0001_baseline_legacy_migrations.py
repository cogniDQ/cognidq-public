"""Baseline: replay the legacy hand-written SQL migrations.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-31

This revision replays every ``*.sql`` file that previously lived under
``backend/scripts/migrations/`` (executed in lexical filename order by
the old ``scripts/run_migrations.py`` runner) as a single Alembic
revision. This preserves the exact schema history without hand-rewriting
60 files individually, while giving the project a real ``alembic_version``
table to build future migrations on top of.

IMPORTANT: migration ``004_default_org_domain_team.sql`` has a hard-coded
foreign key to a bootstrap admin user row that must exist *before* it
runs. The old two-step flow (``scripts/bootstrap_fresh_db.py`` then
``scripts/run_migrations.py``) handled this by seeding that user between
migration 001 and 004. This revision replicates the same order so a
single ``alembic upgrade head`` is a complete, working bootstrap:

    1. Apply ``001_auth.sql`` (creates ``users``).
    2. Seed the bootstrap admin user (same UUID migration 004 references)
       with a placeholder password — CHANGE IT after first login.
    3. Apply all remaining migration files in order.
    4. Promote the seeded user to ``platform_role = 'platform_admin'``.

Fresh database:
    alembic upgrade head

Existing database that was already bootstrapped with the OLD
``scripts/bootstrap_fresh_db.py`` + ``scripts/run_migrations.py`` flow
(all 60 SQL files already applied, admin user already seeded):
    alembic stamp 0001_baseline
    (marks this revision as applied WITHOUT re-running anything, then
    ``alembic upgrade head`` will only apply revisions after it)
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence, Union

import bcrypt
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "migrations"

# UUID hard-coded in 004_default_org_domain_team.sql for the bootstrap user.
_BOOTSTRAP_USER_UUID = "63cae557-c3bc-4442-8592-58205e772aa6"
_BOOTSTRAP_EMAIL = "admin@example.com"
_BOOTSTRAP_PASSWORD = "change-me-strong-password"


def _hash_password(password: str) -> str:
    """Mirror ``User.set_password``: SHA-256 pre-hash, then bcrypt(rounds=12)."""
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(sha.encode("utf-8"), salt).decode("utf-8")


def upgrade() -> None:
    bind = op.get_bind()
    files = sorted(_LEGACY_MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        return

    # 1. Apply 001_auth.sql so the `users` table exists.
    first = files[0]
    if not first.name.startswith("001_"):
        raise RuntimeError(f"Expected first migration to start with '001_', got {first.name}")
    op.execute(first.read_text(encoding="utf-8"))

    # 2. Seed the bootstrap admin user *before* migration 004 (which has a
    # hard-coded FK to this user id). Uses a well-known placeholder password
    # that MUST be changed after first login.
    pw_hash = _hash_password(_BOOTSTRAP_PASSWORD)
    bind.execute(
        text(
            """
            INSERT INTO users
                (id, email, password_hash, full_name, email_verified,
                 status, created_at, updated_at)
            VALUES
                (:id, :email, :pw_hash, :full_name, TRUE, 'active', NOW(), NOW())
            ON CONFLICT (email) DO UPDATE
                SET password_hash  = EXCLUDED.password_hash,
                    email_verified = TRUE,
                    status         = 'active',
                    updated_at     = NOW()
            """
        ),
        {
            "id": _BOOTSTRAP_USER_UUID,
            "email": _BOOTSTRAP_EMAIL,
            "pw_hash": pw_hash,
            "full_name": "CogniDQ Admin",
        },
    )

    # 3. Apply all remaining migration files in order.
    for sql_file in files[1:]:
        sql_text = sql_file.read_text(encoding="utf-8")
        if sql_text.strip():
            op.execute(sql_text)

    # 4. Promote the seeded user to platform_admin (column added later).
    bind.execute(
        text("UPDATE users SET platform_role = 'platform_admin' WHERE email = :email"),
        {"email": _BOOTSTRAP_EMAIL},
    )

    print(
        "\n"
        "Bootstrap admin created:\n"
        f"  Email:    {_BOOTSTRAP_EMAIL}\n"
        f"  Password: {_BOOTSTRAP_PASSWORD}\n"
        "  CHANGE THIS PASSWORD after first login.\n"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "The legacy baseline cannot be downgraded automatically. "
        "Restore the database from a backup instead."
    )
