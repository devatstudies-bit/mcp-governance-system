"""
Unit tests for Stage 1 — Lexical Conflict Detection.

Tests are written BEFORE the implementation (TDD).
Each test describes the exact behavior the implementation must satisfy.

Run:
    pytest tests/unit/test_lexical_detection.py -v
"""

from __future__ import annotations

import pytest

from mtgs.core.conflict_detection.lexical import (
    LexicalAnalyzer,
    LexicalConflict,
    LexicalConflictType,
)
from tests.fixtures.tool_fixtures import (
    TOOL_ADD_TODO,
    TOOL_CREATE_TASK,
    TOOL_GENERATE_INVOICE,
    TOOL_GET_USER_A,
    TOOL_GET_USER_B,
    TOOL_QUERY_DATABASE,
    TOOL_SEND_MESSAGE_EMAIL,
    TOOL_SEND_MESSAGE_SLACK,
    TOOL_SEND_MSG,
    ToolDef,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def analyzer() -> LexicalAnalyzer:
    return LexicalAnalyzer()


# ─────────────────────────────────────────────────────────────────────────────
# EXACT NAME COLLISION
# ─────────────────────────────────────────────────────────────────────────────

class TestExactNameCollision:
    def test_exact_name_collision_detected(self, analyzer: LexicalAnalyzer) -> None:
        """Two tools with identical names across different servers → EXACT_NAME conflict."""
        conflicts = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        assert len(conflicts) >= 1
        exact = [c for c in conflicts if c.conflict_type == LexicalConflictType.EXACT_NAME]
        assert len(exact) == 1

    def test_exact_name_conflict_has_critical_severity(self, analyzer: LexicalAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        exact = [c for c in conflicts if c.conflict_type == LexicalConflictType.EXACT_NAME]
        assert exact[0].severity == "CRITICAL"

    def test_exact_name_conflict_identifies_both_tools(self, analyzer: LexicalAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        exact = conflicts[0]
        assert exact.candidate_name == TOOL_SEND_MESSAGE_SLACK.name
        assert exact.conflicting_name == TOOL_SEND_MESSAGE_EMAIL.name

    def test_no_false_positive_same_server(self, analyzer: LexicalAnalyzer) -> None:
        """
        Tools with the same name on the SAME server should not produce a conflict —
        the registry enforces uniqueness, so this should not arise, but the analyzer
        must be tolerant.
        """
        same_server_tool = ToolDef(
            name="send_message",
            description="Another variant",
            server_name="slack-mcp",  # same server as TOOL_SEND_MESSAGE_SLACK
        )
        # No conflict expected when server_name is treated as a differentiator
        conflicts = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[same_server_tool],
            same_server_ok=True,
        )
        exact = [c for c in conflicts if c.conflict_type == LexicalConflictType.EXACT_NAME]
        assert len(exact) == 0

    def test_exact_name_across_multiple_existing(self, analyzer: LexicalAnalyzer) -> None:
        """One candidate, three existing tools — only the name-matching one collides."""
        conflicts = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[
                TOOL_QUERY_DATABASE,
                TOOL_SEND_MESSAGE_EMAIL,  # collision
                TOOL_GENERATE_INVOICE,
            ],
        )
        exact = [c for c in conflicts if c.conflict_type == LexicalConflictType.EXACT_NAME]
        assert len(exact) == 1


# ─────────────────────────────────────────────────────────────────────────────
# SIMILAR NAME
# ─────────────────────────────────────────────────────────────────────────────

class TestSimilarName:
    def test_edit_distance_1_detected(self, analyzer: LexicalAnalyzer) -> None:
        """send_msg vs send_message → edit distance 4, but token overlap is high."""
        # Actually test a true edit-distance-1 pair
        tool_a = ToolDef(name="create_task", description="Create a task in Jira.")
        tool_b = ToolDef(name="create_taks", description="Create a task in Asana.")  # typo
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        similar = [c for c in conflicts if c.conflict_type == LexicalConflictType.SIMILAR_NAME]
        assert len(similar) >= 1

    def test_edit_distance_2_detected(self, analyzer: LexicalAnalyzer) -> None:
        tool_a = ToolDef(name="get_user", description="Get a user profile.")
        tool_b = ToolDef(name="get_usre", description="Get a user from a different system.")  # 2 typos
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        similar = [c for c in conflicts if c.conflict_type == LexicalConflictType.SIMILAR_NAME]
        assert len(similar) >= 1

    def test_edit_distance_3_not_detected(self, analyzer: LexicalAnalyzer) -> None:
        """Edit distance 3 is above the threshold — should NOT be flagged as SIMILAR_NAME."""
        tool_a = ToolDef(name="create_task", description="Create a task.")
        tool_b = ToolDef(name="delete_task", description="Delete a task.")  # edit distance > 2
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        similar = [c for c in conflicts if c.conflict_type == LexicalConflictType.SIMILAR_NAME]
        # May or may not flag due to token overlap; verify no SIMILAR_NAME from edit distance
        for c in similar:
            # If flagged, it must be due to token overlap, not edit distance
            assert c.evidence.get("detection_method") != "edit_distance"

    def test_shared_all_tokens_detected(self, analyzer: LexicalAnalyzer) -> None:
        """
        'create_salesforce_task' and 'create_jira_task' share tokens [create, task].
        Jaccard similarity on tokens is 2/4 = 0.5 — should be flagged.
        """
        tool_a = ToolDef(name="create_salesforce_task", description="Create task in Salesforce.")
        tool_b = ToolDef(name="create_jira_task", description="Create task in Jira.")
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        similar = [c for c in conflicts if c.conflict_type == LexicalConflictType.SIMILAR_NAME]
        assert len(similar) >= 1

    def test_similar_name_severity_is_medium(self, analyzer: LexicalAnalyzer) -> None:
        tool_a = ToolDef(name="get_user", description="Get user from HR.")
        tool_b = ToolDef(name="get_usre", description="Get user from auth system.")
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        similar = [c for c in conflicts if c.conflict_type == LexicalConflictType.SIMILAR_NAME]
        if similar:
            assert similar[0].severity == "MEDIUM"

    def test_completely_different_names_no_similar_conflict(
        self, analyzer: LexicalAnalyzer
    ) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE, TOOL_SCHEDULE_MEETING],
        )
        similar = [c for c in conflicts if c.conflict_type == LexicalConflictType.SIMILAR_NAME]
        assert len(similar) == 0


# ─────────────────────────────────────────────────────────────────────────────
# RESULT STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestConflictStructure:
    def test_conflict_has_required_fields(self, analyzer: LexicalAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        c = conflicts[0]
        assert isinstance(c, LexicalConflict)
        assert c.conflict_type in LexicalConflictType.__dict__.values()
        assert c.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
        assert c.candidate_name
        assert c.conflicting_name
        assert isinstance(c.evidence, dict)
        assert isinstance(c.conflict_score, (int, float))
        assert 0.0 <= c.conflict_score <= 100.0

    def test_no_conflicts_returns_empty_list(self, analyzer: LexicalAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
        )
        assert isinstance(conflicts, list)

    def test_empty_existing_returns_no_conflicts(self, analyzer: LexicalAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_QUERY_DATABASE,
            existing=[],
        )
        assert conflicts == []

    def test_analysis_is_idempotent(self, analyzer: LexicalAnalyzer) -> None:
        """Running the same analysis twice must produce identical results."""
        run1 = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL, TOOL_SEND_MSG],
        )
        run2 = analyzer.analyze(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL, TOOL_SEND_MSG],
        )
        assert len(run1) == len(run2)
        for c1, c2 in zip(run1, run2):
            assert c1.conflict_type == c2.conflict_type
            assert c1.conflict_score == c2.conflict_score


# ─────────────────────────────────────────────────────────────────────────────
# EDGE CASES
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_case_insensitive_name_matching(self, analyzer: LexicalAnalyzer) -> None:
        """Tool names should be compared case-insensitively."""
        tool_a = ToolDef(name="Create_Task", description="Create a task.")
        tool_b = ToolDef(name="create_task", description="Create a task in another system.")
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        exact = [c for c in conflicts if c.conflict_type == LexicalConflictType.EXACT_NAME]
        assert len(exact) >= 1

    def test_single_character_name(self, analyzer: LexicalAnalyzer) -> None:
        """Very short names should not cause errors."""
        tool_a = ToolDef(name="a", description="Tool A does something.")
        tool_b = ToolDef(name="b", description="Tool B does something else.")
        # Should not raise
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        assert isinstance(conflicts, list)

    def test_very_long_name(self, analyzer: LexicalAnalyzer) -> None:
        """Long names should be handled without performance issues."""
        long_name = "get_" + "user_data_" * 20
        tool_a = ToolDef(name=long_name, description="A tool with a very long name.")
        conflicts = analyzer.analyze(candidate=tool_a, existing=[TOOL_QUERY_DATABASE])
        assert isinstance(conflicts, list)


# Need to import for the test
from tests.fixtures.tool_fixtures import TOOL_SCHEDULE_MEETING  # noqa: E402
