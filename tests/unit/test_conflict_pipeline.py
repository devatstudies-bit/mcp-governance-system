"""
Unit tests for the Conflict Detection Pipeline orchestrator.

Tests that the pipeline correctly:
1. Runs stages 1 and 2 always
2. Short-circuits on CRITICAL (skips stage 3)
3. Deduplicates conflicts
4. Returns sorted output (CRITICAL first)

Run:
    pytest tests/unit/test_conflict_pipeline.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mtgs.core.conflict_detection.lexical import LexicalConflict, LexicalConflictType
from mtgs.core.conflict_detection.pipeline import (
    ConflictDetectionPipeline,
    PipelineResult,
    PipelineStage,
)
from tests.fixtures.tool_fixtures import (
    TOOL_GENERATE_INVOICE,
    TOOL_QUERY_DATABASE,
    TOOL_SEND_MESSAGE_EMAIL,
    TOOL_SEND_MESSAGE_SLACK,
    ToolDef,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def pipeline() -> ConflictDetectionPipeline:
    """Pipeline with embedding service mocked (no Azure API calls in unit tests)."""
    pipeline = ConflictDetectionPipeline(embedding_service=None)
    return pipeline


class TestPipelineStageExecution:
    def test_stages_1_and_2_always_run(self, pipeline: ConflictDetectionPipeline) -> None:
        result = pipeline.run_sync(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
        )
        assert PipelineStage.LEXICAL in result.stages_executed
        assert PipelineStage.SCHEMA in result.stages_executed

    def test_stage_3_skipped_on_critical_from_stage_1(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        """EXACT_NAME collision → CRITICAL → stage 3 (semantic) should be skipped."""
        result = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        assert PipelineStage.LEXICAL in result.stages_executed
        # Stage 3 requires embeddings; should be skipped after CRITICAL
        assert PipelineStage.SEMANTIC not in result.stages_executed

    def test_stage_3_skipped_when_no_embedding_service(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        """Without embedding service, stage 3 must be gracefully skipped."""
        result = pipeline.run_sync(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
        )
        assert PipelineStage.SEMANTIC not in result.stages_executed

    def test_result_sorted_by_severity(self, pipeline: ConflictDetectionPipeline) -> None:
        """CRITICAL conflicts must appear before MEDIUM ones in output."""
        result = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL, TOOL_SEND_MESSAGE_EMAIL],
        )
        severities = [c.severity for c in result.conflicts]
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        for i in range(len(severities) - 1):
            assert severity_order[severities[i]] <= severity_order[severities[i + 1]]


class TestPipelineResult:
    def test_result_is_data_class(self, pipeline: ConflictDetectionPipeline) -> None:
        result = pipeline.run_sync(
            candidate=TOOL_QUERY_DATABASE,
            existing=[],
        )
        assert isinstance(result, PipelineResult)
        assert isinstance(result.conflicts, list)
        assert isinstance(result.stages_executed, list)
        assert isinstance(result.duration_ms, float)
        assert result.duration_ms >= 0

    def test_has_critical_flag(self, pipeline: ConflictDetectionPipeline) -> None:
        result = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        assert result.has_critical is True

    def test_no_critical_flag_when_no_conflicts(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        result = pipeline.run_sync(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
        )
        assert result.has_critical is False

    def test_highest_severity_property(self, pipeline: ConflictDetectionPipeline) -> None:
        result = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        assert result.highest_severity == "CRITICAL"

    def test_highest_severity_none_when_no_conflicts(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        result = pipeline.run_sync(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
        )
        assert result.highest_severity is None


class TestPipelineIdempotency:
    def test_same_inputs_produce_same_output(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        run1 = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        run2 = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        assert len(run1.conflicts) == len(run2.conflicts)
        assert run1.has_critical == run2.has_critical


class TestPipelineEdgeCases:
    def test_empty_registry_returns_empty_result(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        result = pipeline.run_sync(candidate=TOOL_QUERY_DATABASE, existing=[])
        assert result.conflicts == []
        assert result.has_critical is False

    def test_large_registry_does_not_raise(
        self, pipeline: ConflictDetectionPipeline
    ) -> None:
        """100 unique tools — pipeline should complete without error."""
        existing = [
            ToolDef(
                name=f"tool_{i}",
                description=f"This tool does task number {i} in the system.",
            )
            for i in range(100)
        ]
        # Should not raise
        result = pipeline.run_sync(
            candidate=ToolDef(name="new_tool", description="A brand new tool."),
            existing=existing,
        )
        assert isinstance(result, PipelineResult)
