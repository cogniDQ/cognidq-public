"""
F046 — Escalation for Overdue SLA — Celery Task
=================================================

Periodic task that runs the escalation check on every beat tick.
Registered as ``escalation.run_escalation_check`` and wired into
Celery Beat in ``celery_app.py``.
"""

from __future__ import annotations

import logging

from celery import Task

from app.models.database import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="escalation.run_escalation_check")
def run_escalation_check(self: Task) -> dict:
    """
    Scan all workspaces for overdue open issues and log notification events
    for each matching ``issue_overdue`` alert rule.
    """
    from app.services.escalation.escalation_service import EscalationService

    logger.info("F046 escalation check task started")
    db = SessionLocal()
    try:
        result = EscalationService().run_escalation_check(db)
        logger.info("F046 escalation check task finished: %s", result.to_dict())
        return result.to_dict()
    except Exception as exc:
        logger.error("F046 escalation check task error: %s", exc, exc_info=True)
        raise
    finally:
        db.close()
