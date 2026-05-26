"""
Unit tests for Stage 2 — Schema (Parameter) Conflict Analysis.

Tests written BEFORE implementation (TDD).

Run:
    pytest tests/unit/test_schema_analysis.py -v
"""

from __future__ import annotations

import pytest

from mtgs.core.conflict_detection.schema_analysis import (
    SchemaAnalyzer,
    SchemaConflict,
    SchemaConflictType,
)
from tests.fixtures.tool_fixtures import (
    TOOL_GET_USER_A,
    TOOL_GET_USER_B,
    TOOL_CREATE_TASK,
    TOOL_QUERY_DATABASE,
    ToolDef,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def analyzer() -> SchemaAnalyzer:
    return SchemaAnalyzer()


# ─────────────────────────────────────────────────────────────────────────────
# TYPE COLLISION
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeCollision:
    def test_same_param_name_different_type_detected(self, analyzer: SchemaAnalyzer) -> None:
        """
        TOOL_GET_USER_A has user_id: integer
        TOOL_GET_USER_B has user_id: string
        → SCHEMA_COLLISION
        """
        conflicts = analyzer.analyze(
            candidate=TOOL_GET_USER_A,
            existing=[TOOL_GET_USER_B],
        )
        type_conflicts = [
            c for c in conflicts if c.conflict_type == SchemaConflictType.TYPE_COLLISION
        ]
        assert len(type_conflicts) >= 1

    def test_type_collision_reports_param_name(self, analyzer: SchemaAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_GET_USER_A,
            existing=[TOOL_GET_USER_B],
        )
        collision = next(
            c for c in conflicts if c.conflict_type == SchemaConflictType.TYPE_COLLISION
        )
        assert collision.param_name == "user_id"
        assert collision.candidate_type == "integer"
        assert collision.conflicting_type == "string"

    def test_type_collision_severity_is_medium(self, analyzer: SchemaAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_GET_USER_A,
            existing=[TOOL_GET_USER_B],
        )
        collision = next(
            (c for c in conflicts if c.conflict_type == SchemaConflictType.TYPE_COLLISION),
            None
        )
        if collision:
            assert collision.severity == "MEDIUM"

    def test_same_param_same_type_no_collision(self, analyzer: SchemaAnalyzer) -> None:
        """Two tools with user_id: string on both sides → no type collision."""
        tool_a = ToolDef(
            name="get_profile",
            description="Get user profile.",
            input_schema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        )
        tool_b = ToolDef(
            name="get_settings",
            description="Get user settings.",
            input_schema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}},
                "required": ["user_id"],
            },
        )
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        type_conflicts = [
            c for c in conflicts if c.conflict_type == SchemaConflictType.TYPE_COLLISION
        ]
        assert len(type_conflicts) == 0


# ─────────────────────────────────────────────────────────────────────────────
# REQUIRED FIELD OVERLAP
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFieldOverlap:
    def test_high_required_overlap_detected(self, analyzer: SchemaAnalyzer) -> None:
        """
        Two tools with 3 identical required fields out of 3 → high overlap → flagged.
        """
        tool_a = ToolDef(
            name="create_order",
            description="Create a new purchase order.",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "product_id": {"type": "string"},
                    "quantity": {"type": "integer"},
                },
                "required": ["customer_id", "product_id", "quantity"],
            },
        )
        tool_b = ToolDef(
            name="place_order",
            description="Place an order in the system.",
            input_schema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string"},
                    "product_id": {"type": "string"},
                    "quantity": {"type": "integer"},
                },
                "required": ["customer_id", "product_id", "quantity"],
            },
        )
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        overlap_conflicts = [
            c for c in conflicts if c.conflict_type == SchemaConflictType.REQUIRED_FIELD_OVERLAP
        ]
        assert len(overlap_conflicts) >= 1

    def test_low_required_overlap_not_flagged(self, analyzer: SchemaAnalyzer) -> None:
        """Tools with only 1 shared required field out of 4 → below threshold."""
        conflicts = analyzer.analyze(
            candidate=TOOL_CREATE_TASK,
            existing=[TOOL_QUERY_DATABASE],
        )
        overlap_conflicts = [
            c for c in conflicts if c.conflict_type == SchemaConflictType.REQUIRED_FIELD_OVERLAP
        ]
        assert len(overlap_conflicts) == 0


# ─────────────────────────────────────────────────────────────────────────────
# TOOL WITH NO PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────

class TestNoParameters:
    def test_no_params_tool_no_schema_conflict(self, analyzer: SchemaAnalyzer) -> None:
        """Tools with empty schema should not produce schema conflicts."""
        tool_a = ToolDef(
            name="ping",
            description="Health check ping.",
            input_schema={"type": "object", "properties": {}},
        )
        tool_b = ToolDef(
            name="health_check",
            description="System health check.",
            input_schema={"type": "object", "properties": {}},
        )
        conflicts = analyzer.analyze(candidate=tool_a, existing=[tool_b])
        assert conflicts == []

    def test_missing_properties_key_handled_gracefully(self, analyzer: SchemaAnalyzer) -> None:
        """Schemas missing 'properties' should not raise exceptions."""
        tool_a = ToolDef(
            name="run_job",
            description="Run a background job.",
            input_schema={"type": "object"},  # no 'properties'
        )
        # Should not raise
        conflicts = analyzer.analyze(candidate=tool_a, existing=[TOOL_QUERY_DATABASE])
        assert isinstance(conflicts, list)


# ─────────────────────────────────────────────────────────────────────────────
# RESULT STRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaConflictStructure:
    def test_conflict_has_required_fields(self, analyzer: SchemaAnalyzer) -> None:
        conflicts = analyzer.analyze(
            candidate=TOOL_GET_USER_A,
            existing=[TOOL_GET_USER_B],
        )
        assert len(conflicts) > 0
        c = conflicts[0]
        assert isinstance(c, SchemaConflict)
        assert c.conflict_type in SchemaConflictType.__dict__.values()
        assert c.severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
        assert isinstance(c.evidence, dict)

    def test_empty_existing_returns_no_conflicts(self, analyzer: SchemaAnalyzer) -> None:
        conflicts = analyzer.analyze(candidate=TOOL_GET_USER_A, existing=[])
        assert conflicts == []

    def test_analysis_is_idempotent(self, analyzer: SchemaAnalyzer) -> None:
        run1 = analyzer.analyze(candidate=TOOL_GET_USER_A, existing=[TOOL_GET_USER_B])
        run2 = analyzer.analyze(candidate=TOOL_GET_USER_A, existing=[TOOL_GET_USER_B])
        assert len(run1) == len(run2)
