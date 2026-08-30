"""
Cost tracking utilities for LLM usage
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class CostTracker:
    """Track LLM costs"""

    # Pricing per 1000 tokens (as of 2024)
    PRICING = {
        "gpt-4-turbo-preview": {
            "input": 0.01,  # $0.01 per 1K input tokens
            "output": 0.03,  # $0.03 per 1K output tokens
        },
        "gpt-4o": {
            "input": 0.005,  # $0.005 per 1K input tokens
            "output": 0.015,  # $0.015 per 1K output tokens
        },
        "gpt-4": {"input": 0.03, "output": 0.06},
        "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        "gpt-3.5-turbo-16k": {"input": 0.003, "output": 0.004},
    }

    def __init__(self):
        self.session_costs = []
        self.total_tokens = 0
        self.total_cost = 0.0

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for LLM call"""
        pricing = self.PRICING.get(model, self.PRICING["gpt-4-turbo-preview"])
        cost = (input_tokens / 1000) * pricing["input"] + (output_tokens / 1000) * pricing["output"]
        return cost

    def log_usage(
        self, model: str, usage: dict[str, Any], operation: str, metadata: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Log cost and usage for monitoring"""
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

        cost = self.calculate_cost(model, input_tokens, output_tokens)

        # Track in session
        self.total_tokens += total_tokens
        self.total_cost += cost

        usage_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "model": model,
            "operation": operation,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost": cost,
            "metadata": metadata or {},
        }

        self.session_costs.append(usage_record)

        logger.info(
            f"💰 Cost for {operation}: ${cost:.4f} (model: {model}, tokens: {total_tokens})"
        )

        return usage_record

    def get_session_summary(self) -> dict[str, Any]:
        """Get summary of session costs"""
        if not self.session_costs:
            return {
                "total_requests": 0,
                "total_tokens": 0,
                "total_cost": 0.0,
                "by_operation": {},
                "by_model": {},
            }

        # Aggregate by operation
        by_operation = {}
        for record in self.session_costs:
            op = record["operation"]
            if op not in by_operation:
                by_operation[op] = {"count": 0, "total_tokens": 0, "total_cost": 0.0}
            by_operation[op]["count"] += 1
            by_operation[op]["total_tokens"] += record["total_tokens"]
            by_operation[op]["total_cost"] += record["cost"]

        # Aggregate by model
        by_model = {}
        for record in self.session_costs:
            model = record["model"]
            if model not in by_model:
                by_model[model] = {"count": 0, "total_tokens": 0, "total_cost": 0.0}
            by_model[model]["count"] += 1
            by_model[model]["total_tokens"] += record["total_tokens"]
            by_model[model]["total_cost"] += record["cost"]

        return {
            "total_requests": len(self.session_costs),
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "by_operation": by_operation,
            "by_model": by_model,
            "average_cost_per_request": self.total_cost / len(self.session_costs)
            if self.session_costs
            else 0,
        }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        # Rough estimation: 1 token ~= 4 characters
        # More accurate would use tiktoken, but this is good enough for estimation
        return len(text) // 4 + 100  # Add overhead

    def reset(self):
        """Reset session tracking"""
        self.session_costs = []
        self.total_tokens = 0
        self.total_cost = 0.0
        logger.info("🔄 Cost tracker reset")


# Singleton instance
cost_tracker = CostTracker()


class TokenRateLimiter:
    """Rate limiter based on token usage"""

    def __init__(self, max_tokens_per_minute: int = 100000):
        self.max_tokens_per_minute = max_tokens_per_minute
        try:
            import redis

            from app.core.config import settings

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
            logger.info("✅ Token rate limiter initialized")
        except Exception as e:
            logger.warning(f"⚠️ Token rate limiter disabled: {e}")
            self.enabled = False
            self.redis_client = None

    async def check_limit(self, user_id: str, estimated_tokens: int) -> bool:
        """Check if user is within rate limit"""
        if not self.enabled:
            return True

        try:
            key = f"token_limit:{user_id}:{datetime.utcnow().strftime('%Y%m%d%H%M')}"

            current_usage = int(self.redis_client.get(key) or 0)

            if current_usage + estimated_tokens > self.max_tokens_per_minute:
                logger.warning(
                    f"⚠️ Rate limit exceeded for user {user_id}: "
                    f"{current_usage + estimated_tokens}/{self.max_tokens_per_minute} tokens"
                )
                return False

            # Increment usage
            pipe = self.redis_client.pipeline()
            pipe.incrby(key, estimated_tokens)
            pipe.expire(key, 60)  # Expire after 1 minute
            pipe.execute()

            return True

        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            return True  # Allow on error

    def get_current_usage(self, user_id: str) -> int:
        """Get current token usage for user"""
        if not self.enabled:
            return 0

        try:
            key = f"token_limit:{user_id}:{datetime.utcnow().strftime('%Y%m%d%H%M')}"
            return int(self.redis_client.get(key) or 0)
        except Exception as e:
            logger.error(f"Get usage error: {e}")
            return 0


# Singleton instance
token_limiter = TokenRateLimiter()
