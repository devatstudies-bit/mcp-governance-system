"""
Unit tests for Phase 3B — Approval Workflow API layer.

Covers schemas, the ApprovalService, and RBAC enforcement.
No real DB or HTTP calls — all dependencies mocked.

Run:
    pytest tests/unit/test_approval_api.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.unit

CONFLICT_ID = str(uuid.uuid4())
TOOL_ID     = str(uuid.uuid4())
ENV_ID      = str(uuid.uuid4())
REVIEWER_ID = str(uuid.uuid4())
DEV_ID      = str(uuid.uuid4())


# ─── Schema tests ─────────────────────────────────────────────────────────────

class TestApprovalSchemas:
    def test_create_approval_request_schema(self) -> None:
        from mtgs.schemas.approval import CreateApprovalRequest

        req = CreateApprovalRequest(
            conflict_id=CONFLICT_ID,
            tool_id=TOOL_ID,
            environment_id=ENV_ID,
            reason="CRITICAL conflict requires sign-off",
        )
        assert str(req.conflict_id) == CONFLICT_ID
        assert req.reason == "CRITICAL conflict requires sign-off"

    def test_decide_approval_schema_approve(self) -> None:
        from mtgs.schemas.approval import DecideApprovalRequest

        req = DecideApprovalRequest(decision="approve", comment="Looks safe.")
        assert req.decision == "approve"
        assert req.comment == "Looks safe."

    def test_decide_approval_schema_reject(self) -> None:
        from mtgs.schemas.approval import DecideApprovalRequest

        req = DecideApprovalRequest(decision="reject", comment="Name clash is unacceptable.")
        assert req.decision == "reject"

    def test_decide_approval_invalid_decision_raises(self) -> None:
        from mtgs.schemas.approval import DecideApprovalRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DecideApprovalRequest(decision="maybe")

    def test_approval_response_schema(self) -> None:
        from mtgs.schemas.approval import ApprovalResponse

        resp = ApprovalResponse(
            id=str(uuid.uuid4()),
            conflict_id=CONFLICT_ID,
            tool_id=TOOL_ID,
            environment_id=ENV_ID,
            requested_by="ci-agent",
            reason="CRITICAL",
            status="PENDING",
            reviewer_id=None,
            comment=None,
            created_at=datetime.now(timezone.utc),
            decided_at=None,
        )
        assert resp.status == "PENDING"
        assert resp.reviewer_id is None


# ─── ApprovalService tests ────────────────────────────────────────────────────

class TestApprovalService:
    @pytest.mark.asyncio
    async def test_create_request_returns_approval(self) -> None:
        from mtgs.core.approval.service import ApprovalService
        from mtgs.core.approval.workflow import ApprovalRequest

        svc = ApprovalService()
        req = await svc.create_request(
            conflict_id=CONFLICT_ID,
            tool_id=TOOL_ID,
            environment_id=ENV_ID,
            requested_by="ci-agent",
            reason="CRITICAL conflict",
        )
        assert isinstance(req, ApprovalRequest)
        assert req.status.value == "PENDING"

    @pytest.mark.asyncio
    async def test_get_request_returns_none_for_unknown_id(self) -> None:
        from mtgs.core.approval.service import ApprovalService

        svc = ApprovalService()
        result = await svc.get_request(str(uuid.uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_approve_request_transitions_to_approved(self) -> None:
        from mtgs.core.approval.service import ApprovalService

        svc = ApprovalService()
        req = await svc.create_request(
            conflict_id=CONFLICT_ID,
            tool_id=TOOL_ID,
            environment_id=ENV_ID,
            requested_by="ci-agent",
            reason="test",
        )
        updated = await svc.decide(
            request_id=req.id,
            decision="approve",
            reviewer_id=REVIEWER_ID,
            comment="OK",
        )
        assert updated.status.value == "APPROVED"
        assert updated.reviewer_id == REVIEWER_ID

    @pytest.mark.asyncio
    async def test_reject_request_transitions_to_rejected(self) -> None:
        from mtgs.core.approval.service import ApprovalService

        svc = ApprovalService()
        req = await svc.create_request(
            conflict_id=CONFLICT_ID,
            tool_id=TOOL_ID,
            environment_id=ENV_ID,
            requested_by="ci-agent",
            reason="test",
        )
        updated = await svc.decide(
            request_id=req.id,
            decision="reject",
            reviewer_id=REVIEWER_ID,
            comment="No.",
        )
        assert updated.status.value == "REJECTED"

    @pytest.mark.asyncio
    async def test_decide_unknown_request_raises(self) -> None:
        from mtgs.core.approval.service import ApprovalService, ApprovalNotFoundError

        svc = ApprovalService()
        with pytest.raises(ApprovalNotFoundError):
            await svc.decide(
                request_id=str(uuid.uuid4()),
                decision="approve",
                reviewer_id=REVIEWER_ID,
            )

    @pytest.mark.asyncio
    async def test_decide_invalid_decision_raises(self) -> None:
        from mtgs.core.approval.service import ApprovalService, ApprovalDecisionError

        svc = ApprovalService()
        req = await svc.create_request(
            conflict_id=CONFLICT_ID,
            tool_id=TOOL_ID,
            environment_id=ENV_ID,
            requested_by="ci-agent",
            reason="test",
        )
        with pytest.raises(ApprovalDecisionError):
            await svc.decide(
                request_id=req.id,
                decision="maybe",
                reviewer_id=REVIEWER_ID,
            )

    @pytest.mark.asyncio
    async def test_list_pending_returns_only_pending(self) -> None:
        from mtgs.core.approval.service import ApprovalService

        svc = ApprovalService()
        req1 = await svc.create_request(
            conflict_id=CONFLICT_ID, tool_id=TOOL_ID,
            environment_id=ENV_ID, requested_by="ci", reason="r1",
        )
        req2 = await svc.create_request(
            conflict_id=str(uuid.uuid4()), tool_id=TOOL_ID,
            environment_id=ENV_ID, requested_by="ci", reason="r2",
        )
        # Approve req1
        await svc.decide(request_id=req1.id, decision="approve", reviewer_id=REVIEWER_ID)

        pending = await svc.list_pending(environment_id=ENV_ID)
        ids = [r.id for r in pending]
        assert req1.id not in ids
        assert req2.id in ids

    @pytest.mark.asyncio
    async def test_policy_check_requires_reviewer_role(self) -> None:
        from mtgs.core.approval.service import ApprovalService, ApprovalPermissionError

        svc = ApprovalService()
        req = await svc.create_request(
            conflict_id=CONFLICT_ID, tool_id=TOOL_ID,
            environment_id=ENV_ID, requested_by="ci", reason="test",
        )
        with pytest.raises(ApprovalPermissionError):
            await svc.decide(
                request_id=req.id,
                decision="approve",
                reviewer_id=DEV_ID,
                reviewer_role="developer",  # insufficient role
            )

    @pytest.mark.asyncio
    async def test_policy_check_passes_for_reviewer_role(self) -> None:
        from mtgs.core.approval.service import ApprovalService

        svc = ApprovalService()
        req = await svc.create_request(
            conflict_id=CONFLICT_ID, tool_id=TOOL_ID,
            environment_id=ENV_ID, requested_by="ci", reason="test",
        )
        # Should not raise
        updated = await svc.decide(
            request_id=req.id,
            decision="approve",
            reviewer_id=REVIEWER_ID,
            reviewer_role="reviewer",
        )
        assert updated.status.value == "APPROVED"
