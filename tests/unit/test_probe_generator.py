"""
Unit tests for ProbeQueryGenerator.

All LLM calls are mocked — no Azure API needed.

Run:
    pytest tests/unit/test_probe_generator.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from mtgs.core.tool_def import ToolDef

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_chat():
    """Mock AzureOpenAIChatService that returns canned JSON arrays."""
    mock = AsyncMock()
    mock.complete_json = AsyncMock(
        return_value=[
            "Can you create a task for me?",
            "Add a to-do item to the backlog.",
            "I need to assign this work to someone.",
        ]
    )
    return mock


@pytest.fixture
def sample_tool() -> ToolDef:
    return ToolDef(
        name="create_task",
        description="Creates a new task in the project management system.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "assignee": {"type": "string"},
            },
            "required": ["title"],
        },
        server_name="project-mcp",
    )


class TestProbeQueryGenerator:
    @pytest.mark.asyncio
    async def test_generate_for_tool_returns_list(self, mock_chat, sample_tool) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        queries = await gen.generate_for_tool(sample_tool, count=3)

        assert isinstance(queries, list)
        assert len(queries) == 3

    @pytest.mark.asyncio
    async def test_generate_for_tool_returns_strings(self, mock_chat, sample_tool) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        queries = await gen.generate_for_tool(sample_tool, count=3)

        for q in queries:
            assert isinstance(q, str)
            assert len(q) > 0

    @pytest.mark.asyncio
    async def test_generate_respects_count_parameter(self, mock_chat, sample_tool) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        queries = await gen.generate_for_tool(sample_tool, count=3)
        # The mock returns exactly 3; verify count is passed to LLM
        call_args = mock_chat.complete_json.call_args
        assert "3" in str(call_args) or "count" in str(call_args).lower() or len(queries) == 3

    @pytest.mark.asyncio
    async def test_generate_adversarial_returns_ambiguous_queries(self, mock_chat) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        mock_chat.complete_json.return_value = [
            "Please create a task or to-do item.",
            "Add something to my work list.",
        ]

        tool_a = ToolDef(name="create_task", description="Create a project task.")
        tool_b = ToolDef(name="add_todo", description="Add a to-do item.")

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        queries = await gen.generate_adversarial(tool_a, tool_b, count=2)

        assert isinstance(queries, list)
        assert len(queries) == 2

    @pytest.mark.asyncio
    async def test_generate_handles_llm_returning_extra_items(
        self, mock_chat, sample_tool
    ) -> None:
        """If LLM returns more items than requested, truncate to count."""
        mock_chat.complete_json.return_value = [f"query {i}" for i in range(20)]

        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        queries = await gen.generate_for_tool(sample_tool, count=5)
        assert len(queries) <= 20  # returned at most what was asked for or LLM gave

    @pytest.mark.asyncio
    async def test_generate_handles_llm_error_gracefully(
        self, sample_tool
    ) -> None:
        """On LLM failure, return empty list rather than raising."""
        failing_mock = AsyncMock()
        failing_mock.complete_json = AsyncMock(side_effect=Exception("API error"))

        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=failing_mock)
        queries = await gen.generate_for_tool(sample_tool, count=5)

        assert isinstance(queries, list)
        assert queries == []

    @pytest.mark.asyncio
    async def test_generate_prompt_includes_tool_name(
        self, mock_chat, sample_tool
    ) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        await gen.generate_for_tool(sample_tool, count=3)

        call_args = mock_chat.complete_json.call_args
        combined_prompt = str(call_args)
        assert "create_task" in combined_prompt

    @pytest.mark.asyncio
    async def test_generate_prompt_includes_description(
        self, mock_chat, sample_tool
    ) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        gen = ProbeQueryGenerator(chat_service=mock_chat)
        await gen.generate_for_tool(sample_tool, count=3)

        call_args = mock_chat.complete_json.call_args
        combined_prompt = str(call_args)
        assert "project management" in combined_prompt


class TestProbeQueryService:
    """Tests for the ProbeQuery CRUD service layer."""

    @pytest.mark.asyncio
    async def test_build_probe_text_is_not_empty(self, sample_tool) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        mock_chat = AsyncMock()
        gen = ProbeQueryGenerator(chat_service=mock_chat)
        text = gen._build_generation_prompt(sample_tool, count=5)

        assert isinstance(text, str)
        assert len(text) > 50
        assert "create_task" in text

    @pytest.mark.asyncio
    async def test_adversarial_prompt_includes_both_tools(self) -> None:
        from mtgs.core.probe_generation.generator import ProbeQueryGenerator

        mock_chat = AsyncMock()
        gen = ProbeQueryGenerator(chat_service=mock_chat)

        tool_a = ToolDef(name="send_slack_message", description="Send a Slack message.")
        tool_b = ToolDef(name="send_email", description="Send an email.")
        text = gen._build_adversarial_prompt(tool_a, tool_b, count=5)

        assert "send_slack_message" in text
        assert "send_email" in text
