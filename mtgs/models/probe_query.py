"""ProbeQuery model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import TimestampMixin


class ProbeQuerySource:
    SYSTEM_GENERATED = "system_generated"
    MANUAL = "manual"
    PRODUCTION_LOG = "production_log"
    ADVERSARIAL = "adversarial"
    ALL = [SYSTEM_GENERATED, MANUAL, PRODUCTION_LOG, ADVERSARIAL]


class ProbeQuery(TimestampMixin, Base):
    __tablename__ = "probe_queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expected_tool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="SET NULL"), nullable=True
    )

    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProbeQuerySource.MANUAL
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    environment: Mapped["Environment"] = relationship(  # type: ignore[name-defined]
        "Environment", back_populates="probe_queries"
    )
    expected_tool: Mapped["Tool | None"] = relationship(  # type: ignore[name-defined]
        "Tool", foreign_keys=[expected_tool_id]
    )

    def __repr__(self) -> str:
        return f"<ProbeQuery id={self.id} source={self.source!r}>"
