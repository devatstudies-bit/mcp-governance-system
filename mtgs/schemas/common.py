"""Common base schemas and reusable types."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base model that accepts snake_case but serializes to camelCase for the frontend."""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,  # allows .model_validate(orm_obj)
        use_enum_values=True,
    )


class TimestampSchema(CamelModel):
    created_at: datetime
    updated_at: datetime


class PaginatedResponse(CamelModel, Generic[T]):
    """Generic paginated list response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def from_list(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> "PaginatedResponse[T]":
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class MessageResponse(CamelModel):
    """Generic success/info message."""

    message: str
    detail: dict[str, Any] | None = None


class ErrorResponse(CamelModel):
    """Standard error envelope."""

    error: str
    detail: str | list[dict[str, Any]] | None = None
    request_id: str | None = None


class PaginationParams(CamelModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
