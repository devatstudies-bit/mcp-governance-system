"""
Unit tests for Phase 2C — Recommendation Engine.

All LLM calls are mocked.

Run:
    pytest tests/unit/test_recommendation_engine.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from mtgs.core.tool_def import ToolDef

pytestmark = pytest.mark.unit

# Canonical recommendation JSON that the mock LLM returns
MOCK_RECOMMENDATION_RESPONSE = {
    "recommendations": [
        {
            "recommendation_type": "SCOPE_NARROWING",
            "target_tool": "create_task",
            "proposed_change": {
                "field": "description",
                "before": "Creates a new task in the project management system.",
                "after": (
                    "Creates a new task specifically in Jira. "
                    "Do not use for to-do items or personal task lists."
                ),
            },
            "rationale": (
                "Narrowing the description to explicitly mention Jira and exclude "
                "to-do list use cases reduces semantic overlap with 'add_todo'."
            ),
            "predicted_improvement": 45,
        }
    ]
}


@pytest.fixture
def mock_chat():
    mock = AsyncMock()
    mock.complete_json = AsyncMock(return_value=MOCK_RECOMMENDATION_RESPONSE)
    return mock


@pytest.fixture
def conflicting_tools() -> tuple[ToolDef, ToolDef]:
    tool_a = ToolDef(
        name="create_task",
        description="Creates a new task in the project management system.",
        server_name="project-mcp",
    )
    tool_b = ToolDef(
        name="add_todo",
        description="Add a new to-do item to the task list.",
        server_name="todo-mcp",
    )
    return tool_a, tool_b


@pytest.fixture
def mock_conflict() -> dict:
    return {
        "conflict_type": "SEMANTIC_OVERLAP",
        "severity": "HIGH",
        "evidence": {
            "cosine_similarity": 0.88,
            "candidate_tool": "create_task",
            "conflicting_tool": "add_todo",
        },
    }


class TestRecommendationEngine:
    @pytest.mark.asyncio
    async def test_generate_returns_list(
        self, mock_chat, conflicting_tools, mock_conflict
    ) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=mock_chat)
        tool_a, tool_b = conflicting_tools
        recs = await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        assert isinstance(recs, list)
        assert len(recs) >= 1

    @pytest.mark.asyncio
    async def test_recommendation_has_required_fields(
        self, mock_chat, conflicting_tools, mock_conflict
    ) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine, Recommendation

        engine = RecommendationEngine(chat_service=mock_chat)
        tool_a, tool_b = conflicting_tools
        recs = await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        rec = recs[0]
        assert isinstance(rec, Recommendation)
        assert rec.recommendation_type in (
            "RENAME", "DESCRIPTION_REWRITE", "SCOPE_NARROWING",
            "SCHEMA_CLARIFICATION", "DEPRECATE"
        )
        assert rec.target_tool_name
        assert rec.proposed_change
        assert rec.rationale
        assert isinstance(rec.predicted_improvement, (int, float))

    @pytest.mark.asyncio
    async def test_recommendation_type_is_valid(
        self, mock_chat, conflicting_tools, mock_conflict
    ) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=mock_chat)
        tool_a, tool_b = conflicting_tools
        recs = await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        valid_types = {
            "RENAME", "DESCRIPTION_REWRITE", "SCOPE_NARROWING",
            "SCHEMA_CLARIFICATION", "DEPRECATE"
        }
        for rec in recs:
            assert rec.recommendation_type in valid_types

    @pytest.mark.asyncio
    async def test_prompt_includes_conflict_type(
        self, mock_chat, conflicting_tools, mock_conflict
    ) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=mock_chat)
        tool_a, tool_b = conflicting_tools
        await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        call_args = mock_chat.complete_json.call_args
        combined = str(call_args)
        assert "SEMANTIC_OVERLAP" in combined

    @pytest.mark.asyncio
    async def test_prompt_includes_both_tool_names(
        self, mock_chat, conflicting_tools, mock_conflict
    ) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=mock_chat)
        tool_a, tool_b = conflicting_tools
        await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        call_args = mock_chat.complete_json.call_args
        combined = str(call_args)
        assert "create_task" in combined
        assert "add_todo" in combined

    @pytest.mark.asyncio
    async def test_handles_llm_error_gracefully(
        self, conflicting_tools, mock_conflict
    ) -> None:
        """On LLM failure, return empty list rather than raising."""
        failing_mock = AsyncMock()
        failing_mock.complete_json = AsyncMock(
            side_effect=Exception("Azure rate limit")
        )

        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=failing_mock)
        tool_a, tool_b = conflicting_tools
        recs = await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        assert recs == []

    @pytest.mark.asyncio
    async def test_handles_malformed_llm_response(
        self, conflicting_tools, mock_conflict
    ) -> None:
        """Malformed LLM JSON → empty list, no crash."""
        bad_mock = AsyncMock()
        bad_mock.complete_json = AsyncMock(return_value={"unexpected_key": "value"})

        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=bad_mock)
        tool_a, tool_b = conflicting_tools
        recs = await engine.generate(conflict=mock_conflict, tools=[tool_a, tool_b])

        assert isinstance(recs, list)

    @pytest.mark.asyncio
    async def test_exact_name_conflict_suggests_rename(
        self, conflicting_tools
    ) -> None:
        """EXACT_NAME conflicts should receive at least one RENAME recommendation."""
        rename_response = {
            "recommendations": [
                {
                    "recommendation_type": "RENAME",
                    "target_tool": "create_task",
                    "proposed_change": {
                        "field": "name",
                        "before": "create_task",
                        "after": "create_jira_task",
                    },
                    "rationale": "Add system prefix to distinguish from other task tools.",
                    "predicted_improvement": 100,
                }
            ]
        }
        mock_chat = AsyncMock()
        mock_chat.complete_json = AsyncMock(return_value=rename_response)

        exact_name_conflict = {
            "conflict_type": "EXACT_NAME",
            "severity": "CRITICAL",
            "evidence": {},
        }

        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=mock_chat)
        tool_a, tool_b = conflicting_tools
        recs = await engine.generate(conflict=exact_name_conflict, tools=[tool_a, tool_b])

        rename_recs = [r for r in recs if r.recommendation_type == "RENAME"]
        assert len(rename_recs) >= 1


class TestRecommendationPromptBuilder:
    def test_builds_non_empty_prompt(self) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        mock_chat = AsyncMock()
        engine = RecommendationEngine(chat_service=mock_chat)

        tool_a = ToolDef(name="send_message", description="Send a message.", server_name="slack")
        tool_b = ToolDef(name="send_message", description="Send an email.", server_name="email")
        conflict = {"conflict_type": "EXACT_NAME", "severity": "CRITICAL", "evidence": {}}

        prompt = engine._build_prompt(conflict, [tool_a, tool_b])
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_prompt_includes_severity(self) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=AsyncMock())
        tool = ToolDef(name="t", description="A tool.")
        conflict = {"conflict_type": "SEMANTIC_OVERLAP", "severity": "HIGH", "evidence": {}}
        prompt = engine._build_prompt(conflict, [tool])
        assert "HIGH" in prompt

    def test_prompt_requests_json_output(self) -> None:
        from mtgs.core.recommendations.engine import RecommendationEngine

        engine = RecommendationEngine(chat_service=AsyncMock())
        tool = ToolDef(name="t", description="A tool.")
        conflict = {"conflict_type": "SEMANTIC_OVERLAP", "severity": "HIGH", "evidence": {}}
        prompt = engine._build_prompt(conflict, [tool])
        assert "JSON" in prompt or "json" in prompt
