"""Recommendation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from mtgs.schemas.common import CamelModel, TimestampSchema


class RecommendationResponse(TimestampSchema):
    id: uuid.UUID
    conflict_id: uuid.UUID
    target_tool_id: uuid.UUID
    recommendation_type: str
    proposed_change: dict[str, Any]
    predicted_score_after: float | None
    rationale: str
    status: str
    reviewed_at: datetime | None


class RecommendationReviewRequest(CamelModel):
    apply: bool = Field(default=False, description="If True, auto-apply the proposed change")


class RecommendationRejectRequest(CamelModel):
    reason: str = Field(min_length=1)
