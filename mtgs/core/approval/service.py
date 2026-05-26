"""
Phase 3B — ApprovalService.

In-process store (dict-backed) suitable for unit tests and single-process dev.
In production this would be backed by a DB session injected via FastAPI's
dependency injection — swap _store for async DB queries without changing
the public interface.

Public exceptions
-----------------
ApprovalNotFoundError   — request id unknown
ApprovalDecisionError   — invalid decision value or state-transition violation
ApprovalPermissionError — caller's role cannot approve
"""

from __future__ import annotations

import logging
from typing import Any

from mtgs.core.approval.workflow import (
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalWorkflowError,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Custom exceptions
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalNotFoundError(KeyError):
    """Raised when the requested approval id does not exist."""


class ApprovalDecisionError(ValueError):
    """Raised for invalid decision values or illegal state transitions."""


class ApprovalPermissionError(PermissionError):
    """Raised when the caller's role is insufficient to approve/reject."""


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class ApprovalService:
    """
    Manages the lifecycle of ApprovalRequest objects.

    Parameters
    ----------
    policy:
        Configures which severities need approval and which roles can approve.
        Defaults to HIGH+ requiring approval, reviewer/admin roles can decide.
    """

    def __init__(self, policy: ApprovalPolicy | None = None) -> None:
        self._policy = policy or ApprovalPolicy()
        # In-process store: {request_id -> ApprovalRequest}
        self._store: dict[str, ApprovalRequest] = {}

    # ------------------------------------------------------------------ #
    #  CRUD                                                                #
    # ------------------------------------------------------------------ #

    async def create_request(
        self,
        conflict_id: str,
        tool_id: str,
        environment_id: str,
        requested_by: str,
        reason: str,
    ) -> ApprovalRequest:
        """Create and store a new PENDING approval request."""
        req = ApprovalRequest(
            conflict_id=conflict_id,
            tool_id=tool_id,
            environment_id=environment_id,
            requested_by=requested_by,
            reason=reason,
        )
        self._store[req.id] = req
        logger.info("ApprovalRequest created: id=%s conflict=%s", req.id, conflict_id)
        return req

    async def get_request(self, request_id: str) -> ApprovalRequest | None:
        """Return the request or None if not found."""
        return self._store.get(request_id)

    async def list_pending(
        self, environment_id: str | None = None
    ) -> list[ApprovalRequest]:
        """Return all PENDING requests, optionally filtered by environment."""
        from mtgs.core.approval.workflow import ApprovalStatus

        return [
            r for r in self._store.values()
            if r.status == ApprovalStatus.PENDING
            and (environment_id is None or r.environment_id == environment_id)
        ]

    async def list_all(
        self, environment_id: str | None = None
    ) -> list[ApprovalRequest]:
        """Return all requests regardless of status."""
        return [
            r for r in self._store.values()
            if environment_id is None or r.environment_id == environment_id
        ]

    # ------------------------------------------------------------------ #
    #  Decision                                                            #
    # ------------------------------------------------------------------ #

    async def decide(
        self,
        request_id: str,
        decision: str,
        reviewer_id: str,
        comment: str = "",
        reviewer_role: str = "reviewer",
    ) -> ApprovalRequest:
        """
        Approve or reject a pending approval request.

        Parameters
        ----------
        request_id:
            ID of the ApprovalRequest to decide on.
        decision:
            ``"approve"`` or ``"reject"``.
        reviewer_id:
            ID of the user making the decision.
        comment:
            Optional free-text comment.
        reviewer_role:
            Role of the reviewer — enforced against ApprovalPolicy.

        Raises
        ------
        ApprovalNotFoundError    if request_id is unknown.
        ApprovalPermissionError  if reviewer_role cannot approve.
        ApprovalDecisionError    if decision value is invalid or transition illegal.
        """
        req = self._store.get(request_id)
        if req is None:
            raise ApprovalNotFoundError(f"ApprovalRequest {request_id!r} not found")

        if not self._policy.can_approve(reviewer_role):
            raise ApprovalPermissionError(
                f"Role '{reviewer_role}' is not authorised to decide approval requests"
            )

        if decision not in ("approve", "reject"):
            raise ApprovalDecisionError(
                f"Invalid decision '{decision}': must be 'approve' or 'reject'"
            )

        try:
            if decision == "approve":
                req.approve(reviewer_id=reviewer_id, comment=comment)
            else:
                req.reject(reviewer_id=reviewer_id, comment=comment)
        except ApprovalWorkflowError as exc:
            raise ApprovalDecisionError(str(exc)) from exc

        logger.info(
            "ApprovalRequest decided: id=%s decision=%s reviewer=%s",
            request_id, decision, reviewer_id,
        )
        return req
