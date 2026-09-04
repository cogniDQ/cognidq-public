"""
Caching layer for Flow Builder responses
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class FlowBuilderCache:
    """Cache for flow builder responses"""

    def __init__(self):
        try:
            # Parse Redis URL to get host and port
            redis_url = settings.REDIS_URL
            if redis_url.startswith("redis://"):
                redis_url = redis_url[8:]

            parts = redis_url.split("/")
            host_port = parts[0].split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 6379
            db = int(parts[1]) if len(parts) > 1 else 0

            self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self.ttl = getattr(settings, "FLOW_BUILDER_CACHE_TTL", 300)  # Default 300 seconds
            self.enabled = getattr(settings, "ENABLE_FLOW_BUILDER_CACHE", True)

            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Redis cache initialized (host={host}, port={port}, db={db})")
        except Exception as e:
            logger.warning(f"⚠️ Redis cache initialization failed: {e}. Caching disabled.")
            self.enabled = False
            self.redis_client = None

    def _generate_cache_key(
        self, prompt: str, current_flow: dict[str, Any], available_sources: list
    ) -> str:
        """Generate cache key from request parameters"""
        # Create deterministic hash of inputs
        cache_input = {
            "prompt": prompt.lower().strip(),
            "flow_hash": self._hash_dict(current_flow),
            "sources_hash": self._hash_list(available_sources),
        }

        cache_str = json.dumps(cache_input, sort_keys=True)
        return f"flow_builder:{hashlib.sha256(cache_str.encode()).hexdigest()}"

    def _hash_dict(self, data: dict[str, Any]) -> str:
        """Hash dictionary for cache key"""
        # Not security-sensitive: used only to build a cache key, not for auth/integrity.
        return hashlib.md5(
            json.dumps(data, sort_keys=True).encode(), usedforsecurity=False
        ).hexdigest()

    def _hash_list(self, data: list) -> str:
        """Hash list for cache key"""
        # Only hash IDs to avoid column changes invalidating cache
        ids = [item.get("id") for item in data if isinstance(item, dict)]
        # Not security-sensitive: used only to build a cache key, not for auth/integrity.
        return hashlib.md5(json.dumps(sorted(ids)).encode(), usedforsecurity=False).hexdigest()

    def get(
        self, prompt: str, current_flow: dict[str, Any], available_sources: list
    ) -> dict[str, Any] | None:
        """Get cached response"""
        if not self.enabled or not self.redis_client:
            return None

        try:
            key = self._generate_cache_key(prompt, current_flow, available_sources)
            cached = self.redis_client.get(key)

            if cached:
                logger.info(f"✅ Cache HIT for key: {key[:16]}...")
                return json.loads(cached)

            logger.debug(f"❌ Cache MISS for key: {key[:16]}...")
            return None

        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None

    def set(
        self,
        prompt: str,
        current_flow: dict[str, Any],
        available_sources: list,
        response: dict[str, Any],
    ) -> bool:
        """Cache response"""
        if not self.enabled or not self.redis_client:
            return False

        try:
            key = self._generate_cache_key(prompt, current_flow, available_sources)

            # Add cache metadata
            cached_response = {
                **response,
                "cached_at": datetime.utcnow().isoformat(),
                "from_cache": True,
            }

            self.redis_client.setex(key, self.ttl, json.dumps(cached_response))

            logger.info(f"💾 Cached response for key: {key[:16]}... (TTL: {self.ttl}s)")
            return True

        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def invalidate_pattern(self, pattern: str):
        """Invalidate cache entries matching pattern"""
        if not self.enabled or not self.redis_client:
            return

        try:
            keys = self.redis_client.keys(f"flow_builder:{pattern}*")
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"🗑️ Invalidated {len(keys)} cache entries")
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")

    def clear_all(self):
        """Clear all flow builder cache entries"""
        if not self.enabled or not self.redis_client:
            return

        try:
            keys = self.redis_client.keys("flow_builder:*")
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"🗑️ Cleared {len(keys)} cache entries")
        except Exception as e:
            logger.error(f"Cache clear error: {e}")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        if not self.enabled or not self.redis_client:
            return {"enabled": False}

        try:
            keys = self.redis_client.keys("flow_builder:*")
            return {
                "enabled": True,
                "total_entries": len(keys),
                "ttl_seconds": self.ttl,
                "redis_info": {
                    "used_memory": self.redis_client.info("memory").get("used_memory_human"),
                    "connected_clients": self.redis_client.info("clients").get("connected_clients"),
                },
            }
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {"enabled": True, "error": str(e)}


# Singleton instance
flow_builder_cache = FlowBuilderCache()
