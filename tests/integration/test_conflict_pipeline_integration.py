"""
Integration tests for the full conflict detection pipeline.

These tests use a real SQLite DB but mock Azure services.

Run:
    pytest tests/integration/test_conflict_pipeline_integration.py -v -m integration
"""

from __future__ import annotations

import pytest

from mtgs.core.conflict_detection.pipeline import (
    ConflictDetectionPipeline,
    PipelineStage,
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
)

pytestmark = pytest.mark.integration


class TestFullPipelineWithMocks:
    def test_exact_name_conflict_pipeline(self) -> None:
        pipeline = ConflictDetectionPipeline(embedding_service=None)
        result = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        assert result.has_critical
        assert result.highest_severity == "CRITICAL"
        assert PipelineStage.LEXICAL in result.stages_executed
        assert PipelineStage.SCHEMA in result.stages_executed
        # No embedding service → semantic stage skipped
        assert PipelineStage.SEMANTIC not in result.stages_executed

    def test_schema_collision_detected(self) -> None:
        pipeline = ConflictDetectionPipeline(embedding_service=None)
        result = pipeline.run_sync(
            candidate=TOOL_GET_USER_A,
            existing=[TOOL_GET_USER_B],
        )
        # user_id: integer vs string → MEDIUM conflict
        assert any(c.conflict_type == "TYPE_COLLISION" for c in result.conflicts)

    def test_clean_tools_no_conflicts(self) -> None:
        pipeline = ConflictDetectionPipeline(embedding_service=None)
        result = pipeline.run_sync(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
        )
        assert not result.has_critical
        assert result.highest_severity is None

    def test_pipeline_result_duration_is_positive(self) -> None:
        pipeline = ConflictDetectionPipeline(embedding_service=None)
        result = pipeline.run_sync(
            candidate=TOOL_CREATE_TASK,
            existing=[TOOL_ADD_TODO],
        )
        assert result.duration_ms > 0

    def test_conflict_count_by_severity_structure(self) -> None:
        pipeline = ConflictDetectionPipeline(embedding_service=None)
        result = pipeline.run_sync(
            candidate=TOOL_SEND_MESSAGE_SLACK,
            existing=[TOOL_SEND_MESSAGE_EMAIL],
        )
        counts = result.conflict_count_by_severity
        assert "CRITICAL" in counts
        assert "HIGH" in counts
        assert counts["CRITICAL"] >= 1

    @pytest.mark.asyncio
    async def test_async_pipeline_with_mock_search(
        self, mock_search_client
    ) -> None:
        """Stage 3 runs when embedding service is provided, even if it returns empty results."""
        pipeline = ConflictDetectionPipeline(embedding_service=mock_search_client)
        result = await pipeline.run_async(
            candidate=TOOL_QUERY_DATABASE,
            existing=[TOOL_GENERATE_INVOICE],
            candidate_embedding=[0.1] * 3072,
        )
        assert PipelineStage.SEMANTIC in result.stages_executed
        # Mock returns no hits → no semantic conflicts
        assert not result.has_critical
