"""
Reusable SQLAlchemy model mixins.

TimestampMixin  — created_at / updated_at auto-managed
SoftDeleteMixin — deleted_at / is_deleted (never physically delete rows)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds created_at + updated_at columns, both managed automatically."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=func.now(),
        onupdate=utcnow,
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Soft-delete support.
    NEVER use Session.delete() — call model.soft_delete() instead.
    Filter active records with `.where(Model.is_deleted == False)`.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def soft_delete(self) -> None:
        self.deleted_at = utcnow()
        self.is_deleted = True
