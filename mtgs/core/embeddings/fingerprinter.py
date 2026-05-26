"""
ToolFingerprinter — builds a rich text fingerprint for embedding generation.

Design:
- Combines name + description + schema summary + server context
- Returns a stable text string (same inputs → same output, always)
- SHA256 hash of the fingerprint text is stored in the DB to detect stale embeddings

Note: This module is pure Python (no I/O) — fully unit-testable.
"""

from __future__ import annotations

import hashlib
from typing import Any

from mtgs.core.tool_def import ToolDef


class ToolFingerprinter:
    """
    Generates a semantic fingerprint for a tool definition.

    Combines name, description, and schema summary into a structured text
    string optimised for embedding models (not for human readability).
    """

    def build_fingerprint_text(self, tool: ToolDef) -> str:
        """
        Build the text that will be sent to the embedding model.

        Example output:
            Tool name: send_message
            Purpose: Send a message to a Slack channel or user via the Slack API.
            Parameters accepted: channel (string): Slack channel ID, text (string): Message text
            Server context: slack-mcp
        """
        param_summary = self._summarize_schema(tool.input_schema)
        parts = [
            f"Tool name: {tool.name}",
            f"Purpose: {tool.description}",
        ]
        if param_summary:
            parts.append(f"Parameters accepted: {param_summary}")
        parts.append(f"Server context: {tool.server_name}")
        return "\n".join(parts)

    def _summarize_schema(self, schema: dict[str, Any]) -> str:
        """
        Convert a JSON Schema 'properties' object into a compact summary string.

        Example:
            {"channel": {"type": "string", "description": "Slack channel ID"}}
            →  "channel (string): Slack channel ID"
        """
        props: dict[str, Any] = schema.get("properties", {})
        if not props:
            return ""
        summaries = []
        for name, prop in props.items():
            ptype = prop.get("type", "any")
            pdesc = prop.get("description", "")
            if pdesc:
                summaries.append(f"{name} ({ptype}): {pdesc}")
            else:
                summaries.append(f"{name} ({ptype})")
        return ", ".join(summaries)

    def compute_hash(self, tool: ToolDef) -> str:
        """
        Compute a SHA256 hash of the fingerprint text.

        Used to detect whether a stored embedding is stale after a tool update.
        Stored in tools.embedding_fingerprint_hash.

        Returns:
            64-character lowercase hex string.
        """
        text = self.build_fingerprint_text(tool)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
