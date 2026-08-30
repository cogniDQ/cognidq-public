"""
F134 P09 — SandboxService

Lifecycle operations for sandbox environments:
  - extend(sandbox_id, note, admin_id, extra_days, clock)
  - suspend(sandbox_id, admin_id, reason)
  - archive(sandbox_id, admin_id)
  - delete(sandbox_id, admin_id, force)
  - scan_expiring(clock) — sends reminders and suspends expired sandboxes
  - cleanup_expired(clock) — archives expired sandboxes past grace period

All mutating operations emit a stub audit/email call that will be wired
to the real dispatcher in P12.
"""

from __future__ import annotations

import logging
from datetime import UTC, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.lib.time import Clock, SystemClock
from app.services.sandbox.sandbox_environment_repository import (
    SandboxEnvironmentRepository,
)
from app.services.sandbox.sandbox_extension_repository import (
    SandboxExtensionRepository,
)
from app.services.sandbox.validation.extension_validation import (
    validate_extension,
)

logger = logging.getLogger(__name__)

# Default extension period
_DEFAULT_EXTENSION_DAYS = 7
# Grace period before archived sandbox is eligible for hard-delete
_DEFAULT_GRACE_DAYS = 14


# ── Email / audit stubs ───────────────────────────────────────────────────────


def _emit_extension_granted_email(sandbox_id: UUID, days: int) -> None:
    logger.info("STUB: extension_granted email for sandbox %s (+%d days)", sandbox_id, days)


def _emit_expiration_reminder_email(sandbox_id: UUID, hours_remaining: int) -> None:
    logger.info("STUB: expiration_reminder_%dh email for sandbox %s", hours_remaining, sandbox_id)


def _emit_sandbox_expired_email(sandbox_id: UUID) -> None:
    logger.info("STUB: sandbox_expired email for sandbox %s", sandbox_id)


def _emit_audit(action: str, sandbox_id: UUID, actor_id: UUID | None) -> None:
    logger.info("STUB: audit action=%s sandbox=%s actor=%s", action, sandbox_id, actor_id)


# ── Custom exceptions ─────────────────────────────────────────────────────────


class SandboxNotFoundError(ValueError):
    """Raised when the requested sandbox does not exist."""


class SandboxStateError(ValueError):
    """Raised when a lifecycle transition is not valid from the current state."""


class SandboxValidationError(ValueError):
    """Raised when a request violates a business rule (e.g. max extensions)."""


# ── SandboxService ────────────────────────────────────────────────────────────


class SandboxService:
    """
    Lifecycle operations for sandbox environments.

    Parameters
    ----------
    db :
        SQLAlchemy session.
    clock :
        Clock implementation (defaults to SystemClock for production).
    env_repo, ext_repo :
        Repository overrides for unit testing.
    """

    def __init__(
        self,
        db: Session,
        *,
        clock: Clock | None = None,
        env_repo: SandboxEnvironmentRepository | None = None,
        ext_repo: SandboxExtensionRepository | None = None,
    ) -> None:
        self._db = db
        self._clock = clock or SystemClock()
        self._env_repo = env_repo or SandboxEnvironmentRepository(db)
        self._ext_repo = ext_repo or SandboxExtensionRepository(db)

    # ── Public: admin lifecycle mutations ─────────────────────────────────

    def extend(
        self,
        *,
        sandbox_id: UUID,
        note: str,
        admin_id: UUID | None = None,
        extra_days: int = _DEFAULT_EXTENSION_DAYS,
    ) -> dict:
        """
        Extend the sandbox expiry by ``extra_days``.

        Validates:
          - note ≥ 10 chars
          - current extension_count < MAX_EXTENSIONS (2)
        """
        sandbox = self._require_sandbox(sandbox_id)
        ext_count = int(sandbox.get("extension_count") or 0)

        errors = validate_extension(note=note, current_extension_count=ext_count)
        if errors:
            field, msg = errors[0]
            raise SandboxValidationError(f"{field}: {msg}")

        old_expires_at = sandbox.get("expires_at")
        if old_expires_at is None:
            old_expires_at = self._clock.utcnow()
        if not old_expires_at.tzinfo:
            old_expires_at = old_expires_at.replace(tzinfo=UTC)

        new_expires_at = old_expires_at + timedelta(days=extra_days)

        # Record extension audit row
        self._ext_repo.create(
            sandbox_id=sandbox_id,
            extended_by=admin_id,
            extension_days=extra_days,
            note=note,
            previous_expires_at=old_expires_at,
            new_expires_at=new_expires_at,
        )

        # Update sandbox expiry and increment counter
        updated = self._env_repo.increment_extension(
            sandbox_id=sandbox_id,
            new_expires_at=new_expires_at,
        )

        _emit_extension_granted_email(sandbox_id, extra_days)
        _emit_audit("sandbox_extended", sandbox_id, admin_id)

        return updated or sandbox

    def suspend(
        self,
        *,
        sandbox_id: UUID,
        admin_id: UUID | None = None,
        reason: str | None = None,
    ) -> dict:
        """Suspend an active sandbox (stops user access)."""
        sandbox = self._require_sandbox(sandbox_id)

        if sandbox["status"] in ("suspended", "archived", "deleted"):
            raise SandboxStateError(f"Cannot suspend sandbox in status '{sandbox['status']}'.")

        updated = self._env_repo.update_status(
            sandbox_id=sandbox_id,
            status="suspended",
            set_suspended_at=True,
        )
        _emit_audit("sandbox_suspended", sandbox_id, admin_id)
        return updated or sandbox

    def archive(
        self,
        *,
        sandbox_id: UUID,
        admin_id: UUID | None = None,
    ) -> dict:
        """Archive a suspended or expired sandbox."""
        sandbox = self._require_sandbox(sandbox_id)

        if sandbox["status"] in ("active", "provisioning"):
            raise SandboxStateError("Suspend the sandbox before archiving.")
        if sandbox["status"] in ("archived", "deleted"):
            raise SandboxStateError(f"Sandbox is already '{sandbox['status']}'.")

        updated = self._env_repo.update_status(
            sandbox_id=sandbox_id,
            status="archived",
            set_archived_at=True,
        )
        _emit_audit("sandbox_archived", sandbox_id, admin_id)
        return updated or sandbox

    def delete(
        self,
        *,
        sandbox_id: UUID,
        admin_id: UUID | None = None,
        force: bool = False,
    ) -> None:
        """Soft-delete an archived sandbox (marks status='deleted').

        If *force=True* the sandbox may be in any non-deleted state.
        """
        sandbox = self._require_sandbox(sandbox_id)

        if sandbox["status"] == "deleted":
            raise SandboxStateError("Sandbox is already deleted.")

        if not force and sandbox["status"] != "archived":
            raise SandboxStateError("Archive the sandbox before deleting, or use force=True.")

        self._env_repo.update_status(
            sandbox_id=sandbox_id,
            status="deleted",
            set_deleted_at=True,
        )
        _emit_audit("sandbox_deleted", sandbox_id, admin_id)

    # ── Public: scanner / cleanup workers ────────────────────────────────

    def scan_expiring(
        self,
        *,
        reminder_windows: tuple[int, ...] = (48, 24),
        grace_hours: int = 0,
    ) -> dict:
        """
        Scan sandboxes and:
          1. Emit reminder emails at each window in *reminder_windows* (hours before expiry).
          2. Suspend sandboxes that are past expiry.

        Returns a summary dict of actions taken.
        """
        now = self._clock.utcnow()
        reminders_sent: int = 0
        suspended: int = 0

        # 1. Reminders
        for hours in reminder_windows:
            threshold = now + timedelta(hours=hours)
            candidates = self._env_repo.list_expiring(threshold_at=threshold)
            for row in candidates:
                if row.get("status") != "active":
                    continue
                exp = row.get("expires_at")
                if exp is None:
                    continue
                if not exp.tzinfo:
                    exp = exp.replace(tzinfo=UTC)
                hours_left = (exp - now).total_seconds() / 3600
                # Only fire the reminder for the correct window (±15 min hysteresis)
                if hours - 0.25 <= hours_left <= hours + 0.25:
                    _emit_expiration_reminder_email(UUID(str(row["id"])), hours)
                    reminders_sent += 1

        # 2. Suspend expired active sandboxes
        now + timedelta(hours=grace_hours)
        expired_candidates = self._env_repo.list_expiring(threshold_at=now)
        for row in expired_candidates:
            if row.get("status") != "active":
                continue
            exp = row.get("expires_at")
            if exp is None:
                continue
            if not exp.tzinfo:
                exp = exp.replace(tzinfo=UTC)
            if exp <= now:
                self._env_repo.update_status(
                    sandbox_id=UUID(str(row["id"])),
                    status="expired",
                    set_suspended_at=False,
                )
                _emit_sandbox_expired_email(UUID(str(row["id"])))
                suspended += 1

        return {
            "reminders_sent": reminders_sent,
            "expired": suspended,
            "scanned_at": now.isoformat(),
        }

    def cleanup_expired(
        self,
        *,
        grace_days: int = _DEFAULT_GRACE_DAYS,
        batch_limit: int = 50,
    ) -> dict:
        """
        Archive and soft-delete sandboxes that have been expired longer
        than the grace period.

        Returns a summary dict.
        """
        now = self._clock.utcnow()
        threshold_at = now - timedelta(days=grace_days)
        candidates = self._env_repo.list_ready_for_cleanup(
            threshold_at=threshold_at,
            limit=batch_limit,
        )
        archived = 0
        for row in candidates:
            if row.get("status") not in ("expired", "suspended"):
                continue
            sid = UUID(str(row["id"]))
            try:
                self._env_repo.update_status(
                    sandbox_id=sid,
                    status="archived",
                    set_archived_at=True,
                )
                archived += 1
            except Exception as exc:
                logger.warning("cleanup_expired: failed to archive %s — %s", sid, exc)

        return {"archived": archived, "processed_at": now.isoformat()}

    # ── Private helpers ───────────────────────────────────────────────────

    def _require_sandbox(self, sandbox_id: UUID) -> dict:
        row = self._env_repo.find_by_id(sandbox_id)
        if row is None:
            raise SandboxNotFoundError(f"Sandbox {sandbox_id} not found.")
        return row
