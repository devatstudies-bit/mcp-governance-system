"""Health and metrics endpoints."""

from __future__ import annotations

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mtgs.auth.dependencies import require_role
from mtgs.database import get_db, check_db_health
from mtgs.models.analysis_run import AnalysisRun, AnalysisRunStatus
from mtgs.models.conflict import Conflict, ConflictStatus
from mtgs.models.probe_query import ProbeQuery
from mtgs.models.tool import Tool, ToolStatus
from mtgs.schemas.analysis import EnvironmentHealthResponse
from mtgs.schemas.common import MessageResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=MessageResponse, summary="Service liveness check")
async def liveness() -> MessageResponse:
    """Simple liveness probe — returns 200 if the process is running."""
    return MessageResponse(message="ok")


@router.get("/readiness", response_model=MessageResponse, summary="Service readiness check")
async def readiness() -> MessageResponse:
    """
    Readiness probe — checks DB connectivity.
    Returns 503 if DB is unreachable.
    """
    from fastapi import HTTPException, status

    db_ok = await check_db_health()
    if not db_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    return MessageResponse(message="ready")


@router.get(
    "/environments/{env_id}/health",
    response_model=EnvironmentHealthResponse,
    summary="Environment governance health score",
)
async def environment_health(
    env_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("viewer")),
) -> EnvironmentHealthResponse:
    """
    Compute the 0–100 governance health score for an environment.

    Score formula:
      base = 100
      - 20 per CRITICAL open conflict
      - 10 per HIGH open conflict
      - 5  per MEDIUM open conflict
      - 2  per LOW open conflict
      Floor: 0
    """
    # Active tools count
    tools_result = await db.execute(
        select(func.count(Tool.id)).where(
            Tool.environment_id == env_id,
            Tool.status == ToolStatus.ACTIVE,
            Tool.is_deleted == False,
        )
    )
    active_tools = tools_result.scalar_one() or 0

    # Open conflicts by severity
    conflicts_result = await db.execute(
        select(Conflict.severity, func.count(Conflict.id)).where(
            Conflict.environment_id == env_id,
            Conflict.status == ConflictStatus.OPEN,
        ).group_by(Conflict.severity)
    )
    open_conflicts: dict[str, int] = defaultdict(int)
    for severity, count in conflicts_result:
        open_conflicts[severity] = count

    # Health score calculation
    deductions = (
        open_conflicts.get("CRITICAL", 0) * 20
        + open_conflicts.get("HIGH", 0) * 10
        + open_conflicts.get("MEDIUM", 0) * 5
        + open_conflicts.get("LOW", 0) * 2
    )
    score = max(0.0, 100.0 - deductions)

    # Trend — compare with last 2 runs
    runs_result = await db.execute(
        select(AnalysisRun.risk_score)
        .where(
            AnalysisRun.environment_id == env_id,
            AnalysisRun.status == AnalysisRunStatus.COMPLETED,
        )
        .order_by(AnalysisRun.completed_at.desc())
        .limit(3)
    )
    recent_scores = [r[0] for r in runs_result if r[0] is not None]
    if len(recent_scores) >= 2:
        trend = (
            "improving" if recent_scores[0] < recent_scores[1]
            else "degrading" if recent_scores[0] > recent_scores[1]
            else "stable"
        )
    else:
        trend = "stable"

    # Last analysis timestamp
    last_run_result = await db.execute(
        select(AnalysisRun.completed_at)
        .where(
            AnalysisRun.environment_id == env_id,
            AnalysisRun.status == AnalysisRunStatus.COMPLETED,
        )
        .order_by(AnalysisRun.completed_at.desc())
        .limit(1)
    )
    last_analysis = last_run_result.scalar_one_or_none()

    # Probe query coverage
    probe_count_result = await db.execute(
        select(func.count(ProbeQuery.id)).where(
            ProbeQuery.environment_id == env_id,
            ProbeQuery.is_active == True,
        )
    )
    probe_count = probe_count_result.scalar_one() or 0
    tools_with_probes_pct = (
        min(100.0, (probe_count / max(active_tools, 1)) * 100)
        if active_tools
        else 0.0
    )

    return EnvironmentHealthResponse(
        score=round(score, 1),
        active_tools=active_tools,
        open_conflicts={
            "CRITICAL": open_conflicts.get("CRITICAL", 0),
            "HIGH": open_conflicts.get("HIGH", 0),
            "MEDIUM": open_conflicts.get("MEDIUM", 0),
            "LOW": open_conflicts.get("LOW", 0),
            "INFO": open_conflicts.get("INFO", 0),
        },
        last_analysis=last_analysis,
        coverage={
            "probe_queries": probe_count,
            "tools_with_probes_pct": round(tools_with_probes_pct, 1),
        },
        trend=trend,
    )
