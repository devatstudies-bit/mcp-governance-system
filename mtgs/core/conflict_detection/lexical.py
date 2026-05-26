"""
Stage 1 — Lexical Conflict Detection.

Detects:
  - EXACT_NAME   : identical tool names across different servers
  - SIMILAR_NAME : edit distance ≤ 2  OR  high Jaccard token overlap

This stage runs in < 100ms (pure CPU, no I/O).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfuzz.distance import Levenshtein

from mtgs.core.tool_def import ToolDef


class LexicalConflictType:
    EXACT_NAME = "EXACT_NAME"
    SIMILAR_NAME = "SIMILAR_NAME"


# Severity mapping
_SEVERITY_MAP = {
    LexicalConflictType.EXACT_NAME: "CRITICAL",
    LexicalConflictType.SIMILAR_NAME: "MEDIUM",
}

# Thresholds
_EDIT_DISTANCE_THRESHOLD = 2
_JACCARD_TOKEN_THRESHOLD = 0.5  # ≥50% token overlap


@dataclass
class LexicalConflict:
    conflict_type: str
    severity: str
    candidate_name: str
    conflicting_name: str
    conflict_score: float  # 0–100
    evidence: dict[str, Any] = field(default_factory=dict)


def _tokenize(name: str) -> set[str]:
    """Split snake_case / hyphen-case name into tokens."""
    return set(name.lower().replace("-", "_").split("_"))


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


class LexicalAnalyzer:
    """
    Runs Stage 1 lexical analysis against a candidate tool and a list of
    existing tools.

    Public API:
        analyzer.analyze(candidate, existing, same_server_ok=False) -> list[LexicalConflict]
    """

    def analyze(
        self,
        candidate: ToolDef,
        existing: list[ToolDef],
        same_server_ok: bool = False,
    ) -> list[LexicalConflict]:
        """
        Compare `candidate` against every tool in `existing`.

        Args:
            candidate:      The new tool being checked.
            existing:       All currently registered tools.
            same_server_ok: If True, identical names on the same server are not
                            flagged (registry-level uniqueness already enforced).

        Returns:
            List of LexicalConflict, sorted by severity (CRITICAL first).
        """
        conflicts: list[LexicalConflict] = []

        candidate_name_lower = candidate.name.lower()
        candidate_tokens = _tokenize(candidate.name)

        for tool in existing:
            existing_name_lower = tool.name.lower()

            # Optionally skip same-server comparisons
            if same_server_ok and candidate.server_name == tool.server_name:
                continue

            # ── EXACT NAME ────────────────────────────────────────────────────
            if candidate_name_lower == existing_name_lower:
                conflicts.append(
                    LexicalConflict(
                        conflict_type=LexicalConflictType.EXACT_NAME,
                        severity="CRITICAL",
                        candidate_name=candidate.name,
                        conflicting_name=tool.name,
                        conflict_score=100.0,
                        evidence={
                            "detection_method": "exact_match",
                            "candidate_server": candidate.server_name,
                            "conflicting_server": tool.server_name,
                        },
                    )
                )
                continue  # no need to check for SIMILAR if EXACT already found

            # ── SIMILAR NAME (edit distance) ──────────────────────────────────
            edit_dist = Levenshtein.distance(candidate_name_lower, existing_name_lower)
            if edit_dist <= _EDIT_DISTANCE_THRESHOLD:
                score = max(0.0, 70.0 - edit_dist * 10.0)
                conflicts.append(
                    LexicalConflict(
                        conflict_type=LexicalConflictType.SIMILAR_NAME,
                        severity="MEDIUM",
                        candidate_name=candidate.name,
                        conflicting_name=tool.name,
                        conflict_score=score,
                        evidence={
                            "detection_method": "edit_distance",
                            "edit_distance": edit_dist,
                            "threshold": _EDIT_DISTANCE_THRESHOLD,
                        },
                    )
                )
                continue  # already flagged; skip token overlap check

            # ── SIMILAR NAME (Jaccard token overlap) ──────────────────────────
            existing_tokens = _tokenize(tool.name)
            jaccard = _jaccard(candidate_tokens, existing_tokens)
            if jaccard >= _JACCARD_TOKEN_THRESHOLD:
                score = jaccard * 60.0
                conflicts.append(
                    LexicalConflict(
                        conflict_type=LexicalConflictType.SIMILAR_NAME,
                        severity="MEDIUM",
                        candidate_name=candidate.name,
                        conflicting_name=tool.name,
                        conflict_score=score,
                        evidence={
                            "detection_method": "token_jaccard",
                            "jaccard_similarity": round(jaccard, 4),
                            "candidate_tokens": list(candidate_tokens),
                            "conflicting_tokens": list(existing_tokens),
                            "threshold": _JACCARD_TOKEN_THRESHOLD,
                        },
                    )
                )

        # Sort: CRITICAL first, then by descending score
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        return sorted(
            conflicts,
            key=lambda c: (severity_order.get(c.severity, 9), -c.conflict_score),
        )
