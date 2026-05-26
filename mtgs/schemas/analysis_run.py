"""
Phase 3A — Analysis Run API schemas.

Supplements the existing mtgs.schemas.analysis module with:
  - TriggerAnalysisRequest  — POST /api/v1/analysis-runs/
  - AnalysisRunResponse     — re-exported from analysis.py for convenience
  - AnalysisStatsResponse   — GET /api/v1/analysis-runs/stats
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from mtgs.schemas.analysis import AnalysisRunResponse  # re-export
from mtgs.schemas.common import CamelModel

__all__ = [
    "TriggerAnalysisRequest",
    "AnalysisRunResponse",
    "AnalysisStatsResponse",
    "AnalysisRunListResponse",
]


class TriggerAnalysisRequest(CamelModel):
    """POST body for manually triggering an analysis run."""

    tool_id: uuid.UUID = Field(description="ID of the tool to analyse")
    environment_id: uuid.UUID = Field(description="Environment the tool belongs to")
    probe_count: int = Field(default=50, ge=1, le=500)
    run_simulation: bool = Field(default=True)
    run_recommendations: bool = Field(default=True)


class AnalysisStatsResponse(CamelModel):
    """Aggregate statistics for analysis runs (dashboard endpoint)."""

    total_runs: int = Field(ge=0)
    avg_risk_score: float = Field(ge=0.0, le=100.0)
    avg_duration_seconds: float = Field(ge=0.0)
    runs_last_24h: int = Field(ge=0)
    critical_conflicts_last_24h: int = Field(ge=0)
    high_conflicts_last_24h: int = Field(default=0, ge=0)
    tools_analysed: int = Field(default=0, ge=0)


class AnalysisRunListResponse(CamelModel):
    """Paginated list of analysis runs."""

    items: list[AnalysisRunResponse]
    total: int
    page: int = 1
    page_size: int = 20
