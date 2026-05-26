"""
Phase 3C — Audit Log.

Every state-changing action in MTGS produces an immutable AuditEntry.
Entries are append-only and support export to:
  - JSON (structured log, for log aggregators like Splunk / Elastic)
  - CEF (Common Event Format, for SIEM platforms like Microsoft Sentinel / QRadar)

AuditLogger is a lightweight in-process logger. In production it writes to the
database via the AnalysisRun ORM layer; in tests it uses an in-memory list.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class AuditAction(str, Enum):
    TOOL_REGISTERED = "TOOL_REGISTERED"
    TOOL_UPDATED = "TOOL_UPDATED"
    TOOL_DELETED = "TOOL_DELETED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    CONFLICT_STATUS_CHANGED = "CONFLICT_STATUS_CHANGED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    ANALYSIS_RUN_STARTED = "ANALYSIS_RUN_STARTED"
    ANALYSIS_RUN_COMPLETED = "ANALYSIS_RUN_COMPLETED"
    USER_LOGIN = "USER_LOGIN"
    API_KEY_CREATED = "API_KEY_CREATED"
    API_KEY_REVOKED = "API_KEY_REVOKED"


# ─────────────────────────────────────────────────────────────────────────────
# CEF constants
# ─────────────────────────────────────────────────────────────────────────────

_CEF_VERSION = "0"
_CEF_DEVICE_VENDOR = "MTGS"
_CEF_DEVICE_PRODUCT = "MCPToolGovernance"
_CEF_DEVICE_VERSION = "1.0"

_ACTION_SEVERITY: dict[str, int] = {
    AuditAction.TOOL_REGISTERED: 3,
    AuditAction.TOOL_UPDATED: 3,
    AuditAction.TOOL_DELETED: 7,
    AuditAction.CONFLICT_DETECTED: 8,
    AuditAction.CONFLICT_STATUS_CHANGED: 5,
    AuditAction.APPROVAL_REQUESTED: 6,
    AuditAction.APPROVAL_APPROVED: 4,
    AuditAction.APPROVAL_REJECTED: 6,
    AuditAction.ANALYSIS_RUN_STARTED: 2,
    AuditAction.ANALYSIS_RUN_COMPLETED: 2,
    AuditAction.USER_LOGIN: 2,
    AuditAction.API_KEY_CREATED: 4,
    AuditAction.API_KEY_REVOKED: 6,
}


# ─────────────────────────────────────────────────────────────────────────────
# AuditEntry — frozen/immutable dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuditEntry:
    """
    An immutable record of a single governance action.

    Marked ``frozen=True`` so that attempts to mutate any field
    raise ``FrozenInstanceError`` (a subclass of ``AttributeError``).
    """

    action: AuditAction
    actor_id: str
    resource_id: str
    resource_type: str
    environment_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ #
    #  Serialisation                                                       #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict representation."""
        return {
            "entry_id": self.entry_id,
            "action": self.action.value if isinstance(self.action, AuditAction) else str(self.action),
            "actor_id": self.actor_id,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "environment_id": self.environment_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_cef(self) -> str:
        """
        Serialise to Common Event Format (CEF) for SIEM ingestion.

        Format:
        CEF:<version>|<vendor>|<product>|<version>|<sig_id>|<name>|<severity>|<extension>
        """
        action_str = self.action.value if isinstance(self.action, AuditAction) else str(self.action)
        severity = _ACTION_SEVERITY.get(self.action, 5)

        # Extension key=value pairs (CEF spec: escape = and | with backslash)
        def _esc(v: str) -> str:
            return v.replace("\\", "\\\\").replace("=", "\\=").replace("|", "\\|")

        extension_parts = [
            f"rt={self.timestamp.strftime('%b %d %Y %H:%M:%S')}",
            f"suser={_esc(self.actor_id)}",
            f"src={_esc(self.resource_id)}",
            f"resourceType={_esc(self.resource_type)}",
            f"envId={_esc(self.environment_id)}",
        ]
        if self.metadata:
            try:
                extension_parts.append(f"cs1={_esc(json.dumps(self.metadata))}")
                extension_parts.append("cs1Label=metadata")
            except (TypeError, ValueError):
                pass

        extension = " ".join(extension_parts)
        return (
            f"CEF:{_CEF_VERSION}|{_CEF_DEVICE_VENDOR}|{_CEF_DEVICE_PRODUCT}|"
            f"{_CEF_DEVICE_VERSION}|{action_str}|{action_str}|{severity}|{extension}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AuditLogger
# ─────────────────────────────────────────────────────────────────────────────


class AuditLogger:
    """
    In-process audit logger with JSON and CEF export.

    In production, override ``_persist()`` to write entries to the DB or
    a log-aggregation pipeline.  The in-memory store is suitable for testing.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    async def record(
        self,
        action: AuditAction,
        actor_id: str,
        resource_id: str,
        resource_type: str,
        environment_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """Create and store an immutable audit entry. Returns the entry."""
        entry = AuditEntry(
            action=action,
            actor_id=actor_id,
            resource_id=resource_id,
            resource_type=resource_type,
            environment_id=environment_id,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        await self._persist(entry)
        return entry

    def export_json(self) -> list[dict[str, Any]]:
        """Return all entries as a list of JSON-serialisable dicts."""
        return [e.to_dict() for e in self._entries]

    def export_cef(self) -> list[str]:
        """Return all entries as CEF-formatted strings (one per line)."""
        return [e.to_cef() for e in self._entries]

    async def _persist(self, entry: AuditEntry) -> None:
        """
        Hook for production persistence (DB / event bus / log aggregator).
        Default no-op — override in a subclass or inject a storage backend.
        """
