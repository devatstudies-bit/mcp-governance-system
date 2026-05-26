"""
Unit tests for Phase 2D — MCP Server Sync Service.

Tests the MCPServerSyncService that fetches live tool lists from MCP servers
and diffs them against the database to detect additions, removals, and changes.

All HTTP and DB calls are mocked.

Run:
    pytest tests/unit/test_mcp_sync.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mtgs.core.tool_def import ToolDef

pytestmark = pytest.mark.unit


@pytest.fixture
def sample_remote_tools() -> list[dict]:
    """Tool definitions as returned by an MCP server's tools/list endpoint."""
    return [
        {
            "name": "query_database",
            "description": "Execute a SQL query.",
            "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"}}},
        },
        {
            "name": "send_email",
            "description": "Send an email to a recipient.",
            "inputSchema": {},
        },
    ]


@pytest.fixture
def sample_db_tools() -> list[ToolDef]:
    """Tools currently stored in the database for the same server."""
    return [
        ToolDef(name="query_database", description="Execute a SQL query.", server_name="data-mcp"),
        ToolDef(name="legacy_tool", description="An old tool being removed.", server_name="data-mcp"),
    ]


class TestMCPServerSyncService:
    @pytest.mark.asyncio
    async def test_sync_returns_diff_report(
        self, sample_remote_tools, sample_db_tools
    ) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService, SyncReport

        svc = MCPServerSyncService()
        report = await svc.diff(
            remote_tools=sample_remote_tools,
            db_tools=sample_db_tools,
        )

        assert isinstance(report, SyncReport)

    @pytest.mark.asyncio
    async def test_diff_detects_new_tool(
        self, sample_remote_tools, sample_db_tools
    ) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        svc = MCPServerSyncService()
        report = await svc.diff(
            remote_tools=sample_remote_tools,
            db_tools=sample_db_tools,
        )

        # send_email is in remote but not in db_tools
        added_names = [t.name for t in report.added]
        assert "send_email" in added_names

    @pytest.mark.asyncio
    async def test_diff_detects_removed_tool(
        self, sample_remote_tools, sample_db_tools
    ) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        svc = MCPServerSyncService()
        report = await svc.diff(
            remote_tools=sample_remote_tools,
            db_tools=sample_db_tools,
        )

        # legacy_tool is in db but not in remote_tools
        removed_names = [t.name for t in report.removed]
        assert "legacy_tool" in removed_names

    @pytest.mark.asyncio
    async def test_diff_detects_unchanged_tool(
        self, sample_remote_tools, sample_db_tools
    ) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        svc = MCPServerSyncService()
        report = await svc.diff(
            remote_tools=sample_remote_tools,
            db_tools=sample_db_tools,
        )

        # query_database exists in both with same description
        unchanged_names = [t.name for t in report.unchanged]
        assert "query_database" in unchanged_names

    @pytest.mark.asyncio
    async def test_diff_detects_updated_description(self) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        remote = [
            {"name": "run_query", "description": "Run an optimised SQL query.", "inputSchema": {}}
        ]
        db = [ToolDef(name="run_query", description="Run a SQL query.", server_name="db-mcp")]

        svc = MCPServerSyncService()
        report = await svc.diff(remote_tools=remote, db_tools=db)

        updated_names = [t.name for t in report.updated]
        assert "run_query" in updated_names

    @pytest.mark.asyncio
    async def test_empty_remote_marks_all_as_removed(self) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        db = [
            ToolDef(name="tool_a", description="A.", server_name="s"),
            ToolDef(name="tool_b", description="B.", server_name="s"),
        ]

        svc = MCPServerSyncService()
        report = await svc.diff(remote_tools=[], db_tools=db)

        assert len(report.removed) == 2
        assert len(report.added) == 0

    @pytest.mark.asyncio
    async def test_empty_db_marks_all_as_added(self) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        remote = [
            {"name": "new_tool", "description": "Brand new.", "inputSchema": {}},
        ]

        svc = MCPServerSyncService()
        report = await svc.diff(remote_tools=remote, db_tools=[])

        assert len(report.added) == 1
        assert len(report.removed) == 0

    @pytest.mark.asyncio
    async def test_sync_report_has_summary_counts(
        self, sample_remote_tools, sample_db_tools
    ) -> None:
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        svc = MCPServerSyncService()
        report = await svc.diff(
            remote_tools=sample_remote_tools,
            db_tools=sample_db_tools,
        )

        assert report.total_added == len(report.added)
        assert report.total_removed == len(report.removed)
        assert report.total_updated == len(report.updated)
        assert report.has_changes == (
            report.total_added + report.total_removed + report.total_updated > 0
        )

    def test_remote_tool_to_tooldef_conversion(self) -> None:
        """Remote MCP payload should convert cleanly to a ToolDef."""
        from mtgs.core.sync.mcp_sync import MCPServerSyncService

        svc = MCPServerSyncService()
        raw = {
            "name": "create_issue",
            "description": "Create a GitHub issue.",
            "inputSchema": {"type": "object", "properties": {}},
        }
        td = svc.remote_to_tooldef(raw, server_name="github-mcp")

        assert td.name == "create_issue"
        assert td.description == "Create a GitHub issue."
        assert td.server_name == "github-mcp"
        assert isinstance(td.input_schema, dict)
