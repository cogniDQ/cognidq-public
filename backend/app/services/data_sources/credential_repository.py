"""
F004 — Credential repository layer
=====================================

Provides:
* ``CredentialRepository`` — CRUD operations against
  ``control.data_source_credentials``

Design notes
------------
* Credentials are stored as Fernet-encrypted BYTEA.
* When credentials are rotated the old credential is marked with
  ``superseded_at`` rather than deleted, creating an audit trail.
* The repository deals only with bytes; serialisation/encryption is the
  responsibility of ``credential_service.py``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.data_sources.models import DataSourceCredential

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class CredentialNotFoundError(Exception):
    """Raised when a credential row cannot be found by its UUID."""


# ─────────────────────────────────────────────────────────────────────────────
# SQL constants
# ─────────────────────────────────────────────────────────────────────────────

_INSERT_SQL = """
INSERT INTO control.data_source_credentials (
    credential_id, data_source_id, source_type, encrypted_payload, created_by
) VALUES (
    :credential_id, CAST(:data_source_id AS UUID), :source_type, :encrypted_payload, CAST(:created_by AS UUID)
)
RETURNING credential_id, created_at
"""

_SELECT_BY_ID_SQL = """
SELECT
    credential_id, data_source_id, source_type,
    encrypted_payload, created_at, created_by, superseded_at
FROM control.data_source_credentials
WHERE credential_id = CAST(:credential_id AS UUID)
"""

_SUPERSEDE_SQL = """
UPDATE control.data_source_credentials
SET superseded_at = :now
WHERE credential_id = CAST(:credential_id AS UUID)
  AND superseded_at IS NULL
"""


# ─────────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────────


class CredentialRepository:
    """
    All SQL operations against ``control.data_source_credentials``.

    Every public method accepts a SQLAlchemy ``Session`` as its first
    argument so the service layer can wrap operations in one transaction.
    """

    def create(
        self,
        db: Session,
        *,
        data_source_id: UUID,
        source_type: str,
        encrypted_payload: bytes,
        created_by: UUID,
    ) -> DataSourceCredential:
        """Insert a new credential row and return the domain model."""
        datetime.now(UTC)
        cred_id = uuid.uuid4()
        result = db.execute(
            text(_INSERT_SQL),
            {
                "credential_id": str(cred_id),
                "data_source_id": str(data_source_id),
                "source_type": source_type,
                "encrypted_payload": encrypted_payload,
                "created_by": str(created_by),
            },
        )
        row = result.fetchone()
        return DataSourceCredential(
            credential_id=row[0],
            data_source_id=data_source_id,
            source_type=source_type,
            encrypted_payload=encrypted_payload,
            created_by=created_by,
            created_at=row[1],
        )

    def find_by_id(
        self,
        db: Session,
        *,
        credential_id: UUID,
    ) -> DataSourceCredential:
        result = db.execute(
            text(_SELECT_BY_ID_SQL),
            {"credential_id": str(credential_id)},
        )
        row = result.fetchone()
        if row is None:
            raise CredentialNotFoundError(f"Credential {credential_id} not found.")
        return DataSourceCredential(
            credential_id=row[0],
            data_source_id=row[1],
            source_type=row[2],
            encrypted_payload=bytes(row[3]),
            created_at=row[4],
            created_by=row[5],
            superseded_at=row[6],
        )

    def supersede(
        self,
        db: Session,
        *,
        credential_id: UUID,
    ) -> None:
        """Mark an existing credential as superseded (soft rotation)."""
        now = datetime.now(UTC)
        db.execute(
            text(_SUPERSEDE_SQL),
            {"credential_id": str(credential_id), "now": now},
        )
