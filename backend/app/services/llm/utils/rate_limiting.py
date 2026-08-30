"""
Rate limiting utilities for API endpoints
"""

import logging
from datetime import datetime

import redis
from fastapi import HTTPException, Request, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Request-level rate limiting"""

    def __init__(self, requests_per_minute: int = 10, requests_per_hour: int = 100):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour

        try:
            # Parse Redis URL
            redis_url = settings.REDIS_URL
            if redis_url.startswith("redis://"):
                redis_url = redis_url[8:]

            parts = redis_url.split("/")
            host_port = parts[0].split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 6379
            db = int(parts[1]) if len(parts) > 1 else 0

            self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.redis_client.ping()
            self.enabled = True
            logger.info("✅ Rate limiter initialized")
        except Exception as e:
            logger.warning(f"⚠️ Rate limiter disabled: {e}")
            self.enabled = False
            self.redis_client = None

    def get_client_identifier(self, request: Request) -> str:
        """Get client identifier from request"""
        # Try to get user ID from request state (set by auth middleware)
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        # Fall back to IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        client_host = request.client.host if request.client else "unknown"
        return f"ip:{client_host}"

    async def check_rate_limit(self, request: Request, endpoint: str = "api") -> None:
        """Check rate limit and raise exception if exceeded"""
        if not self.enabled:
            return

        try:
            client_id = self.get_client_identifier(request)

            # Check minute limit
            minute_key = f"rate_limit:{endpoint}:{client_id}:minute:{datetime.utcnow().strftime('%Y%m%d%H%M')}"
            minute_count = int(self.redis_client.get(minute_key) or 0)

            if minute_count >= self.requests_per_minute:
                logger.warning(f"⚠️ Rate limit exceeded (minute) for {client_id} on {endpoint}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": self.requests_per_minute,
                        "period": "minute",
                        "retry_after": 60,
                    },
                )

            # Check hour limit
            hour_key = (
                f"rate_limit:{endpoint}:{client_id}:hour:{datetime.utcnow().strftime('%Y%m%d%H')}"
            )
            hour_count = int(self.redis_client.get(hour_key) or 0)

            if hour_count >= self.requests_per_hour:
                logger.warning(f"⚠️ Rate limit exceeded (hour) for {client_id} on {endpoint}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": self.requests_per_hour,
                        "period": "hour",
                        "retry_after": 3600,
                    },
                )

            # Increment counters
            pipe = self.redis_client.pipeline()
            pipe.incr(minute_key)
            pipe.expire(minute_key, 60)
            pipe.incr(hour_key)
            pipe.expire(hour_key, 3600)
            pipe.execute()

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Allow on error

    def get_remaining_requests(self, client_id: str, endpoint: str = "api") -> dict:
        """Get remaining requests for client"""
        if not self.enabled:
            return {"minute": self.requests_per_minute, "hour": self.requests_per_hour}

        try:
            minute_key = f"rate_limit:{endpoint}:{client_id}:minute:{datetime.utcnow().strftime('%Y%m%d%H%M')}"
            hour_key = (
                f"rate_limit:{endpoint}:{client_id}:hour:{datetime.utcnow().strftime('%Y%m%d%H')}"
            )

            minute_count = int(self.redis_client.get(minute_key) or 0)
            hour_count = int(self.redis_client.get(hour_key) or 0)

            return {
                "minute": max(0, self.requests_per_minute - minute_count),
                "hour": max(0, self.requests_per_hour - hour_count),
            }
        except Exception as e:
            logger.error(f"Get remaining requests error: {e}")
            return {"minute": self.requests_per_minute, "hour": self.requests_per_hour}


# Create singleton instances for different endpoints
flow_builder_rate_limiter = RateLimiter(requests_per_minute=10, requests_per_hour=100)

general_rate_limiter = RateLimiter(requests_per_minute=60, requests_per_hour=1000)


# Dependency for FastAPI routes
async def rate_limit_dependency(request: Request):
    """FastAPI dependency for rate limiting"""
    await general_rate_limiter.check_rate_limit(request)


async def flow_builder_rate_limit(request: Request):
    """FastAPI dependency for flow builder rate limiting"""
    await flow_builder_rate_limiter.check_rate_limit(request, endpoint="flow_builder")
