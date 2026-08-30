"""
F134 — Demo Sandbox Provisioning
ProvisioningJobRepository: DB operations for control.provisioning_jobs.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_INSERT_SQL = text("""
    INSERT INTO control.provisioning_jobs (
        id, demo_request_id, sandbox_id, status, celery_task_id
    ) VALUES (
        :id,
        CAST(:demo_request_id AS UUID),
        CAST(:sandbox_id AS UUID),
        'pending',
        :celery_task_id
    )
    RETURNING id::text, demo_request_id::text, status, created_at
""")

_FIND_BY_ID_SQL = text("""
    SELECT
        id::text, demo_request_id::text, sandbox_id::text,
        status, attempt_count, last_error,
        started_at, finished_at, celery_task_id,
        created_at, updated_at
    FROM control.provisioning_jobs
    WHERE id = :id
""")

_FIND_LATEST_FOR_REQUEST_SQL = text("""
    SELECT
        id::text, demo_request_id::text, sandbox_id::text,
        status, attempt_count, last_error,
        started_at, finished_at, celery_task_id,
        created_at, updated_at
    FROM control.provisioning_jobs
    WHERE demo_request_id = CAST(:demo_request_id AS UUID)
    ORDER BY created_at DESC
    LIMIT 1
""")

_UPDATE_SQL = text("""
    UPDATE control.provisioning_jobs
    SET
        status        = COALESCE(:status, status),
        attempt_count = attempt_count + :increment_attempt,
        last_error    = COALESCE(:last_error, last_error),
        started_at    = CASE WHEN :set_started_at THEN NOW() ELSE started_at END,
        finished_at   = CASE WHEN :set_finished_at THEN NOW() ELSE finished_at END,
        sandbox_id    = COALESCE(CAST(:sandbox_id AS UUID), sandbox_id),
        celery_task_id= COALESCE(:celery_task_id, celery_task_id),
        updated_at    = NOW()
    WHERE id = :id
    RETURNING id::text, status, attempt_count, updated_at
""")


class ProvisioningJobRepository:
    """Data access for control.provisioning_jobs."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        demo_request_id: UUID,
        sandbox_id: UUID | None = None,
        celery_task_id: str | None = None,
    ) -> dict[str, Any]:
        row = self._db.execute(
            _INSERT_SQL,
            {
                "id": str(uuid4()),
                "demo_request_id": str(demo_request_id),
                "sandbox_id": str(sandbox_id) if sandbox_id else None,
                "celery_task_id": celery_task_id,
            },
        ).fetchone()
        return dict(row._mapping)

    def find_by_id(self, job_id: UUID) -> dict[str, Any] | None:
        row = self._db.execute(_FIND_BY_ID_SQL, {"id": str(job_id)}).fetchone()
        return dict(row._mapping) if row else None

    def find_latest_for_request(self, demo_request_id: UUID) -> dict[str, Any] | None:
        row = self._db.execute(
            _FIND_LATEST_FOR_REQUEST_SQL,
            {"demo_request_id": str(demo_request_id)},
        ).fetchone()
        return dict(row._mapping) if row else None

    def update(
        self,
        *,
        job_id: UUID,
        status: str | None = None,
        increment_attempt: int = 0,
        last_error: str | None = None,
        set_started_at: bool = False,
        set_finished_at: bool = False,
        sandbox_id: UUID | None = None,
        celery_task_id: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._db.execute(
            _UPDATE_SQL,
            {
                "id": str(job_id),
                "status": status,
                "increment_attempt": increment_attempt,
                "last_error": last_error,
                "set_started_at": set_started_at,
                "set_finished_at": set_finished_at,
                "sandbox_id": str(sandbox_id) if sandbox_id else None,
                "celery_task_id": celery_task_id,
            },
        ).fetchone()
        return dict(row._mapping) if row else None
