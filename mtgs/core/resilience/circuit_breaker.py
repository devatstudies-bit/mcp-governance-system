"""
Circuit Breaker — Phase 4A.

Prevents cascade failures when Azure OpenAI or Azure AI Search are degraded.

States
------
CLOSED     — normal operation; failures are counted.
OPEN       — all calls fail-fast (no real request made) for `recovery_timeout` s.
HALF_OPEN  — one probe request is allowed through; success → CLOSED, fail → OPEN.

Usage
-----
    cb = CircuitBreaker(name="azure-openai", failure_threshold=5)

    @cb.protect
    async def call_llm():
        ...

    # or inline:
    result = await cb.call(some_coroutine_func, *args, **kwargs)

Thread/task safety
------------------
All state mutations use asyncio.Lock so concurrent FastAPI requests don't
race on the counter.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED    = "CLOSED"
    OPEN      = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is OPEN."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit '{name}' is OPEN. Retry after {retry_after:.1f}s."
        )


@dataclass
class CircuitBreakerStats:
    """Observable counters for monitoring / health endpoints."""

    total_calls:    int = 0
    successful:     int = 0
    failed:         int = 0
    rejected:       int = 0   # calls turned away while OPEN
    state_changes:  int = 0


class CircuitBreaker:
    """
    Async-safe circuit breaker.

    Parameters
    ----------
    name:
        Human-readable label (used in logs and CircuitOpenError messages).
    failure_threshold:
        Consecutive failures before the circuit opens.
    recovery_timeout:
        Seconds the circuit stays OPEN before transitioning to HALF_OPEN.
    half_open_max_calls:
        How many probe calls are permitted in HALF_OPEN state before
        deciding to close or re-open.
    expected_exceptions:
        Tuple of exception types that count as failures.
        Default: (Exception,) — any exception.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        expected_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0

        self._lock = asyncio.Lock()
        self.stats = CircuitBreakerStats()

    # ------------------------------------------------------------------ #
    #  Public interface                                                    #
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    async def call(
        self,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute *func* under circuit-breaker protection.

        Raises CircuitOpenError if the circuit is OPEN and the recovery
        timeout has not elapsed.
        """
        async with self._lock:
            await self._maybe_transition()
            if self._state == CircuitState.OPEN:
                self.stats.rejected += 1
                retry_after = max(
                    0.0,
                    self._recovery_timeout - (time.monotonic() - self._last_failure_time),
                )
                raise CircuitOpenError(self.name, retry_after)
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        self.stats.total_calls += 1
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self._expected_exceptions as exc:
            await self._on_failure()
            raise

    def protect(
        self, func: Callable[..., Coroutine[Any, Any, Any]]
    ) -> Callable[..., Coroutine[Any, Any, Any]]:
        """Decorator: wrap an async function with this circuit breaker."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.call(func, *args, **kwargs)

        return wrapper

    # ------------------------------------------------------------------ #
    #  State machine                                                       #
    # ------------------------------------------------------------------ #

    async def _maybe_transition(self) -> None:
        """Check whether the circuit should move OPEN → HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._recovery_timeout:
                logger.info("CircuitBreaker '%s': OPEN → HALF_OPEN", self.name)
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self.stats.state_changes += 1

    async def _on_success(self) -> None:
        async with self._lock:
            self.stats.successful += 1
            if self._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
                if self._state == CircuitState.HALF_OPEN:
                    logger.info("CircuitBreaker '%s': HALF_OPEN → CLOSED", self.name)
                    self.stats.state_changes += 1
                self._state = CircuitState.CLOSED
                self._failure_count = 0

    async def _on_failure(self) -> None:
        async with self._lock:
            self.stats.failed += 1
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning("CircuitBreaker '%s': HALF_OPEN → OPEN (probe failed)", self.name)
                self._state = CircuitState.OPEN
                self.stats.state_changes += 1
            elif (
                self._state == CircuitState.CLOSED
                and self._failure_count >= self._failure_threshold
            ):
                logger.warning(
                    "CircuitBreaker '%s': CLOSED → OPEN (%d failures)",
                    self.name, self._failure_count,
                )
                self._state = CircuitState.OPEN
                self.stats.state_changes += 1

    def reset(self) -> None:
        """Manually reset to CLOSED state (for testing / admin override)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0
        self._last_failure_time = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Named singletons — one per external dependency
# ─────────────────────────────────────────────────────────────────────────────

#: Circuit breaker for Azure OpenAI (embeddings + chat)
azure_openai_cb = CircuitBreaker(
    name="azure-openai",
    failure_threshold=5,
    recovery_timeout=30.0,
)

#: Circuit breaker for Azure AI Search
azure_search_cb = CircuitBreaker(
    name="azure-search",
    failure_threshold=5,
    recovery_timeout=30.0,
)

#: Circuit breaker for outbound MCP server HTTP calls
mcp_sync_cb = CircuitBreaker(
    name="mcp-sync",
    failure_threshold=3,
    recovery_timeout=60.0,
)

#: Circuit breaker for Slack/PagerDuty notification webhooks
notifications_cb = CircuitBreaker(
    name="notifications",
    failure_threshold=3,
    recovery_timeout=120.0,
)


def get_all_breakers() -> dict[str, CircuitBreaker]:
    """Return all named circuit breakers for health-check reporting."""
    return {
        "azure-openai":  azure_openai_cb,
        "azure-search":  azure_search_cb,
        "mcp-sync":      mcp_sync_cb,
        "notifications": notifications_cb,
    }
