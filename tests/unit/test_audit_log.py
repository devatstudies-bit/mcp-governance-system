"""
Unit tests for Phase 3C — Audit Log.

Every state-changing action (tool register/update/delete, conflict status change,
approval decision) must produce an immutable audit log entry. Tests cover:
  - AuditLogger.record() builds correct entries
  - Entries are never modified or deleted
  - SIEM export format (CEF / JSON)

Run:
    pytest tests/unit/test_audit_log.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit

ACTOR_ID = str(uuid.uuid4())
TOOL_ID = str(uuid.uuid4())
ENV_ID = str(uuid.uuid4())


class TestAuditEntry:
    def test_audit_entry_creation(self) -> None:
        from mtgs.core.audit.logger import AuditEntry, AuditAction

        entry = AuditEntry(
            action=AuditAction.TOOL_REGISTERED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="tool",
            environment_id=ENV_ID,
            metadata={"tool_name": "send_message", "server": "slack-mcp"},
        )
        assert entry.action == AuditAction.TOOL_REGISTERED
        assert entry.actor_id == ACTOR_ID
        assert entry.resource_id == TOOL_ID
        assert entry.resource_type == "tool"
        assert isinstance(entry.timestamp, datetime)

    def test_audit_entry_is_immutable(self) -> None:
        """Audit entries must not be modifiable after creation."""
        from mtgs.core.audit.logger import AuditEntry, AuditAction

        entry = AuditEntry(
            action=AuditAction.TOOL_REGISTERED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="tool",
            environment_id=ENV_ID,
        )
        with pytest.raises((AttributeError, TypeError)):
            entry.action = AuditAction.TOOL_DELETED  # type: ignore[misc]

    def test_audit_action_enum_values(self) -> None:
        from mtgs.core.audit.logger import AuditAction

        expected = {
            "TOOL_REGISTERED", "TOOL_UPDATED", "TOOL_DELETED",
            "CONFLICT_DETECTED", "CONFLICT_STATUS_CHANGED",
            "APPROVAL_REQUESTED", "APPROVAL_APPROVED", "APPROVAL_REJECTED",
            "ANALYSIS_RUN_STARTED", "ANALYSIS_RUN_COMPLETED",
        }
        actual = {a.value for a in AuditAction}
        assert expected.issubset(actual)

    def test_to_json_produces_valid_dict(self) -> None:
        from mtgs.core.audit.logger import AuditEntry, AuditAction

        entry = AuditEntry(
            action=AuditAction.CONFLICT_DETECTED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="conflict",
            environment_id=ENV_ID,
            metadata={"severity": "CRITICAL"},
        )
        d = entry.to_dict()
        assert d["action"] == "CONFLICT_DETECTED"
        assert d["actor_id"] == ACTOR_ID
        assert "timestamp" in d
        assert d["metadata"]["severity"] == "CRITICAL"

    def test_to_cef_produces_string(self) -> None:
        """CEF (Common Event Format) output for SIEM ingestion."""
        from mtgs.core.audit.logger import AuditEntry, AuditAction

        entry = AuditEntry(
            action=AuditAction.APPROVAL_APPROVED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="approval",
            environment_id=ENV_ID,
        )
        cef = entry.to_cef()
        assert isinstance(cef, str)
        assert cef.startswith("CEF:")
        assert "APPROVAL_APPROVED" in cef


class TestAuditLogger:
    @pytest.mark.asyncio
    async def test_record_returns_entry(self) -> None:
        from mtgs.core.audit.logger import AuditLogger, AuditAction

        logger = AuditLogger()
        entry = await logger.record(
            action=AuditAction.TOOL_REGISTERED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="tool",
            environment_id=ENV_ID,
        )
        from mtgs.core.audit.logger import AuditEntry
        assert isinstance(entry, AuditEntry)

    @pytest.mark.asyncio
    async def test_record_includes_metadata(self) -> None:
        from mtgs.core.audit.logger import AuditLogger, AuditAction

        logger = AuditLogger()
        entry = await logger.record(
            action=AuditAction.TOOL_UPDATED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="tool",
            environment_id=ENV_ID,
            metadata={"version": 2, "changed_field": "description"},
        )
        assert entry.metadata["version"] == 2
        assert entry.metadata["changed_field"] == "description"

    @pytest.mark.asyncio
    async def test_export_json_returns_list(self) -> None:
        from mtgs.core.audit.logger import AuditLogger, AuditAction

        logger = AuditLogger()
        await logger.record(
            action=AuditAction.ANALYSIS_RUN_STARTED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="analysis_run",
            environment_id=ENV_ID,
        )
        exported = logger.export_json()
        assert isinstance(exported, list)
        assert len(exported) >= 1
        assert all(isinstance(e, dict) for e in exported)

    @pytest.mark.asyncio
    async def test_export_cef_returns_lines(self) -> None:
        from mtgs.core.audit.logger import AuditLogger, AuditAction

        logger = AuditLogger()
        await logger.record(
            action=AuditAction.CONFLICT_DETECTED,
            actor_id=ACTOR_ID,
            resource_id=TOOL_ID,
            resource_type="conflict",
            environment_id=ENV_ID,
        )
        lines = logger.export_cef()
        assert isinstance(lines, list)
        assert all(line.startswith("CEF:") for line in lines)
