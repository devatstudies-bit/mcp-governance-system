"""
Unit tests for Phase 4A — Circuit Breaker.

Run:
    pytest tests/unit/test_circuit_breaker.py -v
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


class TestCircuitBreakerClosed:
    @pytest.mark.asyncio
    async def test_successful_call_stays_closed(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def ok():
            return "ok"

        result = await cb.call(ok)
        assert result == "ok"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_below_threshold_stays_closed(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def boom():
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(boom)

        assert cb.state == CircuitState.CLOSED
        assert cb.stats.failed == 2

    @pytest.mark.asyncio
    async def test_failures_at_threshold_opens_circuit(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=3)

        async def boom():
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(boom)

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_stats_track_calls(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="test", failure_threshold=5)

        async def ok():
            return 1

        async def boom():
            raise RuntimeError("x")

        await cb.call(ok)
        await cb.call(ok)
        with pytest.raises(RuntimeError):
            await cb.call(boom)

        assert cb.stats.total_calls == 3
        assert cb.stats.successful == 2
        assert cb.stats.failed == 1


class TestCircuitBreakerOpen:
    @pytest.mark.asyncio
    async def test_open_circuit_raises_circuit_open_error(self) -> None:
        from mtgs.core.resilience.circuit_breaker import (
            CircuitBreaker, CircuitOpenError, CircuitState,
        )

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=9999)

        async def boom():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(boom)

        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await cb.call(boom)

        assert cb.stats.rejected == 1

    @pytest.mark.asyncio
    async def test_rejected_call_not_counted_as_failure(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitOpenError

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=9999)

        async def boom():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(boom)

        failures_before = cb.stats.failed
        with pytest.raises(CircuitOpenError):
            await cb.call(boom)

        assert cb.stats.failed == failures_before  # no new failure recorded

    @pytest.mark.asyncio
    async def test_reset_closes_open_circuit(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=9999)

        async def boom():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(boom)

        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerHalfOpen:
    @pytest.mark.asyncio
    async def test_recovery_timeout_transitions_to_half_open(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitState
        import time

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.05)

        async def boom():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(boom)

        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.1)  # let recovery_timeout elapse

        async def ok():
            return "recovered"

        result = await cb.call(ok)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failed_probe_reopens_circuit(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="test", failure_threshold=2, recovery_timeout=0.05)

        async def boom():
            raise RuntimeError("fail")

        for _ in range(2):
            with pytest.raises(RuntimeError):
                await cb.call(boom)

        await asyncio.sleep(0.1)

        with pytest.raises(RuntimeError):
            await cb.call(boom)

        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerDecorator:
    @pytest.mark.asyncio
    async def test_protect_decorator(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="test", failure_threshold=3)

        @cb.protect
        async def my_func(x: int) -> int:
            return x * 2

        result = await my_func(5)
        assert result == 10
        assert cb.stats.successful == 1

    @pytest.mark.asyncio
    async def test_protect_decorator_counts_failures(self) -> None:
        from mtgs.core.resilience.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="test", failure_threshold=5)

        @cb.protect
        async def flaky() -> None:
            raise ValueError("oops")

        with pytest.raises(ValueError):
            await flaky()

        assert cb.stats.failed == 1


class TestCircuitBreakerRegistry:
    def test_get_all_breakers_returns_dict(self) -> None:
        from mtgs.core.resilience.circuit_breaker import get_all_breakers

        breakers = get_all_breakers()
        assert isinstance(breakers, dict)
        assert "azure-openai" in breakers
        assert "azure-search" in breakers
        assert "mcp-sync" in breakers
        assert "notifications" in breakers

    def test_named_singletons_have_correct_names(self) -> None:
        from mtgs.core.resilience.circuit_breaker import (
            azure_openai_cb, azure_search_cb, mcp_sync_cb, notifications_cb,
        )

        assert azure_openai_cb.name == "azure-openai"
        assert azure_search_cb.name == "azure-search"
        assert mcp_sync_cb.name == "mcp-sync"
        assert notifications_cb.name == "notifications"
