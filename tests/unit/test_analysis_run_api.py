"""
Unit tests for Phase 3A — Analysis Run API endpoints.

Tests /api/v1/analysis-runs/* — list, get, trigger, history/stats.
DB is mocked via FastAPI dependency overrides.

Run:
    pytest tests/unit/test_analysis_run_api.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

SAMPLE_RUN_ID = str(uuid.uuid4())
SAMPLE_ENV_ID = str(uuid.uuid4())
SAMPLE_TOOL_ID = str(uuid.uuid4())


@pytest.fixture
def sample_run_payload() -> dict:
    """Minimal analysis run as returned by the DB layer."""
    return {
        "id": SAMPLE_RUN_ID,
        "environment_id": SAMPLE_ENV_ID,
        "trigger": "TOOL_REGISTRATION",
        "status": "COMPLETED",
        "total_conflicts_found": 2,
        "risk_score": 65.0,
        "duration_seconds": 3.4,
        "started_at": datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc).isoformat(),
        "completed_at": datetime(2025, 1, 1, 12, 0, 3, tzinfo=timezone.utc).isoformat(),
        "llm_model": "gpt-4o",
        "embedding_model": "text-embedding-3-large",
    }


class TestAnalysisRunEndpoints:
    @pytest.mark.asyncio
    async def test_get_analysis_runs_helper_returns_list(self) -> None:
        """get_analysis_runs() helper returns a list when the DB yields results."""
        from mtgs.api.v1.analysis_runs import get_analysis_runs

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        runs = await get_analysis_runs(
            db=mock_db,
            environment_id=None,
            status_filter=None,
            page=1,
            page_size=20,
        )
        assert isinstance(runs, list)

    @pytest.mark.asyncio
    async def test_get_analysis_run_by_id_returns_none_when_missing(self) -> None:
        """get_analysis_run_by_id() returns None for an unknown run id."""
        from mtgs.api.v1.analysis_runs import get_analysis_run_by_id

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_analysis_run_by_id(mock_db, uuid.uuid4())
        assert result is None

    def test_trigger_analysis_schema(self) -> None:
        """TriggerAnalysisRequest must have required fields."""
        from mtgs.schemas.analysis_run import TriggerAnalysisRequest

        req = TriggerAnalysisRequest(
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
        )
        assert str(req.tool_id) == SAMPLE_TOOL_ID
        assert str(req.environment_id) == SAMPLE_ENV_ID

    def test_analysis_run_response_schema(self, sample_run_payload) -> None:
        """AnalysisRunResponse should parse the sample payload cleanly."""
        from mtgs.schemas.analysis_run import AnalysisRunResponse

        resp = AnalysisRunResponse(**sample_run_payload)
        assert str(resp.id) == SAMPLE_RUN_ID
        assert resp.status == "COMPLETED"
        assert resp.risk_score == 65.0

    def test_analysis_stats_schema(self) -> None:
        """AnalysisStatsResponse should hold aggregated metrics."""
        from mtgs.schemas.analysis_run import AnalysisStatsResponse

        stats = AnalysisStatsResponse(
            total_runs=42,
            avg_risk_score=31.5,
            avg_duration_seconds=2.8,
            runs_last_24h=5,
            critical_conflicts_last_24h=1,
        )
        assert stats.total_runs == 42
        assert stats.avg_risk_score == 31.5
