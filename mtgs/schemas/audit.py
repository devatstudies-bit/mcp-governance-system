"""Phase 3C — Audit log Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from mtgs.schemas.common import CamelModel


class AuditEntryResponse(CamelModel):
    """Single audit log entry as returned by the API."""

    entry_id: str
    action: str
    actor_id: str
    resource_id: str
    resource_type: str
    environment_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class AuditExportRequest(CamelModel):
    """
    Query parameters for GET /api/v1/audit-logs/export.

    format      : "json" (default) or "cef"
    action_filter : restrict to a specific AuditAction value
    actor_filter  : restrict to a specific actor_id
    """

    format: Literal["json", "cef"] = "json"
    action_filter: str | None = None
    actor_filter: str | None = None
    resource_filter: str | None = None
    environment_filter: str | None = None


class AuditListResponse(CamelModel):
    """Paginated list of audit log entries."""

    items: list[AuditEntryResponse]
    total: int
    page: int = 1
    page_size: int = 50
