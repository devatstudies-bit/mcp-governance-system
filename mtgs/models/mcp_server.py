"""MCP Server model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import SoftDeleteMixin, TimestampMixin


class McpServer(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sync_interval_minutes: Mapped[int] = mapped_column(nullable=False, default=60)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # ok | failed | partial

    # Relationships
    environment: Mapped["Environment"] = relationship(  # type: ignore[name-defined]
        "Environment", back_populates="mcp_servers"
    )
    owner_team: Mapped["Team | None"] = relationship(  # type: ignore[name-defined]
        "Team", foreign_keys=[owner_team_id]
    )
    tools: Mapped[list["Tool"]] = relationship(  # type: ignore[name-defined]
        "Tool", back_populates="server", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<McpServer id={self.id} name={self.name!r}>"
