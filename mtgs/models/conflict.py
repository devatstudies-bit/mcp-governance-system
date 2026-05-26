"""Conflict model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import TimestampMixin


class ConflictType:
    EXACT_NAME = "EXACT_NAME"
    SIMILAR_NAME = "SIMILAR_NAME"
    SEMANTIC_OVERLAP = "SEMANTIC_OVERLAP"
    SCHEMA_COLLISION = "SCHEMA_COLLISION"
    INTENT_AMBIGUITY = "INTENT_AMBIGUITY"
    SCOPE_BLEED = "SCOPE_BLEED"
    SUPERSEDED = "SUPERSEDED"
    ALL = [
        EXACT_NAME, SIMILAR_NAME, SEMANTIC_OVERLAP,
        SCHEMA_COLLISION, INTENT_AMBIGUITY, SCOPE_BLEED, SUPERSEDED
    ]


class ConflictStatus:
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"
    ALL = [OPEN, ACKNOWLEDGED, RESOLVED, SUPPRESSED]


class Conflict(TimestampMixin, Base):
    __tablename__ = "conflicts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    conflict_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ConflictStatus.OPEN
    )

    # Store involved tool IDs as a PostgreSQL UUID array
    tool_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    conflict_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Rich evidence blob: similarity scores, affected probe IDs, routing splits, etc.
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    environment: Mapped["Environment"] = relationship(  # type: ignore[name-defined]
        "Environment", back_populates="conflicts"
    )
    analysis_run: Mapped["AnalysisRun | None"] = relationship(  # type: ignore[name-defined]
        "AnalysisRun", back_populates="conflicts"
    )
    resolved_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[resolved_by_id]
    )
    recommendations: Mapped[list["Recommendation"]] = relationship(  # type: ignore[name-defined]
        "Recommendation", back_populates="conflict", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Conflict id={self.id} type={self.conflict_type!r} "
            f"severity={self.severity!r} status={self.status!r}>"
        )
