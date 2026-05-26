"""Conflict schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from mtgs.schemas.common import CamelModel, TimestampSchema


class ConflictResponse(TimestampSchema):
    id: uuid.UUID
    environment_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    conflict_type: str
    severity: str
    status: str
    tool_ids: list[uuid.UUID]
    conflict_score: float | None
    evidence: dict[str, Any]
    detected_at: datetime
    resolved_at: datetime | None
    resolution_notes: str | None
    recommendations_count: int = 0


class ConflictUpdateRequest(CamelModel):
    """PATCH /conflicts/{id} — change status"""

    status: str = Field(description="open | acknowledged | resolved | suppressed")
    resolution_notes: str | None = None


class ConflictFilterParams(CamelModel):
    severity: list[str] | None = None
    status: list[str] | None = None
    conflict_type: list[str] | None = None
    tool_id: uuid.UUID | None = None
    server_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
