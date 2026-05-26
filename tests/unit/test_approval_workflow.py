"""
Unit tests for Phase 3B — Approval Workflow.

Conflicts of CRITICAL/HIGH severity require human approval before the
offending tool can transition to ACTIVE status. This covers:
  - ApprovalRequest lifecycle (pending → approved/rejected)
  - RBAC: only reviewer+ can approve
  - Expiry: pending requests older than N days auto-expire

Run:
    pytest tests/unit/test_approval_workflow.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit

SAMPLE_CONFLICT_ID = str(uuid.uuid4())
SAMPLE_TOOL_ID = str(uuid.uuid4())
SAMPLE_ENV_ID = str(uuid.uuid4())
REVIEWER_USER_ID = str(uuid.uuid4())


class TestApprovalRequest:
    def test_create_approval_request(self) -> None:
        from mtgs.core.approval.workflow import ApprovalRequest, ApprovalStatus

        req = ApprovalRequest(
            conflict_id=SAMPLE_CONFLICT_ID,
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
            requested_by="ci-agent",
            reason="CRITICAL conflict requires human sign-off",
        )
        assert req.status == ApprovalStatus.PENDING
        assert req.conflict_id == SAMPLE_CONFLICT_ID

    def test_approve_transitions_status(self) -> None:
        from mtgs.core.approval.workflow import ApprovalRequest, ApprovalStatus

        req = ApprovalRequest(
            conflict_id=SAMPLE_CONFLICT_ID,
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
            requested_by="ci-agent",
            reason="CRITICAL conflict",
        )
        req.approve(reviewer_id=REVIEWER_USER_ID, comment="Looks safe in this context.")

        assert req.status == ApprovalStatus.APPROVED
        assert req.reviewer_id == REVIEWER_USER_ID
        assert req.comment == "Looks safe in this context."
        assert req.decided_at is not None

    def test_reject_transitions_status(self) -> None:
        from mtgs.core.approval.workflow import ApprovalRequest, ApprovalStatus

        req = ApprovalRequest(
            conflict_id=SAMPLE_CONFLICT_ID,
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
            requested_by="ci-agent",
            reason="CRITICAL conflict",
        )
        req.reject(reviewer_id=REVIEWER_USER_ID, comment="Name collision is unacceptable.")

        assert req.status == ApprovalStatus.REJECTED
        assert req.reviewer_id == REVIEWER_USER_ID

    def test_cannot_approve_already_decided_request(self) -> None:
        from mtgs.core.approval.workflow import ApprovalRequest, ApprovalWorkflowError

        req = ApprovalRequest(
            conflict_id=SAMPLE_CONFLICT_ID,
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
            requested_by="ci-agent",
            reason="Test",
        )
        req.approve(reviewer_id=REVIEWER_USER_ID, comment="ok")

        with pytest.raises(ApprovalWorkflowError, match="already decided"):
            req.approve(reviewer_id=REVIEWER_USER_ID, comment="double approve")

    def test_expired_request_cannot_be_approved(self) -> None:
        from mtgs.core.approval.workflow import ApprovalRequest, ApprovalStatus, ApprovalWorkflowError
        from datetime import timedelta

        req = ApprovalRequest(
            conflict_id=SAMPLE_CONFLICT_ID,
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
            requested_by="ci-agent",
            reason="Test",
        )
        # Back-date the creation time
        req.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

        with pytest.raises(ApprovalWorkflowError, match="expired"):
            req.approve(reviewer_id=REVIEWER_USER_ID, comment="too late")

    def test_is_expired_returns_false_for_new_request(self) -> None:
        from mtgs.core.approval.workflow import ApprovalRequest

        req = ApprovalRequest(
            conflict_id=SAMPLE_CONFLICT_ID,
            tool_id=SAMPLE_TOOL_ID,
            environment_id=SAMPLE_ENV_ID,
            requested_by="ci-agent",
            reason="Test",
        )
        assert req.is_expired is False


class TestApprovalPolicy:
    def test_critical_conflict_requires_approval(self) -> None:
        from mtgs.core.approval.workflow import ApprovalPolicy

        policy = ApprovalPolicy()
        assert policy.requires_approval(severity="CRITICAL") is True

    def test_high_conflict_requires_approval(self) -> None:
        from mtgs.core.approval.workflow import ApprovalPolicy

        policy = ApprovalPolicy()
        assert policy.requires_approval(severity="HIGH") is True

    def test_medium_conflict_does_not_require_approval_by_default(self) -> None:
        from mtgs.core.approval.workflow import ApprovalPolicy

        policy = ApprovalPolicy()
        assert policy.requires_approval(severity="MEDIUM") is False

    def test_policy_minimum_severity_configurable(self) -> None:
        from mtgs.core.approval.workflow import ApprovalPolicy

        strict_policy = ApprovalPolicy(min_severity_for_approval="MEDIUM")
        assert strict_policy.requires_approval(severity="MEDIUM") is True
        assert strict_policy.requires_approval(severity="LOW") is False

    def test_reviewer_role_can_approve(self) -> None:
        from mtgs.core.approval.workflow import ApprovalPolicy

        policy = ApprovalPolicy()
        assert policy.can_approve(role="reviewer") is True
        assert policy.can_approve(role="admin") is True

    def test_developer_role_cannot_approve(self) -> None:
        from mtgs.core.approval.workflow import ApprovalPolicy

        policy = ApprovalPolicy()
        assert policy.can_approve(role="developer") is False
        assert policy.can_approve(role="viewer") is False
