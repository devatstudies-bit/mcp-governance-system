"""
Phase 3C — AuditLogService.

Wraps the in-process AuditLogger with:
  - Filtering by action / actor / resource / environment
  - Pagination
  - Export (JSON dict list or CEF string list), with optional filter applied

In production, swap the in-memory store for async DB queries while keeping
the same public interface.
"""

from __future__ import annotations

import logging
from typing import Any

from mtgs.core.audit.logger import AuditAction, AuditEntry, AuditLogger

logger = logging.getLogger(__name__)


class AuditLogService:
    """
    Queryable, filterable façade over AuditLogger.

    All methods are async so they can be transparently swapped for DB-backed
    implementations without changing call sites.
    """

    def __init__(self) -> None:
        self._logger = AuditLogger()

    # ------------------------------------------------------------------ #
    #  Write                                                               #
    # ------------------------------------------------------------------ #

    async def record(
        self,
        action: AuditAction,
        actor_id: str,
        resource_id: str,
        resource_type: str,
        environment_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Record a governance action and return the immutable entry."""
        return await self._logger.record(
            action=action,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            environment_id=environment_id,
            metadata=metadata or {},
        )

    # ------------------------------------------------------------------ #
    #  Read                                                                #
    # ------------------------------------------------------------------ #

    async def list_entries(
        self,
        action_filter: str | None = None,
        actor_filter: str | None = None,
        resource_filter: str | None = None,
        environment_filter: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[AuditEntry]:
        """
        Return a filtered, paginated slice of audit entries.

        Entries are returned newest-first (reverse insertion order).
        """
        entries = list(reversed(self._logger._entries))

        if action_filter:
            entries = [e for e in entries if e.action.value == action_filter]
        if actor_filter:
            entries = [e for e in entries if e.actor_id == actor_filter]
        if resource_filter:
            entries = [e for e in entries if e.resource_id == resource_filter]
        if environment_filter:
            entries = [e for e in entries if e.environment_id == environment_filter]

        start = (page - 1) * page_size
        return entries[start : start + page_size]

    async def count(
        self,
        action_filter: str | None = None,
        actor_filter: str | None = None,
        resource_filter: str | None = None,
        environment_filter: str | None = None,
    ) -> int:
        """Total number of entries matching the given filters."""
        entries = self._logger._entries

        if action_filter:
            entries = [e for e in entries if e.action.value == action_filter]
        if actor_filter:
            entries = [e for e in entries if e.actor_id == actor_filter]
        if resource_filter:
            entries = [e for e in entries if e.resource_id == resource_filter]
        if environment_filter:
            entries = [e for e in entries if e.environment_id == environment_filter]

        return len(entries)

    # ------------------------------------------------------------------ #
    #  Export                                                              #
    # ------------------------------------------------------------------ #

    async def export(
        self,
        fmt: str = "json",
        action_filter: str | None = None,
        actor_filter: str | None = None,
        resource_filter: str | None = None,
        environment_filter: str | None = None,
    ) -> list[Any]:
        """
        Export all matching entries in the requested format.

        Parameters
        ----------
        fmt:
            ``"json"`` → list[dict]  (structured log)
            ``"cef"``  → list[str]   (Common Event Format, one line per entry)
        """
        # Fetch all entries matching filters (no pagination for export)
        entries = list(self._logger._entries)

        if action_filter:
            entries = [e for e in entries if e.action.value == action_filter]
        if actor_filter:
            entries = [e for e in entries if e.actor_id == actor_filter]
        if resource_filter:
            entries = [e for e in entries if e.resource_id == resource_filter]
        if environment_filter:
            entries = [e for e in entries if e.environment_id == environment_filter]

        if fmt == "cef":
            return [e.to_cef() for e in entries]
        return [e.to_dict() for e in entries]
