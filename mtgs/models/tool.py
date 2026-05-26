"""
Tool and ToolVersion models.

Tool       — the live, mutable record in the registry
ToolVersion — immutable snapshot of each revision (full audit trail)
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtgs.database import Base
from mtgs.models.mixins import SoftDeleteMixin, TimestampMixin


class ToolStatus:
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    FLAGGED = "flagged"
    PENDING_APPROVAL = "pending_approval"
    ALL = [ACTIVE, DEPRECATED, FLAGGED, PENDING_APPROVAL]


class Tool(TimestampMixin, SoftDeleteMixin, Base):
    """
    An MCP tool definition in the registry.

    The `embedding` column is a float[] (PostgreSQL array) storing the
    3072-dimensional vector from text-embedding-3-large.
    Azure AI Search holds a mirrored copy for ANN queries; pgvector is not
    required — the relational store stays vanilla PostgreSQL.
    """

    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint(
            "environment_id", "server_id", "name",
            name="uq_tool_env_server_name"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    owner_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Core MCP fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Registry metadata
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ToolStatus.ACTIVE
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Embedding — stored as float array; mirrors what's in Azure AI Search
    # Using ARRAY(Float) instead of pgvector to keep vanilla PostgreSQL
    embedding: Mapped[list[float] | None] = mapped_column(
        ARRAY(item_type=__import__("sqlalchemy").Float), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_fingerprint_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # SHA256 of fingerprint text — detect stale embeddings

    # Relationships
    environment: Mapped["Environment"] = relationship(  # type: ignore[name-defined]
        "Environment", back_populates="tools"
    )
    server: Mapped["McpServer"] = relationship(
        "McpServer", back_populates="tools"
    )
    owner_team: Mapped["Team | None"] = relationship(  # type: ignore[name-defined]
        "Team", back_populates="tools"
    )
    created_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_id]
    )
    versions: Mapped[list["ToolVersion"]] = relationship(
        "ToolVersion", back_populates="tool", cascade="all, delete-orphan",
        order_by="ToolVersion.version.asc()"
    )
    conflicts: Mapped[list["Conflict"]] = relationship(  # type: ignore[name-defined]
        "Conflict",
        primaryjoin="Tool.id == any_(foreign(Conflict.tool_ids))",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<Tool id={self.id} name={self.name!r} v={self.version} status={self.status!r}>"


class ToolVersion(TimestampMixin, Base):
    """
    Immutable snapshot of a tool definition at a given version.
    Never updated or deleted — provides full audit trail with diffs.
    """

    __tablename__ = "tool_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tools.id", ondelete="CASCADE"), nullable=False
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # JSON Patch (RFC 6902)

    # Relationships
    tool: Mapped["Tool"] = relationship("Tool", back_populates="versions")
    changed_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[changed_by_id]
    )

    def __repr__(self) -> str:
        return f"<ToolVersion tool_id={self.tool_id} v={self.version}>"
