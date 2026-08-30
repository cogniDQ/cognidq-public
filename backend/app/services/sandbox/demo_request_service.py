"""
F134 P04 — Public Demo Request Service

Handles business logic for the public intake flow:
  - duplicate active request detection (BR-001)
  - insert demo request row
  - public status lookup

No rate limiting here — that is applied at the HTTP layer (FastAPI middleware or
a future P04 enhancement). Email dispatch is a fire-and-forget stub that will be
wired to the real dispatcher in P08.
"""

from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.lib.time import Clock, SystemClock
from app.services.sandbox.demo_request_repository import DemoRequestRepository
from app.services.sandbox.validation.demo_request_validation import is_personal_email

_ACTIVE_STATUSES = ("submitted", "under_review", "approved", "provisioned", "active")


def _generate_public_token() -> str:
    """48-byte URL-safe token — 64 chars in base64url."""
    return secrets.token_urlsafe(48)


class DemoRequestService:
    def __init__(
        self,
        db: Session,
        clock: Clock | None = None,
        repo: DemoRequestRepository | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._repo = repo or DemoRequestRepository(db)

    # ── Public helpers ─────────────────────────────────────────────────────────

    def find_active_by_email(self, email: str) -> dict | None:
        """Return active DemoRequest dict for email or None (BR-001)."""
        return self._repo.find_active_by_email(email)

    def create(
        self,
        *,
        work_email: str,
        first_name: str,
        last_name: str,
        company_name: str,
        team_size: str,
        primary_use_case: str,
        consent: bool,
        job_title: str | None = None,
        country: str | None = None,
        stack: dict | None = None,
        heard_about_us: str | None = None,
        source_ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        """
        Insert a new DemoRequest row.  Caller is responsible for duplicate check.
        """
        flagged = is_personal_email(work_email)
        public_token = _generate_public_token()
        return self._repo.create(
            work_email=work_email,
            first_name=first_name,
            last_name=last_name,
            company_name=company_name,
            job_title=job_title,
            team_size=team_size,
            country=country,
            primary_use_case=primary_use_case,
            stack=stack or {},
            heard_about_us=heard_about_us,
            consent=consent,
            is_personal_email=flagged,
            public_status_token=public_token,
            source_ip=source_ip,
            user_agent=user_agent,
            created_at=self._clock.utcnow(),
        )

    def get_status(self, public_token: str) -> dict | None:
        """Return a minimal status dict or None if token unknown."""
        return self._repo.find_by_public_token(public_token)


def emit_request_received_email(request_row: dict) -> None:  # noqa: ARG001
    """
    Fire-and-forget email stub.

    Will be replaced with the real Celery task call in P08.
    Current implementation is intentionally a no-op so the API endpoint
    can be tested without an email infrastructure dependency.
    """
    pass
