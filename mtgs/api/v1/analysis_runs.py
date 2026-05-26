"""
Phase 3A — Analysis Run API endpoints.

Routes
------
GET  /api/v1/analysis-runs/           — list runs (paginated, filterable by env/status)
GET  /api/v1/analysis-runs/stats      — aggregate statistics for dashboard
GET  /api/v1/analysis-runs/{run_id}   — get a specific run
POST /api/v1/analysis-runs/           — trigger a run manually
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mtgs.auth.dependencies import require_role
from mtgs.database import get_db
from mtgs.schemas.analysis_run import (
    AnalysisRunListResponse,
    AnalysisRunResponse,
    AnalysisStatsResponse,
    TriggerAnalysisRequest,
)

router = APIRouter(prefix="/analysis-runs", tags=["analysis-runs"])


# ─────────────────────────────────────────────────────────────────────────────
# Dependency helpers (injectable for testing)
# ─────────────────────────────────────────────────────────────────────────────


async def get_analysis_runs(
    db: AsyncSession,
    environment_id: uuid.UUID | None,
    status_filter: str | None,
    page: int,
    page_size: int,
) -> list[Any]:
    """Fetch analysis runs with optional filters."""
    from mtgs.models.analysis_run import AnalysisRun

    q = select(AnalysisRun)
    if environment_id:
        q = q.where(AnalysisRun.environment_id == environment_id)
    if status_filter:
        q = q.where(AnalysisRun.status == status_filter)
    q = q.order_by(AnalysisRun.started_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(q)
    return result.scalars().all()


async def get_analysis_run_by_id(
    db: AsyncSession, run_id: uuid.UUID
) -> Any | None:
    """Fetch a single analysis run by primary key."""
    from mtgs.models.analysis_run import AnalysisRun

    result = await db.execute(
        select(AnalysisRun).where(AnalysisRun.id == run_id)
    )
    return result.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=AnalysisRunListResponse,
    summary="List analysis runs",
)
async def list_analysis_runs(
    environment_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("viewer")),
) -> AnalysisRunListResponse:
    from mtgs.models.analysis_run import AnalysisRun

    runs = await get_analysis_runs(
        db=db,
        environment_id=environment_id,
        status_filter=status,
        page=page,
        page_size=page_size,
    )

    # Count total (without pagination)
    count_q = select(func.count(AnalysisRun.id))
    if environment_id:
        count_q = count_q.where(AnalysisRun.environment_id == environment_id)
    if status:
        count_q = count_q.where(AnalysisRun.status == status)
    total = (await db.execute(count_q)).scalar_one()

    return AnalysisRunListResponse(
        items=[_orm_to_response(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/stats",
    response_model=AnalysisStatsResponse,
    summary="Aggregate analysis run statistics",
)
async def get_analysis_stats(
    environment_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("viewer")),
) -> AnalysisStatsResponse:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import and_

    from mtgs.models.analysis_run import AnalysisRun

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    base_q = select(AnalysisRun)
    if environment_id:
        base_q = base_q.where(AnalysisRun.environment_id == environment_id)

    result = await db.execute(base_q)
    all_runs = result.scalars().all()

    total_runs = len(all_runs)
    completed = [r for r in all_runs if r.risk_score is not None]
    avg_risk = sum(r.risk_score for r in completed) / len(completed) if completed else 0.0
    durations = [r.duration_seconds for r in all_runs if r.duration_seconds]
    avg_dur = sum(durations) / len(durations) if durations else 0.0

    recent = [r for r in all_runs if r.started_at and r.started_at >= since_24h]
    critical = sum(1 for r in recent if r.risk_score and r.risk_score >= 80)

    return AnalysisStatsResponse(
        total_runs=total_runs,
        avg_risk_score=round(avg_risk, 2),
        avg_duration_seconds=round(avg_dur, 2),
        runs_last_24h=len(recent),
        critical_conflicts_last_24h=critical,
    )


@router.get(
    "/{run_id}",
    response_model=AnalysisRunResponse,
    summary="Get a specific analysis run",
)
async def get_analysis_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("viewer")),
) -> AnalysisRunResponse:
    run = await get_analysis_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found")
    return _orm_to_response(run)


@router.post(
    "/",
    response_model=AnalysisRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger an analysis run",
)
async def trigger_analysis_run(
    body: TriggerAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role("developer")),
) -> AnalysisRunResponse:
    from datetime import datetime, timezone

    from mtgs.models.analysis_run import AnalysisRun, AnalysisRunStatus, AnalysisRunTrigger
    from mtgs.workers.tasks import run_conflict_analysis_task

    run = AnalysisRun(
        environment_id=body.environment_id,
        trigger=AnalysisRunTrigger.MANUAL,
        trigger_tool_id=body.tool_id,
        status=AnalysisRunStatus.PENDING,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        run_conflict_analysis_task,
        tool_id=str(body.tool_id),
        env_id=str(body.environment_id),
    )

    return _orm_to_response(run)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _orm_to_response(run: Any) -> AnalysisRunResponse:
    return AnalysisRunResponse(
        id=run.id,
        environment_id=run.environment_id,
        trigger=run.trigger.value if hasattr(run.trigger, "value") else str(run.trigger),
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        llm_model=run.llm_model or "",
        embedding_model=run.embedding_model or "",
        risk_score=run.risk_score,
        routing_shift_pct=getattr(run, "routing_shift_pct", None),
        total_conflicts_found=run.total_conflicts_found,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_seconds=run.duration_seconds,
        error_message=run.error_message,
        report_url=None,
    )
