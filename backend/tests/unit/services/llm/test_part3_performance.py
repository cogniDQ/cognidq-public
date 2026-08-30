"""
Tests for Part 3 Performance Optimization Features

Tests caching, cost tracking, rate limiting, and retry logic.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from app.services.llm.utils.cache import FlowBuilderCache
from app.services.llm.utils.cost_tracker import CostTracker, TokenRateLimiter
from app.services.llm.utils.rate_limiting import RateLimiter
from app.services.llm.utils.retry_logic import LLMRetryHandler, RetryConfig, retry_on_error


class TestFlowBuilderCache:
    """Test caching functionality"""

    def test_cache_key_generation(self):
        """Test that cache keys are generated correctly"""
        cache = FlowBuilderCache()

        prompt1 = "Check completeness of email"
        flow1 = {"nodes": [], "connections": []}
        sources1 = [{"id": "1", "name": "customers"}]

        key1 = cache._generate_cache_key(prompt1, flow1, sources1)
        key2 = cache._generate_cache_key(prompt1, flow1, sources1)

        # Same inputs should generate same key
        assert key1 == key2
        assert key1.startswith("flow_builder:")

    def test_cache_key_sensitivity(self):
        """Test that cache keys change with different inputs"""
        cache = FlowBuilderCache()

        prompt1 = "Check completeness"
        prompt2 = "Check validity"
        flow = {"nodes": [], "connections": []}
        sources = []

        key1 = cache._generate_cache_key(prompt1, flow, sources)
        key2 = cache._generate_cache_key(prompt2, flow, sources)

        # Different prompts should generate different keys
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_cache_get_miss(self):
        """Test cache miss scenario"""
        cache = FlowBuilderCache()

        result = cache.get("test prompt", {"nodes": []}, [])

        # First access should be a miss
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """Test cache set and retrieve"""
        cache = FlowBuilderCache()

        if not cache.enabled:
            pytest.skip("Cache disabled (Redis not available)")

        prompt = "test prompt for cache"
        flow = {"nodes": []}
        sources = []
        response = {"success": True, "flow_updates": {"nodes": [{"id": "1"}]}}

        # Set cache
        cache.set(prompt, flow, sources, response)

        # Get from cache
        cached = cache.get(prompt, flow, sources)

        assert cached is not None
        assert cached["success"] == True
        assert cached["from_cache"] == True
        assert "cached_at" in cached

        # Clean up
        cache.clear_all()


class TestCostTracker:
    """Test cost tracking functionality"""

    def test_cost_calculation_gpt4(self):
        """Test cost calculation for GPT-4"""
        tracker = CostTracker()

        cost = tracker.calculate_cost(model="gpt-4o", input_tokens=1000, output_tokens=500)

        # $0.005 per 1K input + $0.015 per 1K output
        expected = (1000 / 1000 * 0.005) + (500 / 1000 * 0.015)
        assert cost == expected

    def test_cost_calculation_gpt35(self):
        """Test cost calculation for GPT-3.5"""
        tracker = CostTracker()

        cost = tracker.calculate_cost(model="gpt-3.5-turbo", input_tokens=2000, output_tokens=1000)

        # $0.0005 per 1K input + $0.0015 per 1K output
        expected = (2000 / 1000 * 0.0005) + (1000 / 1000 * 0.0015)
        assert cost == expected

    def test_log_usage(self):
        """Test usage logging"""
        tracker = CostTracker()
        tracker.reset()

        usage = {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}

        record = tracker.log_usage(model="gpt-4o", usage=usage, operation="parse_instructions")

        assert record["model"] == "gpt-4o"
        assert record["operation"] == "parse_instructions"
        assert record["total_tokens"] == 1500
        assert record["cost"] > 0
        assert tracker.total_tokens == 1500

    def test_session_summary(self):
        """Test session summary generation"""
        tracker = CostTracker()
        tracker.reset()

        # Log multiple operations
        tracker.log_usage("gpt-4o", {"prompt_tokens": 1000, "completion_tokens": 500}, "op1")
        tracker.log_usage("gpt-4o", {"prompt_tokens": 800, "completion_tokens": 400}, "op2")
        tracker.log_usage("gpt-3.5-turbo", {"prompt_tokens": 500, "completion_tokens": 200}, "op3")

        summary = tracker.get_session_summary()

        assert summary["total_requests"] == 3
        assert summary["total_tokens"] > 0
        assert summary["total_cost"] > 0
        assert len(summary["by_model"]) == 2
        assert "gpt-4o" in summary["by_model"]
        assert "gpt-3.5-turbo" in summary["by_model"]

    def test_token_estimation(self):
        """Test token estimation"""
        tracker = CostTracker()

        text = "This is a test prompt for token estimation"
        estimated = tracker.estimate_tokens(text)

        # Should be roughly len(text)/4 + overhead
        assert estimated > 0
        assert estimated > len(text) // 4


class TestRetryLogic:
    """Test retry functionality"""

    @pytest.mark.asyncio
    async def test_retry_on_success(self):
        """Test that successful calls don't retry"""
        call_count = 0

        @retry_on_error(RetryConfig(max_attempts=3))
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await successful_func()

        assert result == "success"
        assert call_count == 1  # Should only call once

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry on transient failures"""
        import httpx
        from openai import RateLimitError

        _fake_resp = httpx.Response(429, request=httpx.Request("GET", "https://api.openai.com"))

        call_count = 0

        @retry_on_error(RetryConfig(max_attempts=3, initial_delay=0.1, max_delay=0.2))
        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RateLimitError("Rate limit hit", response=_fake_resp, body=None)
            return "success"

        result = await failing_func()

        assert result == "success"
        assert call_count == 3  # Should retry twice

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test that retries are eventually exhausted"""
        import httpx
        from openai import RateLimitError

        _fake_resp = httpx.Response(429, request=httpx.Request("GET", "https://api.openai.com"))

        @retry_on_error(RetryConfig(max_attempts=3, initial_delay=0.1, max_delay=0.2))
        async def always_failing_func():
            raise RateLimitError("Always fails", response=_fake_resp, body=None)

        with pytest.raises(RateLimitError):
            await always_failing_func()

    @pytest.mark.asyncio
    async def test_retry_handler(self):
        """Test LLMRetryHandler"""
        import httpx
        from openai import RateLimitError

        _fake_resp = httpx.Response(429, request=httpx.Request("GET", "https://api.openai.com"))
        handler = LLMRetryHandler(RetryConfig(max_attempts=3, initial_delay=0.1))

        call_count = 0

        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RateLimitError("Test", response=_fake_resp, body=None)
            return "success"

        result = await handler.call_with_retry(test_func)

        assert result == "success"
        assert call_count == 2


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initialization"""
        limiter = RateLimiter(requests_per_minute=10, requests_per_hour=100)

        assert limiter.requests_per_minute == 10
        assert limiter.requests_per_hour == 100

    @pytest.mark.asyncio
    async def test_rate_limit_check_disabled(self):
        """Test that disabled rate limiter allows all requests"""
        limiter = RateLimiter()
        limiter.enabled = False

        # Create mock request
        mock_request = Mock()
        mock_request.client = Mock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        # Should not raise exception
        await limiter.check_rate_limit(mock_request)


class TestTokenRateLimiter:
    """Test token-based rate limiting"""

    @pytest.mark.asyncio
    async def test_token_limiter_allows_within_limit(self):
        """Test that requests within limit are allowed"""
        limiter = TokenRateLimiter(max_tokens_per_minute=10000)

        if not limiter.enabled:
            pytest.skip("Token limiter disabled (Redis not available)")

        # Small request should be allowed
        allowed = await limiter.check_limit("test_user", 1000)
        assert allowed == True

    @pytest.mark.asyncio
    async def test_token_limiter_blocks_over_limit(self):
        """Test that requests over limit are blocked"""
        limiter = TokenRateLimiter(max_tokens_per_minute=1000)

        if not limiter.enabled:
            pytest.skip("Token limiter disabled (Redis not available)")

        # Request that exceeds limit should be blocked
        allowed = await limiter.check_limit("test_user_2", 2000)
        assert allowed == False


class TestIntegration:
    """Integration tests for all Part 3 features"""

    @pytest.mark.asyncio
    async def test_cost_tracker_integration(self):
        """Test cost tracking with realistic usage"""
        tracker = CostTracker()
        tracker.reset()

        # Simulate a flow builder session
        operations = [
            ("parse_instructions", "gpt-4o", 1500, 500),
            ("match_sources", "gpt-4o", 1000, 300),
            ("generate_checks", "gpt-4o", 2000, 800),
        ]

        for op_name, model, input_tokens, output_tokens in operations:
            tracker.log_usage(
                model=model,
                usage={
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
                operation=op_name,
            )

        summary = tracker.get_session_summary()

        assert summary["total_requests"] == 3
        assert summary["total_cost"] > 0
        assert summary["by_operation"]["parse_instructions"]["count"] == 1

        print("\n📊 Session Summary:")
        print(f"   Total Requests: {summary['total_requests']}")
        print(f"   Total Tokens: {summary['total_tokens']}")
        print(f"   Total Cost: ${summary['total_cost']:.4f}")
        print(f"   Avg Cost/Request: ${summary['average_cost_per_request']:.4f}")


def test_all_utilities_importable():
    """Test that all utilities can be imported"""
    from app.services.llm.utils import (
        cost_tracker,
        default_retry_handler,
        flow_builder_cache,
        flow_builder_rate_limiter,
        llm_circuit_breaker,
        token_limiter,
    )

    assert flow_builder_cache is not None
    assert cost_tracker is not None
    assert token_limiter is not None
    assert flow_builder_rate_limiter is not None
    assert default_retry_handler is not None
    assert llm_circuit_breaker is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
