"""Conflict management endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mtgs.auth.dependencies import AuthenticatedUser, require_role
from mtgs.database import get_db
from mtgs.models.conflict import Conflict, ConflictStatus
from mtgs.schemas.common import PaginatedResponse
from mtgs.schemas.conflict import ConflictResponse, ConflictUpdateRequest
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/environments/{env_id}/conflicts", tags=["conflicts"])


@router.get(
    "",
    response_model=PaginatedResponse[ConflictResponse],
    summary="List conflicts in an environment",
)
async def list_conflicts(
    env_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    severity: list[str] | None = Query(default=None),
    conflict_status: str | None = Query(default=None, alias="status"),
    conflict_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("viewer")),
) -> PaginatedResponse[ConflictResponse]:
    query = (
        select(Conflict)
        .where(Conflict.environment_id == env_id)
        .order_by(Conflict.detected_at.desc())
    )
    if severity:
        query = query.where(Conflict.severity.in_(severity))
    if conflict_status:
        query = query.where(Conflict.status == conflict_status)
    if conflict_type:
        query = query.where(Conflict.conflict_type == conflict_type)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    conflicts = result.scalars().all()

    items = [
        ConflictResponse(
            id=c.id,
            environment_id=c.environment_id,
            analysis_run_id=c.analysis_run_id,
            conflict_type=c.conflict_type,
            severity=c.severity,
            status=c.status,
            tool_ids=c.tool_ids,
            conflict_score=float(c.conflict_score) if c.conflict_score else None,
            evidence=c.evidence,
            detected_at=c.detected_at,
            resolved_at=c.resolved_at,
            resolution_notes=c.resolution_notes,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conflicts
    ]
    return PaginatedResponse.from_list(items, total=total, page=page, page_size=page_size)


@router.get(
    "/{conflict_id}",
    response_model=ConflictResponse,
    summary="Get conflict detail",
)
async def get_conflict(
    env_id: uuid.UUID,
    conflict_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("viewer")),
) -> ConflictResponse:
    result = await db.execute(
        select(Conflict).where(
            Conflict.id == conflict_id,
            Conflict.environment_id == env_id,
        )
    )
    conflict = result.scalar_one_or_none()
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    return ConflictResponse(
        id=conflict.id,
        environment_id=conflict.environment_id,
        analysis_run_id=conflict.analysis_run_id,
        conflict_type=conflict.conflict_type,
        severity=conflict.severity,
        status=conflict.status,
        tool_ids=conflict.tool_ids,
        conflict_score=float(conflict.conflict_score) if conflict.conflict_score else None,
        evidence=conflict.evidence,
        detected_at=conflict.detected_at,
        resolved_at=conflict.resolved_at,
        resolution_notes=conflict.resolution_notes,
        created_at=conflict.created_at,
        updated_at=conflict.updated_at,
    )


@router.patch(
    "/{conflict_id}",
    response_model=ConflictResponse,
    summary="Update conflict status (acknowledge / resolve / suppress)",
)
async def update_conflict_status(
    env_id: uuid.UUID,
    conflict_id: uuid.UUID,
    body: ConflictUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("reviewer")),
) -> ConflictResponse:
    result = await db.execute(
        select(Conflict).where(
            Conflict.id == conflict_id,
            Conflict.environment_id == env_id,
        )
    )
    conflict = result.scalar_one_or_none()
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")

    if body.status not in ConflictStatus.ALL:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {ConflictStatus.ALL}",
        )

    # Suppress CRITICAL requires admin
    if body.status == ConflictStatus.SUPPRESSED and conflict.severity == "CRITICAL":
        from mtgs.auth.security import has_minimum_role
        if not has_minimum_role(current_user.role, "admin"):
            raise HTTPException(
                status_code=403,
                detail="Suppressing CRITICAL conflicts requires admin role.",
            )

    conflict.status = body.status
    if body.resolution_notes:
        conflict.resolution_notes = body.resolution_notes
    if body.status in (ConflictStatus.RESOLVED, ConflictStatus.SUPPRESSED):
        conflict.resolved_at = datetime.now(timezone.utc)
        conflict.resolved_by_id = current_user.id

    await db.commit()
    logger.info(
        "conflict_status_updated",
        conflict_id=str(conflict_id),
        new_status=body.status,
        user_id=str(current_user.id),
    )

    return ConflictResponse(
        id=conflict.id,
        environment_id=conflict.environment_id,
        analysis_run_id=conflict.analysis_run_id,
        conflict_type=conflict.conflict_type,
        severity=conflict.severity,
        status=conflict.status,
        tool_ids=conflict.tool_ids,
        conflict_score=float(conflict.conflict_score) if conflict.conflict_score else None,
        evidence=conflict.evidence,
        detected_at=conflict.detected_at,
        resolved_at=conflict.resolved_at,
        resolution_notes=conflict.resolution_notes,
        created_at=conflict.created_at,
        updated_at=conflict.updated_at,
    )
