"""Environment model — scopes tool registries (dev / staging / prod)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import TimestampMixin

DEFAULT_POLICY: dict[str, Any] = {
    "max_severity_to_block": "HIGH",
    "auto_approve_below": "LOW",
    "require_approval_for_suppression": True,
    "notification_channels": [],
    "health_score_alert_threshold": 60,
}


class Environment(TimestampMixin, Base):
    __tablename__ = "environments"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_env_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # dev | staging | prod (or custom)
    policy: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=lambda: DEFAULT_POLICY.copy()
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]
        "Organization", back_populates="environments"
    )
    tools: Mapped[list["Tool"]] = relationship(  # type: ignore[name-defined]
        "Tool", back_populates="environment", cascade="all, delete-orphan"
    )
    mcp_servers: Mapped[list["McpServer"]] = relationship(  # type: ignore[name-defined]
        "McpServer", back_populates="environment", cascade="all, delete-orphan"
    )
    conflicts: Mapped[list["Conflict"]] = relationship(  # type: ignore[name-defined]
        "Conflict", back_populates="environment", cascade="all, delete-orphan"
    )
    probe_queries: Mapped[list["ProbeQuery"]] = relationship(  # type: ignore[name-defined]
        "ProbeQuery", back_populates="environment", cascade="all, delete-orphan"
    )
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(  # type: ignore[name-defined]
        "AnalysisRun", back_populates="environment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Environment id={self.id} name={self.name!r}>"
