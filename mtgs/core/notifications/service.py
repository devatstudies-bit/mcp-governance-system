"""
Phase 2E — Notification Service.

Provides three notification channels:
  - SlackNotifier   — HTTP POST to a Slack Incoming Webhook URL
  - EmailNotifier   — SMTP via Python's aiosmtplib (stub-able)
  - PagerDutyNotifier — PagerDuty Events API v2

And a high-level NotificationRouter that:
  - Accepts a list of channel instances
  - Filters events by minimum severity
  - Dispatches to all channels concurrently
  - Never raises; failed channels are recorded as False in the results dict
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Severity ordering (ascending risk)
_SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────


class NotificationChannel(Protocol):
    """Any notification channel must implement send()."""

    async def send(self, event: dict[str, Any]) -> bool: ...


# ─────────────────────────────────────────────────────────────────────────────
# Slack
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}


class SlackNotifier:
    """Send governance conflict events to a Slack channel via Incoming Webhook."""

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(self, event: dict[str, Any]) -> bool:
        """POST the formatted event to the Slack webhook. Returns True on 200."""
        if aiohttp is None:
            logger.error("aiohttp not installed — cannot send Slack notification")
            return False
        payload = self._format_message(event)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        logger.info("Slack notification sent (event_type=%s)", event.get("event_type"))
                        return True
                    logger.warning("Slack webhook returned HTTP %d", resp.status)
                    return False
        except Exception:
            logger.exception("SlackNotifier.send failed")
            return False

    def _format_message(self, event: dict[str, Any]) -> dict[str, Any]:
        """Build a Slack Block Kit message payload."""
        severity = event.get("severity", "UNKNOWN")
        emoji = _SEVERITY_EMOJI.get(severity, "⚪")
        conflict_type = event.get("conflict_type", "UNKNOWN")
        tool_names = ", ".join(event.get("tool_names", []))
        server_names = ", ".join(event.get("server_names", []))
        environment = event.get("environment", "unknown")
        conflict_id = event.get("conflict_id", "")

        text = (
            f"{emoji} *MCP Tool Conflict Detected* — `{severity}`\n"
            f"*Type:* {conflict_type}\n"
            f"*Tools:* `{tool_names}`\n"
            f"*Servers:* {server_names}\n"
            f"*Environment:* {environment}\n"
            f"*Conflict ID:* `{conflict_id}`"
        )

        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                }
            ],
            "text": f"{emoji} MCP conflict detected: {severity} — {conflict_type} ({tool_names})",
        }


# ─────────────────────────────────────────────────────────────────────────────
# Email (stub — real implementation uses aiosmtplib)
# ─────────────────────────────────────────────────────────────────────────────


class EmailNotifier:
    """Send governance alerts via SMTP email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        recipients: list[str],
        username: str = "",
        password: str = "",
        use_tls: bool = True,
    ) -> None:
        self._host = smtp_host
        self._port = smtp_port
        self._sender = sender
        self._recipients = recipients
        self._username = username
        self._password = password
        self._use_tls = use_tls

    async def send(self, event: dict[str, Any]) -> bool:
        """Send an alert email. Returns True on success."""
        subject, body = self._format_message(event)
        try:
            import aiosmtplib  # optional dep

            smtp = aiosmtplib.SMTP(
                hostname=self._host,
                port=self._port,
                use_tls=self._use_tls,
            )
            async with smtp:
                if self._username:
                    await smtp.login(self._username, self._password)
                from email.mime.text import MIMEText

                msg = MIMEText(body, "plain")
                msg["Subject"] = subject
                msg["From"] = self._sender
                msg["To"] = ", ".join(self._recipients)
                await smtp.send_message(msg)
            logger.info("EmailNotifier sent: %s", subject)
            return True
        except Exception:
            logger.exception("EmailNotifier.send failed")
            return False

    def _format_message(self, event: dict[str, Any]) -> tuple[str, str]:
        severity = event.get("severity", "UNKNOWN")
        conflict_type = event.get("conflict_type", "UNKNOWN")
        tool_names = ", ".join(event.get("tool_names", []))
        environment = event.get("environment", "unknown")
        conflict_id = event.get("conflict_id", "")

        subject = f"[MTGS] {severity} conflict detected in {environment}: {conflict_type}"
        body = (
            f"MCP Tool Governance System Alert\n"
            f"{'=' * 40}\n\n"
            f"Severity    : {severity}\n"
            f"Type        : {conflict_type}\n"
            f"Tools       : {tool_names}\n"
            f"Environment : {environment}\n"
            f"Conflict ID : {conflict_id}\n\n"
            f"Please review and resolve this conflict in the MTGS dashboard."
        )
        return subject, body


# ─────────────────────────────────────────────────────────────────────────────
# PagerDuty
# ─────────────────────────────────────────────────────────────────────────────


class PagerDutyNotifier:
    """Trigger/resolve PagerDuty incidents via Events API v2."""

    _EVENTS_API = "https://events.pagerduty.com/v2/enqueue"

    def __init__(self, integration_key: str) -> None:
        self._key = integration_key

    async def send(self, event: dict[str, Any]) -> bool:
        """Trigger a PagerDuty alert. Returns True on 202."""
        if aiohttp is None:
            logger.error("aiohttp not installed — cannot send PagerDuty notification")
            return False
        payload = self._format_message(event)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._EVENTS_API,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 202):
                        logger.info("PagerDuty alert triggered")
                        return True
                    logger.warning("PagerDuty API returned HTTP %d", resp.status)
                    return False
        except Exception:
            logger.exception("PagerDutyNotifier.send failed")
            return False

    def _format_message(self, event: dict[str, Any]) -> dict[str, Any]:
        severity = event.get("severity", "UNKNOWN")
        conflict_type = event.get("conflict_type", "UNKNOWN")
        tool_names = ", ".join(event.get("tool_names", []))
        conflict_id = event.get("conflict_id", "unknown")

        pd_severity_map = {
            "CRITICAL": "critical",
            "HIGH": "error",
            "MEDIUM": "warning",
            "LOW": "info",
        }
        pd_severity = pd_severity_map.get(severity, "warning")

        return {
            "routing_key": self._key,
            "event_action": "trigger",
            "dedup_key": conflict_id,
            "payload": {
                "summary": f"MCP Tool Conflict: {conflict_type} — {tool_names} ({severity})",
                "severity": pd_severity,
                "source": "mtgs",
                "custom_details": event,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────


class NotificationRouter:
    """
    Dispatch governance events to one or more notification channels.

    Parameters
    ----------
    channels:
        List of NotificationChannel instances (Slack, email, PagerDuty, …).
    min_severity:
        Minimum severity level to trigger notifications.
        Events below this threshold are silently dropped.
        Defaults to "LOW" (all events dispatched).
    """

    def __init__(
        self,
        channels: list[Any],
        min_severity: str = "LOW",
    ) -> None:
        self._channels = channels
        self._min_severity = min_severity

    async def dispatch(self, event: dict[str, Any]) -> dict[str, bool]:
        """
        Send *event* to all registered channels.

        Returns
        -------
        dict[channel_class_name -> success_bool]
        """
        if not self._should_dispatch(event):
            logger.debug(
                "NotificationRouter: skipping event (severity=%s < min=%s)",
                event.get("severity"),
                self._min_severity,
            )
            return {}

        results: dict[str, bool] = {}
        for channel in self._channels:
            channel_name = channel.__class__.__name__
            try:
                ok = await channel.send(event)
                results[channel_name] = bool(ok)
            except Exception:
                logger.exception("NotificationRouter: channel %s raised", channel_name)
                results[channel_name] = False

        return results

    # ------------------------------------------------------------------ #

    def _should_dispatch(self, event: dict[str, Any]) -> bool:
        """Return True if the event's severity meets the minimum threshold."""
        event_severity = event.get("severity", "LOW")
        try:
            event_idx = _SEVERITY_ORDER.index(event_severity)
            min_idx = _SEVERITY_ORDER.index(self._min_severity)
            return event_idx >= min_idx
        except ValueError:
            return True  # unknown severity → always dispatch
