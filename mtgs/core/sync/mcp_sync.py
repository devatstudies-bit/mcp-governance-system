"""
Phase 2D — MCP Server Sync Service.

Diffs the live tool list returned by an MCP server against the current
database snapshot, classifying each tool as added / removed / updated / unchanged.

Designed to be called from:
  - A Celery beat scheduled task (periodic polling)
  - The CI/CD webhook on every push
  - The CLI `mtgs sync` command
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from mtgs.core.tool_def import ToolDef

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SyncReport:
    """Result of diffing a remote MCP tool list against the database snapshot."""

    added: list[ToolDef] = field(default_factory=list)
    """Tools present in the remote list but absent in the database."""

    removed: list[ToolDef] = field(default_factory=list)
    """Tools present in the database but absent in the remote list."""

    updated: list[ToolDef] = field(default_factory=list)
    """Tools whose description or schema changed between remote and database."""

    unchanged: list[ToolDef] = field(default_factory=list)
    """Tools that are identical in remote and database."""

    @property
    def total_added(self) -> int:
        return len(self.added)

    @property
    def total_removed(self) -> int:
        return len(self.removed)

    @property
    def total_updated(self) -> int:
        return len(self.updated)

    @property
    def total_unchanged(self) -> int:
        return len(self.unchanged)

    @property
    def has_changes(self) -> bool:
        return (self.total_added + self.total_removed + self.total_updated) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class MCPServerSyncService:
    """
    Stateless service that computes the diff between a live MCP server's tool
    list and the tools stored in the database.

    Typical usage
    -------------
    svc = MCPServerSyncService()
    remote_payload = await fetch_mcp_tools(server_url)           # HTTP call
    db_tools       = await load_db_tools(server_id, session)     # DB query
    report = await svc.diff(remote_tools=remote_payload, db_tools=db_tools)
    """

    async def diff(
        self,
        remote_tools: list[dict[str, Any]],
        db_tools: list[ToolDef],
        server_name: str = "unknown",
    ) -> SyncReport:
        """
        Compute the diff between *remote_tools* (raw MCP payload) and *db_tools*.

        Parameters
        ----------
        remote_tools:
            Raw tool dicts as returned by the MCP server's ``tools/list`` method.
            Each dict is expected to have at minimum ``name`` and ``description``.
        db_tools:
            Current snapshot of tools stored in the database for this server.
        server_name:
            Human-readable name of the MCP server (used to populate ToolDef.server_name).
        """
        # Build lookup maps
        remote_map: dict[str, ToolDef] = {}
        for raw in remote_tools:
            inferred_server = (
                raw.get("server_name")
                or (db_tools[0].server_name if db_tools else server_name)
            )
            td = self.remote_to_tooldef(raw, server_name=inferred_server)
            remote_map[td.name] = td

        db_map: dict[str, ToolDef] = {t.name: t for t in db_tools}

        report = SyncReport()

        # Tools in remote but not in DB → added
        for name, td in remote_map.items():
            if name not in db_map:
                report.added.append(td)

        # Tools in DB but not in remote → removed
        for name, td in db_map.items():
            if name not in remote_map:
                report.removed.append(td)

        # Tools in both → compare
        for name in set(remote_map) & set(db_map):
            remote_td = remote_map[name]
            db_td = db_map[name]
            if self._has_changed(remote_td, db_td):
                report.updated.append(remote_td)
            else:
                report.unchanged.append(remote_td)

        logger.info(
            "MCPServerSyncService.diff complete: +%d -%d ~%d =%d",
            report.total_added,
            report.total_removed,
            report.total_updated,
            report.total_unchanged,
        )
        return report

    # ------------------------------------------------------------------ #
    #  Helpers (public for unit testing)                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def remote_to_tooldef(raw: dict[str, Any], server_name: str = "unknown") -> ToolDef:
        """Convert a raw MCP tools/list payload entry to a canonical ToolDef."""
        return ToolDef(
            name=raw.get("name", ""),
            description=raw.get("description", ""),
            input_schema=raw.get("inputSchema") or raw.get("input_schema") or {},
            server_name=raw.get("server_name", server_name),
        )

    @staticmethod
    def _has_changed(remote: ToolDef, db: ToolDef) -> bool:
        """
        Return True if any meaningful field differs between remote and DB copy.

        Schema comparison is skipped when the DB copy has no schema stored ({}),
        because the DB may not have persisted the schema on initial registration.
        """
        if remote.description.strip() != db.description.strip():
            return True
        # Only compare schemas if the DB has a non-empty schema tracked
        if db.input_schema and remote.input_schema != db.input_schema:
            return True
        return False
