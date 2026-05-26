"""
Tool Registry API — CRUD + dry-run conflict check.

Endpoints:
  POST   /environments/{env_id}/tools            Register new tool
  GET    /environments/{env_id}/tools            List tools
  GET    /environments/{env_id}/tools/{tool_id}  Get tool detail
  PUT    /environments/{env_id}/tools/{tool_id}  Update tool
  DELETE /environments/{env_id}/tools/{tool_id}  Deprecate tool
  GET    /environments/{env_id}/tools/{tool_id}/history  Version history
  POST   /environments/{env_id}/tools/check      Dry-run / CI gate
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mtgs.auth.dependencies import AuthenticatedUser, require_role
from mtgs.database import get_db
from mtgs.models.conflict import Conflict, ConflictStatus
from mtgs.models.tool import Tool, ToolStatus, ToolVersion
from mtgs.schemas.common import PaginatedResponse
from mtgs.schemas.tool import (
    ToolCheckRequest,
    ToolCheckResponse,
    ToolRegisterRequest,
    ToolRegistrationResponse,
    ToolResponse,
    ToolUpdateRequest,
    ToolVersionResponse,
)
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/environments/{env_id}/tools", tags=["tools"])


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

async def _get_tool_or_404(
    tool_id: uuid.UUID,
    env_id: uuid.UUID,
    db: AsyncSession,
) -> Tool:
    result = await db.execute(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.environment_id == env_id,
            Tool.is_deleted == False,
        )
    )
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


async def _tool_to_response(tool: Tool, db: AsyncSession) -> ToolResponse:
    """Map ORM model to response schema, adding live conflict count."""
    from sqlalchemy import text as sql_text

    # Count open conflicts for this tool (PostgreSQL array operator @>)
    count_result = await db.execute(
        select(func.count(Conflict.id)).where(
            Conflict.tool_ids.contains([tool.id]),
            Conflict.status == ConflictStatus.OPEN,
        )
    )
    conflict_count = count_result.scalar_one() or 0

    return ToolResponse(
        id=tool.id,
        environment_id=tool.environment_id,
        server_id=tool.server_id,
        owner_team_id=tool.owner_team_id,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        status=tool.status,
        version=tool.version,
        embedding_model=tool.embedding_model,
        conflict_count=conflict_count,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /environments/{env_id}/tools/check  (must be before /{tool_id} routes)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/check",
    response_model=ToolCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Dry-run conflict check (CI/CD gate)",
)
async def check_tool(
    env_id: uuid.UUID,
    body: ToolCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("developer")),
) -> ToolCheckResponse:
    """
    Run a full conflict check on a candidate tool WITHOUT registering it.
    Use this as a CI/CD gate before registering tools in production.
    """
    from mtgs.core.tool_def import ToolDef
    from mtgs.core.conflict_detection.pipeline import ConflictDetectionPipeline

    # Load all active tools in this environment
    result = await db.execute(
        select(Tool).where(
            Tool.environment_id == env_id,
            Tool.status == ToolStatus.ACTIVE,
            Tool.is_deleted == False,
        )
    )
    existing_tools = result.scalars().all()

    # Convert to ToolDef DTOs for the engine
    existing_defs = [
        ToolDef(
            name=t.name,
            description=t.description,
            input_schema=t.input_schema,
            server_name=str(t.server_id),
        )
        for t in existing_tools
    ]
    candidate_def = ToolDef(
        name=body.name,
        description=body.description,
        input_schema=body.input_schema,
        server_name=str(body.server_id),
    )

    pipeline = ConflictDetectionPipeline()
    pipeline_result = pipeline.run_sync(
        candidate=candidate_def,
        existing=existing_defs,
    )

    # Determine pass/fail based on environment policy
    env_result = await db.execute(
        select(__import__("mtgs.models.environment", fromlist=["Environment"]).Environment)
        .where(__import__("mtgs.models.environment", fromlist=["Environment"]).Environment.id == env_id)
    )
    env = env_result.scalar_one_or_none()
    fail_severity = (env.policy.get("max_severity_to_block", "HIGH") if env else "HIGH")
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    fail_threshold = severity_order.get(fail_severity, 1)

    blocking_conflicts = []
    warnings = []
    for c in pipeline_result.conflicts:
        c_dict = {
            "type": c.conflict_type,
            "severity": c.severity,
            "conflicting_tool": c.conflicting_name,
            "score": c.conflict_score,
            "evidence": c.evidence,
        }
        if severity_order.get(c.severity, 99) <= fail_threshold:
            blocking_conflicts.append(c_dict)
        else:
            warnings.append(c_dict)

    passed = len(blocking_conflicts) == 0
    highest_blocking = blocking_conflicts[0]["severity"] if blocking_conflicts else None

    logger.info(
        "tool_check_completed",
        env_id=str(env_id),
        tool_name=body.name,
        passed=passed,
        conflicts=len(pipeline_result.conflicts),
        duration_ms=pipeline_result.duration_ms,
    )

    return ToolCheckResponse(
        passed=passed,
        blocking_severity=highest_blocking,
        conflicts=blocking_conflicts,
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /environments/{env_id}/tools
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ToolRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new MCP tool",
)
async def register_tool(
    env_id: uuid.UUID,
    body: ToolRegisterRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("developer")),
) -> ToolRegistrationResponse:
    """
    Register a new tool in the registry.
    Conflict analysis is dispatched asynchronously via Celery.
    """
    from mtgs.models.environment import Environment

    # Verify environment exists and belongs to user's org
    env_result = await db.execute(
        select(Environment).where(
            Environment.id == env_id,
            Environment.organization_id == current_user.org_id,
        )
    )
    env = env_result.scalar_one_or_none()
    if env is None:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Check for duplicate name in this env+server
    existing = await db.execute(
        select(Tool).where(
            Tool.environment_id == env_id,
            Tool.server_id == body.server_id,
            Tool.name == body.name,
            Tool.is_deleted == False,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tool '{body.name}' already exists on this server in this environment.",
        )

    # Check environment policy — require approval for high-severity environments
    policy = env.policy or {}
    needs_approval = policy.get("max_severity_to_block") == "CRITICAL"  # simplified

    tool_status = (
        ToolStatus.PENDING_APPROVAL if needs_approval else ToolStatus.ACTIVE
    )

    tool = Tool(
        environment_id=env_id,
        server_id=body.server_id,
        owner_team_id=body.owner_team_id,
        created_by_id=current_user.id,
        name=body.name,
        description=body.description,
        input_schema=body.input_schema,
        status=tool_status,
    )
    db.add(tool)
    await db.flush()  # get tool.id before committing

    # Create first version snapshot
    version = ToolVersion(
        tool_id=tool.id,
        changed_by_id=current_user.id,
        version=1,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        change_reason=body.change_reason or "Initial registration",
    )
    db.add(version)
    await db.commit()

    # Dispatch async conflict analysis
    from mtgs.workers.tasks import run_conflict_analysis_task

    background_tasks.add_task(
        run_conflict_analysis_task,
        tool_id=str(tool.id),
        env_id=str(env_id),
    )

    logger.info(
        "tool_registered",
        tool_id=str(tool.id),
        tool_name=tool.name,
        env_id=str(env_id),
        user_id=str(current_user.id),
    )

    return ToolRegistrationResponse(
        tool_id=tool.id,
        status=tool.status,
        message="Tool registered. Conflict analysis running asynchronously.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /environments/{env_id}/tools
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=PaginatedResponse[ToolResponse],
    summary="List tools in an environment",
)
async def list_tools(
    env_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    server_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    team_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("viewer")),
) -> PaginatedResponse[ToolResponse]:
    query = (
        select(Tool)
        .where(Tool.environment_id == env_id, Tool.is_deleted == False)
        .order_by(Tool.created_at.desc())
    )
    if server_id:
        query = query.where(Tool.server_id == server_id)
    if status_filter:
        query = query.where(Tool.status == status_filter)
    if team_id:
        query = query.where(Tool.owner_team_id == team_id)

    # Total count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    # Paginated results
    tools_result = await db.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    tools = tools_result.scalars().all()

    items = [await _tool_to_response(t, db) for t in tools]
    return PaginatedResponse.from_list(items, total=total, page=page, page_size=page_size)


# ─────────────────────────────────────────────────────────────────────────────
# GET /environments/{env_id}/tools/{tool_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{tool_id}",
    response_model=ToolResponse,
    summary="Get a tool by ID",
)
async def get_tool(
    env_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("viewer")),
) -> ToolResponse:
    tool = await _get_tool_or_404(tool_id, env_id, db)
    return await _tool_to_response(tool, db)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /environments/{env_id}/tools/{tool_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/{tool_id}",
    response_model=ToolResponse,
    summary="Update a tool definition",
)
async def update_tool(
    env_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: ToolUpdateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("developer")),
) -> ToolResponse:
    tool = await _get_tool_or_404(tool_id, env_id, db)

    # Track what changed for the version diff
    changed_fields: dict = {}
    if body.description and body.description != tool.description:
        changed_fields["description"] = {"before": tool.description, "after": body.description}
        tool.description = body.description
    if body.input_schema and body.input_schema != tool.input_schema:
        changed_fields["input_schema"] = {"before": tool.input_schema, "after": body.input_schema}
        tool.input_schema = body.input_schema
    if body.status and body.status != tool.status:
        changed_fields["status"] = {"before": tool.status, "after": body.status}
        tool.status = body.status

    if not changed_fields:
        return await _tool_to_response(tool, db)

    tool.version += 1
    # Invalidate embedding
    tool.embedding_fingerprint_hash = None

    version = ToolVersion(
        tool_id=tool.id,
        changed_by_id=current_user.id,
        version=tool.version,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        change_reason=body.change_reason,
        diff=changed_fields,
    )
    db.add(version)
    await db.commit()

    # Re-run conflict analysis
    from mtgs.workers.tasks import run_conflict_analysis_task

    background_tasks.add_task(
        run_conflict_analysis_task,
        tool_id=str(tool.id),
        env_id=str(env_id),
    )

    logger.info(
        "tool_updated",
        tool_id=str(tool.id),
        changed_fields=list(changed_fields.keys()),
        new_version=tool.version,
    )
    return await _tool_to_response(tool, db)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /environments/{env_id}/tools/{tool_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deprecate (soft-delete) a tool",
)
async def deprecate_tool(
    env_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("developer")),
) -> None:
    tool = await _get_tool_or_404(tool_id, env_id, db)
    tool.soft_delete()
    tool.status = ToolStatus.DEPRECATED
    await db.commit()
    logger.info("tool_deprecated", tool_id=str(tool_id), user_id=str(current_user.id))


# ─────────────────────────────────────────────────────────────────────────────
# GET /environments/{env_id}/tools/{tool_id}/history
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{tool_id}/history",
    response_model=list[ToolVersionResponse],
    summary="Get tool version history",
)
async def get_tool_history(
    env_id: uuid.UUID,
    tool_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_role("viewer")),
) -> list[ToolVersionResponse]:
    await _get_tool_or_404(tool_id, env_id, db)
    result = await db.execute(
        select(ToolVersion)
        .where(ToolVersion.tool_id == tool_id)
        .order_by(ToolVersion.version.desc())
    )
    versions = result.scalars().all()
    return [
        ToolVersionResponse(
            id=v.id,
            tool_id=v.tool_id,
            version=v.version,
            name=v.name,
            description=v.description,
            input_schema=v.input_schema,
            change_reason=v.change_reason,
            diff=v.diff,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in versions
    ]
