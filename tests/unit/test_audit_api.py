"""
Unit tests for Phase 3C — Audit Log API layer.

Covers:
  - AuditLogService: filter by action, actor, resource, date range
  - Schemas: AuditEntryResponse, AuditExportRequest
  - SIEM export: JSON and CEF formats via the API
  - Pagination

No real DB — all in-process via AuditLogger.

Run:
    pytest tests/unit/test_audit_api.py -v
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit

ACTOR_A  = str(uuid.uuid4())
ACTOR_B  = str(uuid.uuid4())
RES_ID   = str(uuid.uuid4())
ENV_ID   = str(uuid.uuid4())


# ─── Schema tests ─────────────────────────────────────────────────────────────

class TestAuditSchemas:
    def test_audit_entry_response_schema(self) -> None:
        from mtgs.schemas.audit import AuditEntryResponse

        resp = AuditEntryResponse(
            entry_id=str(uuid.uuid4()),
            action="TOOL_REGISTERED",
            actor_id=ACTOR_A,
            resource_id=RES_ID,
            resource_type="tool",
            environment_id=ENV_ID,
            metadata={"tool_name": "send_message"},
            timestamp=datetime.now(timezone.utc),
        )
        assert resp.action == "TOOL_REGISTERED"
        assert resp.actor_id == ACTOR_A

    def test_audit_export_request_defaults(self) -> None:
        from mtgs.schemas.audit import AuditExportRequest

        req = AuditExportRequest()
        assert req.format == "json"
        assert req.action_filter is None
        assert req.actor_filter is None

    def test_audit_export_request_cef_format(self) -> None:
        from mtgs.schemas.audit import AuditExportRequest

        req = AuditExportRequest(format="cef")
        assert req.format == "cef"

    def test_audit_export_request_invalid_format_raises(self) -> None:
        from mtgs.schemas.audit import AuditExportRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AuditExportRequest(format="xml")

    def test_audit_list_response_schema(self) -> None:
        from mtgs.schemas.audit import AuditListResponse, AuditEntryResponse

        resp = AuditListResponse(
            items=[],
            total=0,
            page=1,
            page_size=50,
        )
        assert resp.total == 0
        assert resp.items == []


# ─── AuditLogService tests ────────────────────────────────────────────────────

class TestAuditLogService:
    @pytest.mark.asyncio
    async def test_record_and_list_returns_entry(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        await svc.record(
            action=AuditAction.TOOL_REGISTERED,
            actor_id=ACTOR_A,
            resource_id=RES_ID,
            resource_type="tool",
            environment_id=ENV_ID,
        )
        entries = await svc.list_entries()
        assert len(entries) == 1
        assert entries[0].actor_id == ACTOR_A

    @pytest.mark.asyncio
    async def test_filter_by_action(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        await svc.record(AuditAction.TOOL_REGISTERED,  ACTOR_A, RES_ID, "tool", ENV_ID)
        await svc.record(AuditAction.CONFLICT_DETECTED, ACTOR_A, RES_ID, "conflict", ENV_ID)

        filtered = await svc.list_entries(action_filter="TOOL_REGISTERED")
        assert len(filtered) == 1
        assert filtered[0].action.value == "TOOL_REGISTERED"

    @pytest.mark.asyncio
    async def test_filter_by_actor(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, RES_ID, "tool", ENV_ID)
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_B, RES_ID, "tool", ENV_ID)

        filtered = await svc.list_entries(actor_filter=ACTOR_A)
        assert all(e.actor_id == ACTOR_A for e in filtered)
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_filter_by_resource(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        res_a = str(uuid.uuid4())
        res_b = str(uuid.uuid4())
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, res_a, "tool", ENV_ID)
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, res_b, "tool", ENV_ID)

        filtered = await svc.list_entries(resource_filter=res_a)
        assert len(filtered) == 1
        assert filtered[0].resource_id == res_a

    @pytest.mark.asyncio
    async def test_filter_by_environment(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        env_a = str(uuid.uuid4())
        env_b = str(uuid.uuid4())
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, RES_ID, "tool", env_a)
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, RES_ID, "tool", env_b)

        filtered = await svc.list_entries(environment_filter=env_a)
        assert len(filtered) == 1
        assert filtered[0].environment_id == env_a

    @pytest.mark.asyncio
    async def test_pagination_page_size(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        for i in range(10):
            await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, str(i), "tool", ENV_ID)

        page1 = await svc.list_entries(page=1, page_size=4)
        page2 = await svc.list_entries(page=2, page_size=4)
        page3 = await svc.list_entries(page=3, page_size=4)

        assert len(page1) == 4
        assert len(page2) == 4
        assert len(page3) == 2

    @pytest.mark.asyncio
    async def test_export_json_returns_list_of_dicts(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        await svc.record(AuditAction.APPROVAL_APPROVED, ACTOR_A, RES_ID, "approval", ENV_ID)

        exported = await svc.export(fmt="json")
        assert isinstance(exported, list)
        assert len(exported) == 1
        assert isinstance(exported[0], dict)
        assert exported[0]["action"] == "APPROVAL_APPROVED"

    @pytest.mark.asyncio
    async def test_export_cef_returns_list_of_strings(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        await svc.record(AuditAction.CONFLICT_DETECTED, ACTOR_A, RES_ID, "conflict", ENV_ID)

        lines = await svc.export(fmt="cef")
        assert isinstance(lines, list)
        assert all(isinstance(ln, str) for ln in lines)
        assert all(ln.startswith("CEF:") for ln in lines)

    @pytest.mark.asyncio
    async def test_export_filtered_by_action(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, RES_ID, "tool", ENV_ID)
        await svc.record(AuditAction.TOOL_DELETED,    ACTOR_A, RES_ID, "tool", ENV_ID)

        exported = await svc.export(fmt="json", action_filter="TOOL_DELETED")
        assert len(exported) == 1
        assert exported[0]["action"] == "TOOL_DELETED"

    @pytest.mark.asyncio
    async def test_total_count_matches_unfiltered(self) -> None:
        from mtgs.core.audit.service import AuditLogService
        from mtgs.core.audit.logger import AuditAction

        svc = AuditLogService()
        for _ in range(5):
            await svc.record(AuditAction.TOOL_REGISTERED, ACTOR_A, RES_ID, "tool", ENV_ID)

        total = await svc.count()
        assert total == 5
