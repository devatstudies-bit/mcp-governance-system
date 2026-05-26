"""
CI/CD webhook endpoint.

POST /webhooks/ci-check
  - Accepts a tool definition payload
  - Runs conflict check synchronously
  - Returns pass/fail with full report
  - Designed for use as a pipeline gate
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mtgs.database import get_db
from mtgs.models.environment import Environment
from mtgs.models.tool import Tool, ToolStatus
from mtgs.schemas.tool import ToolCheckRequest, ToolCheckResponse
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/ci-check",
    response_model=ToolCheckResponse,
    summary="CI/CD gate — conflict check for a candidate tool",
)
async def ci_check(
    body: ToolCheckRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_environment: str = Header(..., alias="X-Environment"),
    db: AsyncSession = Depends(get_db),
) -> ToolCheckResponse:
    """
    Stateless conflict check suitable for CI/CD pipelines.

    Authentication: X-API-Key header (service account key).
    Environment:    X-Environment header (dev | staging | prod).

    Returns HTTP 200 always; use `passed` field to determine gate outcome.
    The CI runner should exit 1 if `passed == False`.
    """
    from mtgs.auth.security import verify_api_key
    from mtgs.models.user import ApiKey
    from mtgs.core.conflict_detection.pipeline import ConflictDetectionPipeline
    from mtgs.core.tool_def import ToolDef

    # Authenticate via API key
    prefix = x_api_key[:8]
    key_result = await db.execute(
        select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.is_active == True)
    )
    key_records = key_result.scalars().all()
    authenticated = False
    org_id = None
    for record in key_records:
        if verify_api_key(x_api_key, record.key_hash):
            from mtgs.models.user import User
            user_result = await db.execute(
                select(User).where(User.id == record.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                authenticated = True
                org_id = user.organization_id
                break

    if not authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # Resolve environment
    env_result = await db.execute(
        select(Environment).where(
            Environment.name == x_environment,
            Environment.organization_id == org_id,
        )
    )
    env = env_result.scalar_one_or_none()
    if env is None:
        raise HTTPException(
            status_code=404,
            detail=f"Environment '{x_environment}' not found for your organization.",
        )

    # Load active tools
    tools_result = await db.execute(
        select(Tool).where(
            Tool.environment_id == env.id,
            Tool.status == ToolStatus.ACTIVE,
            Tool.is_deleted == False,
        )
    )
    existing_tools = tools_result.scalars().all()

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

    # Run pipeline
    pipeline = ConflictDetectionPipeline()
    result = pipeline.run_sync(candidate=candidate_def, existing=existing_defs)

    # Apply environment policy
    policy = env.policy or {}
    fail_severity = policy.get("max_severity_to_block", "HIGH")
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    fail_threshold = severity_order.get(fail_severity, 1)

    blocking, warnings = [], []
    for c in result.conflicts:
        entry = {
            "type": c.conflict_type,
            "severity": c.severity,
            "conflicting_tool": c.conflicting_name,
            "score": c.conflict_score,
            "evidence": c.evidence,
        }
        if severity_order.get(c.severity, 99) <= fail_threshold:
            blocking.append(entry)
        else:
            warnings.append(entry)

    passed = len(blocking) == 0

    logger.info(
        "ci_check_completed",
        tool_name=body.name,
        environment=x_environment,
        passed=passed,
        blocking_count=len(blocking),
        duration_ms=result.duration_ms,
    )

    return ToolCheckResponse(
        passed=passed,
        blocking_severity=blocking[0]["severity"] if blocking else None,
        conflicts=blocking,
        warnings=warnings,
    )
