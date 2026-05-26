"""
Phase 3C — Audit Log API endpoints.

Routes
------
GET  /api/v1/audit-logs/          — list entries (paginated, filterable)
GET  /api/v1/audit-logs/export    — download full log as JSON or CEF
GET  /api/v1/audit-logs/actions   — list valid AuditAction values (for UI dropdowns)

All endpoints require viewer+ authentication.
Export endpoint requires reviewer+ (sensitive: full actor history).

SIEM integration
----------------
The /export?format=cef endpoint produces RFC-5424-like CEF lines that can be
piped directly into Splunk, Microsoft Sentinel, or IBM QRadar by pointing the
SIEM forwarder at:

    curl -H "Authorization: Bearer $TOKEN" \\
         "$MTGS_URL/v1/api/audit-logs/export?format=cef" \\
         >> /var/log/mtgs/audit.cef
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from mtgs.auth.dependencies import require_role
from mtgs.core.audit.logger import AuditAction, AuditEntry
from mtgs.core.audit.service import AuditLogService
from mtgs.schemas.audit import AuditEntryResponse, AuditListResponse

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

# Module-level singleton — injectable via Depends() for testing
_service = AuditLogService()


def get_audit_service() -> AuditLogService:
    return _service


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _entry_to_response(entry: AuditEntry) -> AuditEntryResponse:
    return AuditEntryResponse(
        entry_id=entry.entry_id,
        action=entry.action.value if isinstance(entry.action, AuditAction) else str(entry.action),
        actor_id=entry.actor_id,
        resource_id=entry.resource_id,
        resource_type=entry.resource_type,
        environment_id=entry.environment_id,
        metadata=entry.metadata,
        timestamp=entry.timestamp,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=AuditListResponse,
    summary="List audit log entries",
)
async def list_audit_logs(
    action: str | None = Query(None, description="Filter by AuditAction value"),
    actor_id: str | None = Query(None, description="Filter by actor UUID"),
    resource_id: str | None = Query(None, description="Filter by resource UUID"),
    environment_id: str | None = Query(None, description="Filter by environment UUID"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    svc: AuditLogService = Depends(get_audit_service),
    _user=Depends(require_role("viewer")),
) -> AuditListResponse:
    entries = await svc.list_entries(
        action_filter=action,
        actor_filter=actor_id,
        resource_filter=resource_id,
        environment_filter=environment_id,
        page=page,
        page_size=page_size,
    )
    total = await svc.count(
        action_filter=action,
        actor_filter=actor_id,
        resource_filter=resource_id,
        environment_filter=environment_id,
    )
    return AuditListResponse(
        items=[_entry_to_response(e) for e in entries],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/export",
    summary="Export audit log (JSON or CEF for SIEM)",
)
async def export_audit_logs(
    format: str = Query("json", description="Output format: 'json' or 'cef'"),
    action: str | None = Query(None),
    actor_id: str | None = Query(None),
    resource_id: str | None = Query(None),
    environment_id: str | None = Query(None),
    svc: AuditLogService = Depends(get_audit_service),
    _user=Depends(require_role("reviewer")),
) -> Response:
    """
    Download the full audit log in JSON (structured) or CEF (SIEM) format.

    JSON response: ``Content-Type: application/json``
    CEF  response: ``Content-Type: text/plain`` — one CEF line per entry
    """
    fmt = format.lower().strip()
    exported = await svc.export(
        fmt=fmt,
        action_filter=action,
        actor_filter=actor_id,
        resource_filter=resource_id,
        environment_filter=environment_id,
    )

    if fmt == "cef":
        return PlainTextResponse(
            content="\n".join(exported),
            media_type="text/plain",
            headers={"Content-Disposition": 'attachment; filename="audit.cef"'},
        )

    return JSONResponse(
        content=exported,
        headers={"Content-Disposition": 'attachment; filename="audit.json"'},
    )


@router.get(
    "/actions",
    response_model=list[str],
    summary="List valid audit action types",
)
async def list_audit_actions(
    _user=Depends(require_role("viewer")),
) -> list[str]:
    """Return all valid AuditAction enum values — useful for UI filter dropdowns."""
    return sorted(a.value for a in AuditAction)
