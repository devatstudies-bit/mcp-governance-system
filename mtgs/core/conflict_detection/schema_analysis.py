"""
Stage 2 — Schema (Parameter) Conflict Analysis.

Detects:
  - TYPE_COLLISION         : same parameter name, different JSON types
  - REQUIRED_FIELD_OVERLAP : high Jaccard overlap of required field names

Runs in < 200ms (pure CPU).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mtgs.core.tool_def import ToolDef


class SchemaConflictType:
    TYPE_COLLISION = "TYPE_COLLISION"
    REQUIRED_FIELD_OVERLAP = "REQUIRED_FIELD_OVERLAP"


# Threshold: if ≥70% of required fields overlap, flag it
_REQUIRED_OVERLAP_THRESHOLD = 0.70


@dataclass
class SchemaConflict:
    conflict_type: str
    severity: str
    candidate_name: str
    conflicting_name: str
    conflict_score: float
    param_name: str | None = None       # for TYPE_COLLISION
    candidate_type: str | None = None
    conflicting_type: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


def _get_properties(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return schema.get("properties", {})


def _get_required(schema: dict[str, Any]) -> set[str]:
    return set(schema.get("required", []))


def _jaccard_sets(a: set[str], b: set[str]) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class SchemaAnalyzer:
    """
    Runs Stage 2 schema analysis against a candidate tool and existing tools.

    Public API:
        analyzer.analyze(candidate, existing) -> list[SchemaConflict]
    """

    def analyze(
        self,
        candidate: ToolDef,
        existing: list[ToolDef],
    ) -> list[SchemaConflict]:
        """
        Compare candidate's input_schema against every tool in existing.

        Returns:
            Sorted list of SchemaConflict (most severe first).
        """
        conflicts: list[SchemaConflict] = []

        candidate_props = _get_properties(candidate.input_schema)
        candidate_required = _get_required(candidate.input_schema)

        for tool in existing:
            existing_props = _get_properties(tool.input_schema)
            existing_required = _get_required(tool.input_schema)

            # ── TYPE COLLISION ────────────────────────────────────────────────
            for param_name, candidate_param in candidate_props.items():
                if param_name in existing_props:
                    candidate_type = candidate_param.get("type", "any")
                    existing_type = existing_props[param_name].get("type", "any")
                    if candidate_type != existing_type:
                        conflicts.append(
                            SchemaConflict(
                                conflict_type=SchemaConflictType.TYPE_COLLISION,
                                severity="MEDIUM",
                                candidate_name=candidate.name,
                                conflicting_name=tool.name,
                                conflict_score=65.0,
                                param_name=param_name,
                                candidate_type=candidate_type,
                                conflicting_type=existing_type,
                                evidence={
                                    "param_name": param_name,
                                    "candidate_type": candidate_type,
                                    "conflicting_type": existing_type,
                                    "candidate_tool": candidate.name,
                                    "conflicting_tool": tool.name,
                                },
                            )
                        )

            # ── REQUIRED FIELD OVERLAP ────────────────────────────────────────
            if candidate_required and existing_required:
                jaccard = _jaccard_sets(candidate_required, existing_required)
                if jaccard >= _REQUIRED_OVERLAP_THRESHOLD:
                    score = jaccard * 70.0
                    conflicts.append(
                        SchemaConflict(
                            conflict_type=SchemaConflictType.REQUIRED_FIELD_OVERLAP,
                            severity="MEDIUM",
                            candidate_name=candidate.name,
                            conflicting_name=tool.name,
                            conflict_score=score,
                            evidence={
                                "jaccard_similarity": round(jaccard, 4),
                                "candidate_required": sorted(candidate_required),
                                "conflicting_required": sorted(existing_required),
                                "shared_fields": sorted(
                                    candidate_required & existing_required
                                ),
                                "threshold": _REQUIRED_OVERLAP_THRESHOLD,
                            },
                        )
                    )

        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        return sorted(
            conflicts,
            key=lambda c: (severity_order.get(c.severity, 9), -c.conflict_score),
        )
