"""
Celery application configuration
"""

import os

from celery import Celery

# Get Redis URL from environment, defaulting to localhost
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Initialize Celery app
celery_app = Celery(
    "dataquality_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.rule_validation",
        "app.workers.tasks.data_quality",
        "app.workers.tasks.rules",  # Rule execution tasks
        "app.workers.tasks.flows",  # Flow execution tasks
        "app.workers.tasks.escalation",  # F046 — Escalation for overdue SLA
        "app.workers.tasks.notification_dispatch",  # Periodic alert delivery loop
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    task_soft_time_limit=240,  # 4 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Celery Beat Schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "scheduled-rule-execution": {
        "task": "rules.scheduled_execution",
        "schedule": 60.0,  # Every minute
    },
    "cleanup-old-violations": {
        "task": "rules.cleanup_old_violations",
        "schedule": 86400.0,  # Daily at midnight
        "args": (90,),  # Keep 90 days of violations
    },
    "escalation-overdue-sla-check": {
        "task": "escalation.run_escalation_check",
        "schedule": 3600.0,  # Every hour
    },
    "notification-dispatch-pending": {
        "task": "notification.dispatch_pending",
        "schedule": 300.0,  # Every 5 minutes
    },
}

# Task routing (optional)
celery_app.conf.task_routes = {
    "app.workers.tasks.rule_validation.*": {"queue": "rule_validation"},
    "app.workers.tasks.data_quality.*": {"queue": "data_quality"},
    "rules.*": {"queue": "rules"},  # Rule execution queue
}

if __name__ == "__main__":
    celery_app.start()
