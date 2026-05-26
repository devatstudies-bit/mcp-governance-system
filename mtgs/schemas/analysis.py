"""Analysis run and health schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from mtgs.schemas.common import CamelModel, TimestampSchema


class AnalysisRunRequest(CamelModel):
    probe_count: int = Field(default=50, ge=1, le=500)
    model: str = Field(default="gpt-4o")
    run_simulation: bool = True


class AnalysisRunResponse(CamelModel):
    """API response for a single analysis run — all nullable fields have defaults."""

    id: uuid.UUID
    environment_id: uuid.UUID
    trigger: str
    status: str
    llm_model: str = ""
    embedding_model: str = ""
    risk_score: float | None = None
    routing_shift_pct: float | None = None
    total_conflicts_found: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None
    report_url: str | None = None


class EnvironmentHealthResponse(CamelModel):
    """GET /environments/{env_id}/health"""

    score: float = Field(ge=0, le=100, description="0–100 health score")
    active_tools: int
    open_conflicts: dict[str, int] = Field(
        description="Count per severity: {CRITICAL: 0, HIGH: 2, ...}"
    )
    last_analysis: datetime | None
    coverage: dict[str, Any] = Field(
        description="{probe_queries: N, tools_with_probes_pct: 0.0–100.0}"
    )
    trend: str = Field(description="improving | stable | degrading")
