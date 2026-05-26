"""
Unit tests for Phase 2E — Notification Service.

Tests Slack, email and PagerDuty notification channels.
All HTTP calls are mocked — no real endpoints needed.

Run:
    pytest tests/unit/test_notification_service.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def critical_conflict_event() -> dict:
    return {
        "event_type": "CONFLICT_DETECTED",
        "severity": "CRITICAL",
        "conflict_type": "EXACT_NAME",
        "tool_names": ["send_message", "send_message"],
        "server_names": ["slack-mcp", "email-mcp"],
        "environment": "production",
        "conflict_id": "c1a2b3",
    }


@pytest.fixture
def high_conflict_event() -> dict:
    return {
        "event_type": "CONFLICT_DETECTED",
        "severity": "HIGH",
        "conflict_type": "SEMANTIC_OVERLAP",
        "tool_names": ["create_task", "add_todo"],
        "server_names": ["project-mcp", "todo-mcp"],
        "environment": "staging",
        "conflict_id": "d4e5f6",
    }


class TestSlackNotifier:
    def _make_aiohttp_mock(self, status: int) -> MagicMock:
        """
        Build a correctly structured aiohttp module mock.

        aiohttp uses nested async context managers:
          async with aiohttp.ClientSession() as session:
              async with session.post(...) as resp:

        - ClientSession() must return an async context manager yielding the session.
        - session.post() must return an async context manager yielding the response.
        - session must be a MagicMock (not AsyncMock) so that session.post(...) returns
          a MagicMock (context manager), NOT a coroutine.
        """
        mock_response = MagicMock()
        mock_response.status = status

        # Inner context manager: session.post(...) → resp
        post_cm = MagicMock()
        post_cm.__aenter__ = AsyncMock(return_value=mock_response)
        post_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=post_cm)

        # Outer context manager: ClientSession() → session
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=session_cm)
        mock_aiohttp.ClientTimeout = MagicMock(return_value=MagicMock())
        return mock_aiohttp

    @pytest.mark.asyncio
    async def test_send_critical_returns_true_on_success(
        self, critical_conflict_event
    ) -> None:
        from mtgs.core.notifications.service import SlackNotifier

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        mock_aiohttp = self._make_aiohttp_mock(status=200)

        with patch("mtgs.core.notifications.service.aiohttp", mock_aiohttp):
            result = await notifier.send(critical_conflict_event)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_returns_false_on_http_error(
        self, critical_conflict_event
    ) -> None:
        from mtgs.core.notifications.service import SlackNotifier

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        mock_aiohttp = self._make_aiohttp_mock(status=500)

        with patch("mtgs.core.notifications.service.aiohttp", mock_aiohttp):
            result = await notifier.send(critical_conflict_event)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_returns_false_on_exception(
        self, critical_conflict_event
    ) -> None:
        from mtgs.core.notifications.service import SlackNotifier

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")

        with patch("mtgs.core.notifications.service.aiohttp") as mock_aiohttp:
            mock_aiohttp.ClientSession.side_effect = Exception("Network error")
            result = await notifier.send(critical_conflict_event)

        assert result is False

    def test_format_message_includes_severity(self, critical_conflict_event) -> None:
        from mtgs.core.notifications.service import SlackNotifier

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        payload = notifier._format_message(critical_conflict_event)

        # Slack Block Kit or fallback text must contain severity
        combined = str(payload)
        assert "CRITICAL" in combined

    def test_format_message_includes_tool_names(self, critical_conflict_event) -> None:
        from mtgs.core.notifications.service import SlackNotifier

        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        payload = notifier._format_message(critical_conflict_event)

        combined = str(payload)
        assert "send_message" in combined


class TestNotificationRouter:
    """Tests for the high-level NotificationRouter that dispatches to channels."""

    @pytest.mark.asyncio
    async def test_router_dispatches_to_slack(self, critical_conflict_event) -> None:
        from mtgs.core.notifications.service import NotificationRouter, SlackNotifier

        mock_slack = AsyncMock(spec=SlackNotifier)
        mock_slack.send = AsyncMock(return_value=True)

        router = NotificationRouter(channels=[mock_slack])
        results = await router.dispatch(critical_conflict_event)

        mock_slack.send.assert_called_once_with(critical_conflict_event)
        assert results["SlackNotifier"] is True

    @pytest.mark.asyncio
    async def test_router_dispatches_to_multiple_channels(
        self, critical_conflict_event
    ) -> None:
        from mtgs.core.notifications.service import NotificationRouter, SlackNotifier

        ch1 = AsyncMock()
        ch1.send = AsyncMock(return_value=True)
        ch1.__class__.__name__ = "SlackNotifier"

        ch2 = AsyncMock()
        ch2.send = AsyncMock(return_value=True)
        ch2.__class__.__name__ = "EmailNotifier"

        router = NotificationRouter(channels=[ch1, ch2])
        results = await router.dispatch(critical_conflict_event)

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_router_filters_by_minimum_severity(
        self, high_conflict_event
    ) -> None:
        """With min_severity=CRITICAL, HIGH events should not be dispatched."""
        from mtgs.core.notifications.service import NotificationRouter

        mock_ch = AsyncMock()
        mock_ch.send = AsyncMock(return_value=True)

        router = NotificationRouter(channels=[mock_ch], min_severity="CRITICAL")
        results = await router.dispatch(high_conflict_event)

        # HIGH < CRITICAL, so nothing dispatched
        mock_ch.send.assert_not_called()
        assert results == {}

    @pytest.mark.asyncio
    async def test_router_continues_if_one_channel_fails(
        self, critical_conflict_event
    ) -> None:
        from mtgs.core.notifications.service import NotificationRouter

        ch_ok = AsyncMock()
        ch_ok.send = AsyncMock(return_value=True)
        ch_ok.__class__.__name__ = "SlackNotifier"

        ch_bad = AsyncMock()
        ch_bad.send = AsyncMock(side_effect=Exception("Down"))
        ch_bad.__class__.__name__ = "PagerDutyNotifier"

        router = NotificationRouter(channels=[ch_ok, ch_bad])
        results = await router.dispatch(critical_conflict_event)

        # SlackNotifier succeeded, PagerDutyNotifier is marked failed
        assert results["SlackNotifier"] is True
        assert results["PagerDutyNotifier"] is False
