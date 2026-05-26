"""
Unit tests for ToolFingerprinter — the embedding text builder.

These are pure logic tests (no Azure API calls).

Run:
    pytest tests/unit/test_fingerprinter.py -v
"""

from __future__ import annotations

import hashlib

import pytest

from mtgs.core.embeddings.fingerprinter import ToolFingerprinter
from tests.fixtures.tool_fixtures import (
    TOOL_CREATE_TASK,
    TOOL_QUERY_DATABASE,
    TOOL_SEND_MESSAGE_SLACK,
    ToolDef,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def fingerprinter() -> ToolFingerprinter:
    return ToolFingerprinter()


class TestFingerprintTextGeneration:
    def test_fingerprint_includes_name(self, fingerprinter: ToolFingerprinter) -> None:
        text = fingerprinter.build_fingerprint_text(TOOL_SEND_MESSAGE_SLACK)
        assert TOOL_SEND_MESSAGE_SLACK.name in text

    def test_fingerprint_includes_description(self, fingerprinter: ToolFingerprinter) -> None:
        text = fingerprinter.build_fingerprint_text(TOOL_SEND_MESSAGE_SLACK)
        assert TOOL_SEND_MESSAGE_SLACK.description in text

    def test_fingerprint_includes_server_name(self, fingerprinter: ToolFingerprinter) -> None:
        text = fingerprinter.build_fingerprint_text(TOOL_SEND_MESSAGE_SLACK)
        assert TOOL_SEND_MESSAGE_SLACK.server_name in text

    def test_fingerprint_includes_param_names(self, fingerprinter: ToolFingerprinter) -> None:
        text = fingerprinter.build_fingerprint_text(TOOL_SEND_MESSAGE_SLACK)
        assert "channel" in text
        assert "text" in text

    def test_fingerprint_includes_param_types(self, fingerprinter: ToolFingerprinter) -> None:
        text = fingerprinter.build_fingerprint_text(TOOL_QUERY_DATABASE)
        assert "string" in text  # sql parameter type

    def test_two_different_tools_produce_different_fingerprints(
        self, fingerprinter: ToolFingerprinter
    ) -> None:
        text_a = fingerprinter.build_fingerprint_text(TOOL_SEND_MESSAGE_SLACK)
        text_b = fingerprinter.build_fingerprint_text(TOOL_QUERY_DATABASE)
        assert text_a != text_b

    def test_same_tool_produces_same_fingerprint(self, fingerprinter: ToolFingerprinter) -> None:
        text1 = fingerprinter.build_fingerprint_text(TOOL_CREATE_TASK)
        text2 = fingerprinter.build_fingerprint_text(TOOL_CREATE_TASK)
        assert text1 == text2


class TestFingerprintHash:
    def test_hash_is_hex_string(self, fingerprinter: ToolFingerprinter) -> None:
        h = fingerprinter.compute_hash(TOOL_CREATE_TASK)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA256 hex digest

    def test_hash_is_deterministic(self, fingerprinter: ToolFingerprinter) -> None:
        h1 = fingerprinter.compute_hash(TOOL_CREATE_TASK)
        h2 = fingerprinter.compute_hash(TOOL_CREATE_TASK)
        assert h1 == h2

    def test_different_tools_different_hashes(self, fingerprinter: ToolFingerprinter) -> None:
        h1 = fingerprinter.compute_hash(TOOL_CREATE_TASK)
        h2 = fingerprinter.compute_hash(TOOL_QUERY_DATABASE)
        assert h1 != h2

    def test_description_change_changes_hash(self, fingerprinter: ToolFingerprinter) -> None:
        tool_v1 = ToolDef(name="my_tool", description="Version 1 description.")
        tool_v2 = ToolDef(name="my_tool", description="Version 2 description — updated.")
        assert fingerprinter.compute_hash(tool_v1) != fingerprinter.compute_hash(tool_v2)

    def test_schema_change_changes_hash(self, fingerprinter: ToolFingerprinter) -> None:
        tool_v1 = ToolDef(
            name="my_tool",
            description="A tool.",
            input_schema={"type": "object", "properties": {"a": {"type": "string"}}},
        )
        tool_v2 = ToolDef(
            name="my_tool",
            description="A tool.",
            input_schema={"type": "object", "properties": {"b": {"type": "integer"}}},
        )
        assert fingerprinter.compute_hash(tool_v1) != fingerprinter.compute_hash(tool_v2)


class TestSchemaParameterSummary:
    def test_empty_schema_produces_empty_summary(
        self, fingerprinter: ToolFingerprinter
    ) -> None:
        tool = ToolDef(name="no_params", description="No params.", input_schema={})
        summary = fingerprinter._summarize_schema(tool.input_schema)
        assert isinstance(summary, str)

    def test_schema_with_description_includes_it(
        self, fingerprinter: ToolFingerprinter
    ) -> None:
        schema = {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "The unique order identifier"}
            },
        }
        summary = fingerprinter._summarize_schema(schema)
        assert "order_id" in summary
        assert "string" in summary
