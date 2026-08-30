"""Redis-backed API rate limiting (slowapi / limits).

Global default limits come from ``RATE_LIMIT_PER_MINUTE`` /
``RATE_LIMIT_PER_HOUR``. Sensitive auth endpoints apply stricter,
per-IP limits on top of the global default (see
``app/api/v1/endpoints/auth.py``).

Uses Redis as the shared counter store so limits are enforced correctly
across multiple backend replicas, not just per-process.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    default_limits=[
        f"{settings.RATE_LIMIT_PER_MINUTE}/minute",
        f"{settings.RATE_LIMIT_PER_HOUR}/hour",
    ],
    headers_enabled=True,
)
