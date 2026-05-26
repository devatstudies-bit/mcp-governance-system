"""Phase 3B — Approval workflow Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from mtgs.schemas.common import CamelModel


class CreateApprovalRequest(CamelModel):
    """POST /api/v1/approvals/ — request human review of a conflict."""

    conflict_id: uuid.UUID
    tool_id: uuid.UUID
    environment_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=1000)


class DecideApprovalRequest(CamelModel):
    """PATCH /api/v1/approvals/{id}/decide — approve or reject."""

    decision: Literal["approve", "reject"]
    comment: str = Field(default="", max_length=2000)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        return v


class ApprovalResponse(CamelModel):
    """Single approval request as returned by the API."""

    id: str
    conflict_id: str
    tool_id: str
    environment_id: str
    requested_by: str
    reason: str
    status: str
    reviewer_id: str | None = None
    comment: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class ApprovalListResponse(CamelModel):
    """Paginated list of approval requests."""

    items: list[ApprovalResponse]
    total: int
    pending_count: int
