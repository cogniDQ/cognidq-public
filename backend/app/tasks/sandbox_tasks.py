"""
F134 P07 — Sandbox Celery Tasks

Celery task stubs for sandbox provisioning.
The real Celery app is wired in app.celery_app; importing it here would
require Celery to be installed and configured. For MVP we provide the
task logic as a plain function and a thin Celery wrapper.

IMPORTANT: Only import celery at call-time so unit tests don't require
           Celery to be installed.
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


def _get_celery_app():
    """Lazy import of Celery app to avoid import-time dependency."""
    try:
        from app.celery_app import celery_app  # type: ignore

        return celery_app
    except ImportError:
        return None


def provision_sandbox_task(job_id_str: str) -> dict:
    """
    Core provisioning logic called by the Celery task.

    Separated from the @app.task decorator so it can be unit-tested
    without a Celery broker.

    Parameters
    ----------
    job_id_str :
        UUID string of the provisioning_jobs row to process.

    Returns the sandbox_environment dict on success.
    """
    from app.core.config import settings
    from app.models.database import get_db_context
    from app.services.sandbox.provisioning_service import SandboxProvisioningService

    job_id = UUID(job_id_str)
    with get_db_context() as db:
        svc = SandboxProvisioningService(
            db,
            invitation_secret=settings.JWT_SECRET_KEY,
        )
        result = svc.provision(job_id=job_id)
        db.commit()
    return result


def enqueue_provision_sandbox(job_id: UUID) -> None:
    """
    Enqueue a provisioning job to Celery if available, otherwise run inline.

    Falls back to synchronous execution when Celery is not configured (dev/test).
    """
    celery_app = _get_celery_app()
    if celery_app is not None:
        celery_app.send_task(
            "app.tasks.sandbox_tasks.provision_sandbox",
            kwargs={"job_id_str": str(job_id)},
            countdown=0,
            max_retries=3,
        )
        logger.info("provision_sandbox task enqueued for job %s", job_id)
    else:
        logger.warning(
            "Celery not available — running provision_sandbox synchronously for job %s",
            job_id,
        )
        provision_sandbox_task(str(job_id))


# ---------------------------------------------------------------------------
# P09 — Lifecycle scanner tasks
# ---------------------------------------------------------------------------


def scan_expiring_sandboxes_task() -> dict:
    """
    Beat task: every 10 minutes.
    Sends reminder emails at 48h and 24h before expiry, suspends at 0h.
    """
    from app.models.database import get_db_context
    from app.services.sandbox.sandbox_service import SandboxService

    with get_db_context() as db:
        svc = SandboxService(db)
        result = svc.scan_expiring()
        db.commit()
    return result


def cleanup_expired_sandboxes_task(grace_days: int = 14) -> dict:
    """
    Beat task: every 1 hour.
    Archives and soft-deletes sandboxes past their grace period.
    """
    from app.models.database import get_db_context
    from app.services.sandbox.sandbox_service import SandboxService

    with get_db_context() as db:
        svc = SandboxService(db)
        result = svc.cleanup_expired(grace_days=grace_days)
        db.commit()
    return result


# ---------------------------------------------------------------------------
# P10 — Usage aggregation task
# ---------------------------------------------------------------------------


def aggregate_sandbox_usage_task() -> dict:
    """
    Beat task: every 5 minutes.
    Computes engagement scores for all active sandboxes and updates the DB.
    """
    from uuid import UUID

    from app.models.database import get_db_context
    from app.services.sandbox.sandbox_environment_repository import (
        SandboxEnvironmentRepository,
    )
    from app.services.sandbox.usage_tracking_service import UsageTrackingService

    updated = 0
    with get_db_context() as db:
        env_repo = SandboxEnvironmentRepository(db)
        rows, _ = env_repo.list_all(status="active", limit=500)
        svc = UsageTrackingService(db, env_repo=env_repo)
        for row in rows:
            try:
                svc.aggregate(sandbox_id=UUID(str(row["id"])))
                updated += 1
            except Exception as exc:
                logger.warning("aggregate_sandbox_usage: failed for %s — %s", row["id"], exc)
        db.commit()
    return {"sandboxes_updated": updated}
