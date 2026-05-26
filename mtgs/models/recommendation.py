"""Recommendation model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import TimestampMixin


class RecommendationType:
    RENAME = "RENAME"
    DESCRIPTION_REWRITE = "DESCRIPTION_REWRITE"
    SCOPE_NARROWING = "SCOPE_NARROWING"
    SCHEMA_CLARIFICATION = "SCHEMA_CLARIFICATION"
    DEPRECATE = "DEPRECATE"
    ALL = [RENAME, DESCRIPTION_REWRITE, SCOPE_NARROWING, SCHEMA_CLARIFICATION, DEPRECATE]


class RecommendationStatus:
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIALLY_APPLIED = "partially_applied"
    ALL = [PENDING, ACCEPTED, REJECTED, PARTIALLY_APPLIED]


class Recommendation(TimestampMixin, Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conflict_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conflicts.id", ondelete="CASCADE"), nullable=False
    )
    target_tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False
    )
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # {field: 'description', before: '...', after: '...'}
    proposed_change: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    predicted_score_after: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=RecommendationStatus.PENDING
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    conflict: Mapped["Conflict"] = relationship(  # type: ignore[name-defined]
        "Conflict", back_populates="recommendations"
    )
    target_tool: Mapped["Tool"] = relationship(  # type: ignore[name-defined]
        "Tool", foreign_keys=[target_tool_id]
    )
    reviewed_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[reviewed_by_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Recommendation id={self.id} type={self.recommendation_type!r} "
            f"status={self.status!r}>"
        )
