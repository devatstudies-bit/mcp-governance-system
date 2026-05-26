"""AnalysisRun model — tracks every conflict-detection execution."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import TimestampMixin


class AnalysisRunTrigger:
    TOOL_REGISTRATION = "tool_registration"
    TOOL_UPDATE = "tool_update"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    CI_WEBHOOK = "ci_webhook"
    ALL = [TOOL_REGISTRATION, TOOL_UPDATE, SCHEDULED, MANUAL, CI_WEBHOOK]


class AnalysisRunStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ALL = [PENDING, RUNNING, COMPLETED, FAILED]


class AnalysisRun(TimestampMixin, Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    trigger_tool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="SET NULL"), nullable=True
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    trigger: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AnalysisRunStatus.PENDING
    )
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)

    # Snapshot of the full tool set at analysis time — ensures reproducibility
    tool_set_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    probe_query_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )
    conflict_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True
    )

    # Aggregate results
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    routing_shift_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_conflicts_found: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Duration in seconds — denormalized for quick queries
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)

    # Relationships
    environment: Mapped["Environment"] = relationship(  # type: ignore[name-defined]
        "Environment", back_populates="analysis_runs"
    )
    trigger_tool: Mapped["Tool | None"] = relationship(  # type: ignore[name-defined]
        "Tool", foreign_keys=[trigger_tool_id]
    )
    conflicts: Mapped[list["Conflict"]] = relationship(  # type: ignore[name-defined]
        "Conflict", back_populates="analysis_run"
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisRun id={self.id} trigger={self.trigger!r} status={self.status!r}>"
        )
