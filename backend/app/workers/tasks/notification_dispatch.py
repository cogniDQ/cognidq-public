"""
Notification Dispatch — Celery Task
=====================================

Periodic task that drains pending/retrying NotificationEvent rows by calling
``NotificationDispatcher.dispatch_pending`` across all workspaces. Wired into
Celery Beat in ``celery_app.py`` at a 5-minute cadence (configurable).
"""

from __future__ import annotations

import logging

from celery import Task

# Importing app.main triggers the same model-registration order as the FastAPI
# backend, ensuring SQLAlchemy mappers fully configure (otherwise some
# string-referenced relationships fail in worker context).
import app.main  # noqa: F401  pylint: disable=unused-import
from app.models.database import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="notification.dispatch_pending")
def dispatch_pending_notifications(self: Task, batch_size: int = 100) -> dict:
    """Drain pending/retrying notifications globally."""
    from app.services.alerts.notification_dispatcher import NotificationDispatcher

    logger.info("notification.dispatch_pending task started (batch_size=%s)", batch_size)
    db = SessionLocal()
    try:
        counts = NotificationDispatcher().dispatch_pending(db, batch_size=batch_size)
        logger.info("notification.dispatch_pending finished: %s", counts)
        return counts
    except Exception as exc:
        logger.error("notification.dispatch_pending error: %s", exc, exc_info=True)
        raise
    finally:
        db.close()
