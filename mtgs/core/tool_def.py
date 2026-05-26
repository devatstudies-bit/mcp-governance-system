"""
ToolDef — lightweight data transfer object for tool definitions.

Used throughout the conflict detection engine without any DB or framework
dependency. This is the internal representation — NOT an ORM model.

The ORM Tool model lives in mtgs.models.tool; ToolDef is what the
pipeline operates on to keep engine logic pure and easily testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDef:
    """
    Minimal, immutable representation of an MCP tool definition.

    Attributes:
        name:         Tool name (snake_case).
        description:  Natural language description sent to LLMs.
        input_schema: JSON Schema dict for parameters.
        server_name:  Logical server name (used for server-scoped deduplication).
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = "unknown-server"

    @classmethod
    def from_orm(cls, tool: Any) -> "ToolDef":
        """Convert an ORM Tool instance to a ToolDef."""
        return cls(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema or {},
            server_name=str(getattr(tool, "server_id", "unknown")),
        )
