"""
Phase 3B — Approval Workflow.

Conflicts of CRITICAL or HIGH severity block the offending tool from being set
to ACTIVE until a human reviewer approves or rejects the registration.

Key objects
-----------
ApprovalStatus  — enum: PENDING | APPROVED | REJECTED | EXPIRED
ApprovalRequest — mutable but restricted state machine for a single approval request
ApprovalPolicy  — configurable rules controlling which severities need approval
                   and which roles can approve
ApprovalWorkflowError — raised on invalid state transitions
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

# Default TTL: pending requests older than 7 days auto-expire
_DEFAULT_TTL_DAYS = 7

# Severity order (ascending risk)
_SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

# Roles that can approve (minimum: reviewer)
_APPROVER_ROLES = frozenset({"reviewer", "admin"})


# ─────────────────────────────────────────────────────────────────────────────
# Enums & Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalWorkflowError(Exception):
    """Raised on invalid state transitions or policy violations."""


# ─────────────────────────────────────────────────────────────────────────────
# ApprovalRequest
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalRequest:
    """
    State machine for a single conflict-approval request.

    Lifecycle: PENDING → APPROVED | REJECTED
    If the request is not decided within `ttl_days`, it is considered EXPIRED.
    """

    def __init__(
        self,
        conflict_id: str,
        tool_id: str,
        environment_id: str,
        requested_by: str,
        reason: str,
        ttl_days: int = _DEFAULT_TTL_DAYS,
    ) -> None:
        self.id: str = str(uuid.uuid4())
        self.conflict_id = conflict_id
        self.tool_id = tool_id
        self.environment_id = environment_id
        self.requested_by = requested_by
        self.reason = reason
        self.ttl_days = ttl_days

        self.status: ApprovalStatus = ApprovalStatus.PENDING
        self.reviewer_id: str | None = None
        self.comment: str | None = None
        self.created_at: datetime = datetime.now(timezone.utc)
        self.decided_at: datetime | None = None

    # ------------------------------------------------------------------ #
    #  Properties                                                          #
    # ------------------------------------------------------------------ #

    @property
    def is_expired(self) -> bool:
        """True if the request has not been decided and the TTL has elapsed."""
        if self.status != ApprovalStatus.PENDING:
            return False
        age = datetime.now(timezone.utc) - self.created_at
        return age > timedelta(days=self.ttl_days)

    # ------------------------------------------------------------------ #
    #  State transitions                                                   #
    # ------------------------------------------------------------------ #

    def approve(self, reviewer_id: str, comment: str = "") -> None:
        """Transition PENDING → APPROVED."""
        self._assert_decidable()
        self.status = ApprovalStatus.APPROVED
        self.reviewer_id = reviewer_id
        self.comment = comment
        self.decided_at = datetime.now(timezone.utc)

    def reject(self, reviewer_id: str, comment: str = "") -> None:
        """Transition PENDING → REJECTED."""
        self._assert_decidable()
        self.status = ApprovalStatus.REJECTED
        self.reviewer_id = reviewer_id
        self.comment = comment
        self.decided_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------ #
    #  Internal guards                                                     #
    # ------------------------------------------------------------------ #

    def _assert_decidable(self) -> None:
        if self.status != ApprovalStatus.PENDING:
            raise ApprovalWorkflowError(
                f"Request {self.id} is already decided (status={self.status.value})"
            )
        if self.is_expired:
            raise ApprovalWorkflowError(
                f"Request {self.id} has expired and can no longer be decided"
            )

    def __repr__(self) -> str:
        return (
            f"ApprovalRequest(id={self.id!r}, status={self.status.value!r}, "
            f"conflict_id={self.conflict_id!r})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ApprovalPolicy
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalPolicy:
    """
    Configurable policy that determines:
    - Which conflict severities require human approval.
    - Which user roles are authorised to approve requests.

    Defaults:
    - Approval required for CRITICAL and HIGH (but not MEDIUM or LOW).
    - Only reviewer and admin roles can approve.
    """

    def __init__(
        self,
        min_severity_for_approval: str = "HIGH",
        approver_roles: frozenset[str] | None = None,
    ) -> None:
        self._min_severity = min_severity_for_approval
        self._approver_roles = approver_roles if approver_roles is not None else _APPROVER_ROLES

    def requires_approval(self, severity: str) -> bool:
        """Return True if the given severity meets the minimum threshold."""
        try:
            sev_idx = _SEVERITY_ORDER.index(severity)
            min_idx = _SEVERITY_ORDER.index(self._min_severity)
            return sev_idx >= min_idx
        except ValueError:
            return False  # unknown severity → no approval required

    def can_approve(self, role: str) -> bool:
        """Return True if the given role is authorised to approve requests."""
        return role in self._approver_roles
