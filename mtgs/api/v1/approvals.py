"""
Phase 3B — Approval Workflow API endpoints.

Routes
------
GET  /api/v1/approvals/              — list all requests (filterable by env / status)
GET  /api/v1/approvals/pending       — list only PENDING requests
GET  /api/v1/approvals/{id}          — get a single request
POST /api/v1/approvals/              — create a new approval request  [developer+]
PATCH /api/v1/approvals/{id}/decide  — approve or reject              [reviewer+]

RBAC:
- Any authenticated user can read approval requests (viewer+).
- developer+ can create requests.
- reviewer+ can approve/reject (enforced both at the HTTP layer and inside
  ApprovalService.decide()).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from mtgs.auth.dependencies import require_role
from mtgs.core.approval.service import (
    ApprovalDecisionError,
    ApprovalNotFoundError,
    ApprovalPermissionError,
    ApprovalService,
)
from mtgs.core.approval.workflow import ApprovalRequest
from mtgs.schemas.approval import (
    ApprovalListResponse,
    ApprovalResponse,
    CreateApprovalRequest,
    DecideApprovalRequest,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])

# Module-level singleton — in production inject via FastAPI dependency
_service = ApprovalService()


def get_approval_service() -> ApprovalService:
    return _service


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _to_response(req: ApprovalRequest) -> ApprovalResponse:
    return ApprovalResponse(
        id=req.id,
        conflict_id=req.conflict_id,
        tool_id=req.tool_id,
        environment_id=req.environment_id,
        requested_by=req.requested_by,
        reason=req.reason,
        status=req.status.value,
        reviewer_id=req.reviewer_id,
        comment=req.comment,
        created_at=req.created_at,
        decided_at=req.decided_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=ApprovalListResponse,
    summary="List all approval requests",
)
async def list_approvals(
    environment_id: str | None = Query(None),
    svc: ApprovalService = Depends(get_approval_service),
    _user=Depends(require_role("viewer")),
) -> ApprovalListResponse:
    all_reqs = await svc.list_all(environment_id=environment_id)
    pending = [r for r in all_reqs if r.status.value == "PENDING"]
    return ApprovalListResponse(
        items=[_to_response(r) for r in all_reqs],
        total=len(all_reqs),
        pending_count=len(pending),
    )


@router.get(
    "/pending",
    response_model=ApprovalListResponse,
    summary="List pending approval requests",
)
async def list_pending_approvals(
    environment_id: str | None = Query(None),
    svc: ApprovalService = Depends(get_approval_service),
    _user=Depends(require_role("viewer")),
) -> ApprovalListResponse:
    pending = await svc.list_pending(environment_id=environment_id)
    return ApprovalListResponse(
        items=[_to_response(r) for r in pending],
        total=len(pending),
        pending_count=len(pending),
    )


@router.get(
    "/{request_id}",
    response_model=ApprovalResponse,
    summary="Get a single approval request",
)
async def get_approval(
    request_id: str,
    svc: ApprovalService = Depends(get_approval_service),
    _user=Depends(require_role("viewer")),
) -> ApprovalResponse:
    req = await svc.get_request(request_id)
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request {request_id!r} not found",
        )
    return _to_response(req)


@router.post(
    "/",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an approval request for a conflict",
)
async def create_approval(
    body: CreateApprovalRequest,
    svc: ApprovalService = Depends(get_approval_service),
    user=Depends(require_role("developer")),
) -> ApprovalResponse:
    req = await svc.create_request(
        conflict_id=str(body.conflict_id),
        tool_id=str(body.tool_id),
        environment_id=str(body.environment_id),
        requested_by=getattr(user, "user_id", "api"),
        reason=body.reason,
    )
    return _to_response(req)


@router.patch(
    "/{request_id}/decide",
    response_model=ApprovalResponse,
    summary="Approve or reject an approval request",
)
async def decide_approval(
    request_id: str,
    body: DecideApprovalRequest,
    svc: ApprovalService = Depends(get_approval_service),
    user=Depends(require_role("reviewer")),
) -> ApprovalResponse:
    reviewer_id = getattr(user, "user_id", "api")
    reviewer_role = getattr(user, "role", "reviewer")
    try:
        req = await svc.decide(
            request_id=request_id,
            decision=body.decision,
            reviewer_id=reviewer_id,
            comment=body.comment,
            reviewer_role=reviewer_role,
        )
    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval request {request_id!r} not found",
        )
    except ApprovalPermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except ApprovalDecisionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return _to_response(req)
