"""
F134 P05 — Admin Demo Request Service

Business logic for the admin review queue:
  - list with filters/pagination
  - detail lookup by ID
  - approve (transition + create ProvisioningJob stub)
  - reject (transition + email stub)
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.lib.time import Clock, SystemClock
from app.services.sandbox.demo_request_repository import DemoRequestRepository
from app.services.sandbox.provisioning_job_repository import ProvisioningJobRepository


def emit_sandbox_rejected_email(request_row: dict, reason: str) -> None:  # noqa: ARG001
    """
    Fire-and-forget rejection email stub.
    Will be wired to real dispatcher in P07/P08.
    """
    pass


class AdminDemoRequestService:
    def __init__(
        self,
        db: Session,
        clock: Clock | None = None,
        request_repo: DemoRequestRepository | None = None,
        job_repo: ProvisioningJobRepository | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._request_repo = request_repo or DemoRequestRepository(db)
        self._job_repo = job_repo or ProvisioningJobRepository(db)

    def list_requests(
        self,
        *,
        status: str | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        return self._request_repo.list_with_filters(
            status=status,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    def get_request(self, request_id: UUID) -> dict | None:
        return self._request_repo.find_by_id(request_id)

    def approve_request(
        self,
        *,
        request_id: UUID,
        decided_by: UUID,
        template_id: str,
        duration_days: int,
        access_profile_code: str,
        tags: list[str] | None = None,
        internal_note: str | None = None,
    ) -> dict:
        """
        Transition request to 'approved' and create a ProvisioningJob row.
        Enqueuing the Celery task is handled in P07; here we only create
        the job row (status='pending') as an idempotency anchor.
        """
        # Update the request status
        updated = self._request_repo.update_status(
            request_id=request_id,
            status="approved",
            decided_by=decided_by,
            set_decided_at=True,
            internal_note=internal_note,
            admin_tags=tags or [],
        )

        # Create a ProvisioningJob row (Celery task enqueued in P07)
        # template_id, duration_days, access_profile_code are stored on the
        # approved request row; the provisioning worker reads them from there.
        self._job_repo.create(
            demo_request_id=request_id,
        )

        return updated

    def reject_request(
        self,
        *,
        request_id: UUID,
        decided_by: UUID,
        reason: str,
        internal_note: str | None = None,
    ) -> dict:
        """
        Transition request to 'rejected' and emit rejection email stub.
        """
        updated = self._request_repo.update_status(
            request_id=request_id,
            status="rejected",
            decided_by=decided_by,
            set_decided_at=True,
            rejection_reason=reason,
            internal_note=internal_note,
        )
        emit_sandbox_rejected_email(updated, reason)
        return updated
