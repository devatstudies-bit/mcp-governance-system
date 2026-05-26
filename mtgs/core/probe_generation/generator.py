"""
Phase 2A — Probe Query Generator.

Generates natural-language probe queries that an LLM agent might send to a tool.
Two modes:
  - `generate_for_tool`: queries that should route to a *specific* tool.
  - `generate_adversarial`: ambiguous queries that could route to *either* of two
    conflicting tools, used to stress-test routing stability.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from mtgs.core.tool_def import ToolDef

logger = logging.getLogger(__name__)


class ChatService(Protocol):
    """Minimal interface for the chat completion service."""

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> Any: ...


class ProbeQueryGenerator:
    """Generate probe queries for conflict-impact simulation."""

    def __init__(self, chat_service: ChatService) -> None:
        self._chat = chat_service

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def generate_for_tool(self, tool: ToolDef, count: int = 10) -> list[str]:
        """Return *count* natural-language queries that should invoke *tool*."""
        prompt = self._build_generation_prompt(tool, count)
        try:
            result = await self._chat.complete_json(
                system_prompt=self._system_prompt_for_generation(),
                user_prompt=prompt,
            )
            queries = self._parse_query_list(result)
            return queries[:count]
        except Exception:
            logger.exception("ProbeQueryGenerator.generate_for_tool failed")
            return []

    async def generate_adversarial(
        self,
        tool_a: ToolDef,
        tool_b: ToolDef,
        count: int = 10,
    ) -> list[str]:
        """Return *count* ambiguous queries that could route to *tool_a* OR *tool_b*."""
        prompt = self._build_adversarial_prompt(tool_a, tool_b, count)
        try:
            result = await self._chat.complete_json(
                system_prompt=self._system_prompt_for_adversarial(),
                user_prompt=prompt,
            )
            queries = self._parse_query_list(result)
            return queries[:count]
        except Exception:
            logger.exception("ProbeQueryGenerator.generate_adversarial failed")
            return []

    # ------------------------------------------------------------------ #
    #  Prompt builders (public for testing)                               #
    # ------------------------------------------------------------------ #

    def _build_generation_prompt(self, tool: ToolDef, count: int) -> str:
        """Build the user-facing prompt for single-tool probe generation."""
        schema_section = ""
        if tool.input_schema:
            schema_section = (
                f"\n\nInput schema:\n```json\n{json.dumps(tool.input_schema, indent=2)}\n```"
            )

        return (
            f"Generate exactly {count} distinct natural-language queries that an AI agent "
            f"user would send to invoke the following MCP tool.\n\n"
            f"Tool name: {tool.name}\n"
            f"Tool description: {tool.description}\n"
            f"Server: {tool.server_name}"
            f"{schema_section}\n\n"
            f"Requirements:\n"
            f"- Each query must be a realistic user request that clearly maps to this tool.\n"
            f"- Vary phrasing, formality, and specificity across the {count} queries.\n"
            f"- Return a JSON array of {count} strings — no keys, no nesting, just the list.\n"
            f'Example: ["Can you create a task for me?", "Add a to-do item..."]'
        )

    def _build_adversarial_prompt(
        self, tool_a: ToolDef, tool_b: ToolDef, count: int
    ) -> str:
        """Build the user-facing prompt for adversarial / ambiguous probe generation."""
        return (
            f"Generate exactly {count} deliberately ambiguous natural-language queries "
            f"that could reasonably invoke EITHER of the two conflicting MCP tools below.\n\n"
            f"Tool A — {tool_a.name}: {tool_a.description}\n"
            f"Tool B — {tool_b.name}: {tool_b.description}\n\n"
            f"Requirements:\n"
            f"- Each query must be genuinely ambiguous — a reader could interpret it as "
            f"calling either tool.\n"
            f"- Avoid mentioning either tool name explicitly.\n"
            f"- Vary phrasing across the {count} queries.\n"
            f"- Return a JSON array of {count} strings — no keys, no nesting, just the list.\n"
            f'Example: ["Add something to my task list.", "Record this work item for me."]'
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _system_prompt_for_generation() -> str:
        return (
            "You are a test-data engineer building a probe query library for an MCP tool "
            "governance system. Your job is to generate realistic natural-language queries "
            "that would trigger a specific tool. "
            "Always respond with a valid JSON array of strings and nothing else."
        )

    @staticmethod
    def _system_prompt_for_adversarial() -> str:
        return (
            "You are a red-team engineer crafting adversarial test cases for an MCP tool "
            "governance system. Your job is to generate queries that are so ambiguous that "
            "an LLM agent might route them to the wrong tool. "
            "Always respond with a valid JSON array of strings and nothing else."
        )

    @staticmethod
    def _parse_query_list(raw: Any) -> list[str]:
        """Coerce LLM output into a flat list[str]."""
        if isinstance(raw, list):
            return [str(item) for item in raw if item]
        if isinstance(raw, dict):
            # Some models wrap the array: {"queries": [...]}
            for v in raw.values():
                if isinstance(v, list):
                    return [str(item) for item in v if item]
        return []
