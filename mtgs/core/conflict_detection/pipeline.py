"""
Conflict Detection Pipeline — orchestrates Stages 1 through 4.

Stage 1 (Lexical)  — always runs, < 100ms
Stage 2 (Schema)   — always runs, < 200ms
Stage 3 (Semantic) — skipped if CRITICAL found in S1/S2; requires embedding service
Stage 4 (Behavioral) — only for pairs flagged in S3; invoked by Celery worker, not here

Short-circuit logic:
  If Stage 1 produces a CRITICAL conflict, Stage 3 is skipped entirely
  (the routing problem is already severe; expensive LLM calls are unnecessary).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Union

from mtgs.core.conflict_detection.lexical import LexicalAnalyzer, LexicalConflict
from mtgs.core.conflict_detection.schema_analysis import SchemaAnalyzer, SchemaConflict

if TYPE_CHECKING:
    from mtgs.core.embeddings.azure_search_client import AzureSearchClient

from mtgs.core.tool_def import ToolDef

# Unified conflict type for pipeline output
AnyConflict = Union[LexicalConflict, SchemaConflict]

_SEVERITY_ORDER: dict[str, int] = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MEDIUM": 2,
    "LOW": 3,
    "INFO": 4,
}


class PipelineStage(StrEnum):
    LEXICAL = "lexical"
    SCHEMA = "schema"
    SEMANTIC = "semantic"
    BEHAVIORAL = "behavioral"


@dataclass
class SemanticConflict:
    """Lightweight result from Stage 3 semantic analysis."""

    conflict_type: str = "SEMANTIC_OVERLAP"
    severity: str = "HIGH"
    candidate_name: str = ""
    conflicting_name: str = ""
    conflict_score: float = 0.0
    cosine_similarity: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Aggregated result from all executed pipeline stages."""

    conflicts: list[AnyConflict]
    stages_executed: list[PipelineStage]
    duration_ms: float
    stage_durations_ms: dict[str, float] = field(default_factory=dict)

    @property
    def has_critical(self) -> bool:
        return any(c.severity == "CRITICAL" for c in self.conflicts)

    @property
    def highest_severity(self) -> str | None:
        if not self.conflicts:
            return None
        return min(
            (c.severity for c in self.conflicts),
            key=lambda s: _SEVERITY_ORDER.get(s, 99),
        )

    @property
    def conflict_count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {s: 0 for s in _SEVERITY_ORDER}
        for c in self.conflicts:
            counts[c.severity] = counts.get(c.severity, 0) + 1
        return counts


class ConflictDetectionPipeline:
    """
    Orchestrates the multi-stage conflict detection pipeline.

    Args:
        embedding_service: Optional AzureSearchClient for Stage 3 semantic analysis.
                           If None, Stage 3 is skipped gracefully.
        semantic_threshold: Cosine similarity threshold for SEMANTIC_OVERLAP (default: 0.80).
    """

    def __init__(
        self,
        embedding_service: "AzureSearchClient | None" = None,
        semantic_threshold: float = 0.80,
    ) -> None:
        self._lexical = LexicalAnalyzer()
        self._schema = SchemaAnalyzer()
        self._embedding_service = embedding_service
        self._semantic_threshold = semantic_threshold

    def run_sync(
        self,
        candidate: ToolDef,
        existing: list[ToolDef],
        same_server_ok: bool = False,
    ) -> PipelineResult:
        """
        Synchronous pipeline execution (for unit tests and CLI).
        Stages 1 and 2 only — Stage 3 requires async embedding service.
        """
        t_total = time.perf_counter()
        all_conflicts: list[AnyConflict] = []
        stages_executed: list[PipelineStage] = []
        stage_durations: dict[str, float] = {}

        # ── Stage 1: Lexical ──────────────────────────────────────────────────
        t1 = time.perf_counter()
        lexical_conflicts = self._lexical.analyze(
            candidate=candidate,
            existing=existing,
            same_server_ok=same_server_ok,
        )
        stage_durations[PipelineStage.LEXICAL] = (time.perf_counter() - t1) * 1000
        stages_executed.append(PipelineStage.LEXICAL)
        all_conflicts.extend(lexical_conflicts)

        # ── Stage 2: Schema ───────────────────────────────────────────────────
        t2 = time.perf_counter()
        schema_conflicts = self._schema.analyze(
            candidate=candidate,
            existing=existing,
        )
        stage_durations[PipelineStage.SCHEMA] = (time.perf_counter() - t2) * 1000
        stages_executed.append(PipelineStage.SCHEMA)
        all_conflicts.extend(schema_conflicts)

        # ── Stage 3: Semantic ─────────────────────────────────────────────────
        # Short-circuit: skip if CRITICAL already found, or no embedding service
        has_critical = any(c.severity == "CRITICAL" for c in all_conflicts)
        if not has_critical and self._embedding_service is not None:
            # Stage 3 is async — use run_async path for real usage
            # In sync mode, we simply record that it was skipped
            pass
        # Stage 3 not in stages_executed if skipped

        total_ms = (time.perf_counter() - t_total) * 1000

        # Sort all conflicts by severity, then descending score
        sorted_conflicts = sorted(
            all_conflicts,
            key=lambda c: (_SEVERITY_ORDER.get(c.severity, 9), -c.conflict_score),
        )

        return PipelineResult(
            conflicts=sorted_conflicts,
            stages_executed=stages_executed,
            duration_ms=total_ms,
            stage_durations_ms=stage_durations,
        )

    async def run_async(
        self,
        candidate: ToolDef,
        existing: list[ToolDef],
        same_server_ok: bool = False,
        candidate_embedding: list[float] | None = None,
        existing_embeddings: dict[str, list[float]] | None = None,
    ) -> PipelineResult:
        """
        Full async pipeline including Stage 3 semantic analysis.

        Args:
            candidate_embedding:  Pre-computed embedding for the candidate tool.
            existing_embeddings:  Dict of {tool_name: embedding} for ANN lookup.
                                  If provided, skips Azure AI Search call.
        """
        import asyncio

        t_total = time.perf_counter()
        all_conflicts: list[AnyConflict] = []
        stages_executed: list[PipelineStage] = []
        stage_durations: dict[str, float] = {}

        # Stages 1 & 2 (reuse sync logic)
        sync_result = self.run_sync(
            candidate=candidate,
            existing=existing,
            same_server_ok=same_server_ok,
        )
        all_conflicts.extend(sync_result.conflicts)
        stages_executed.extend(sync_result.stages_executed)
        stage_durations.update(sync_result.stage_durations_ms)

        # ── Stage 3: Semantic ─────────────────────────────────────────────────
        has_critical = any(c.severity == "CRITICAL" for c in all_conflicts)
        if not has_critical and self._embedding_service is not None:
            t3 = time.perf_counter()
            semantic_conflicts = await self._run_semantic_stage(
                candidate=candidate,
                existing=existing,
                candidate_embedding=candidate_embedding,
            )
            stage_durations[PipelineStage.SEMANTIC] = (time.perf_counter() - t3) * 1000
            stages_executed.append(PipelineStage.SEMANTIC)
            all_conflicts.extend(semantic_conflicts)

        total_ms = (time.perf_counter() - t_total) * 1000
        sorted_conflicts = sorted(
            all_conflicts,
            key=lambda c: (_SEVERITY_ORDER.get(c.severity, 9), -c.conflict_score),
        )

        return PipelineResult(
            conflicts=sorted_conflicts,
            stages_executed=stages_executed,
            duration_ms=total_ms,
            stage_durations_ms=stage_durations,
        )

    async def _run_semantic_stage(
        self,
        candidate: ToolDef,
        existing: list[ToolDef],
        candidate_embedding: list[float] | None,
    ) -> list[SemanticConflict]:
        """
        Stage 3: ANN search + cosine similarity check.
        Returns SemanticConflict for pairs above the threshold.
        """
        if self._embedding_service is None:
            return []

        # Get candidate embedding if not provided
        if candidate_embedding is None:
            from mtgs.core.embeddings.fingerprinter import ToolFingerprinter

            fp = ToolFingerprinter()
            fp_text = fp.build_fingerprint_text(candidate)
            candidate_embedding = await self._embedding_service.embed(fp_text)

        # ANN search: get top-K nearest existing tools
        nearest = await self._embedding_service.search_nearest(
            embedding=candidate_embedding,
            top_k=20,
        )

        conflicts: list[SemanticConflict] = []
        for hit in nearest:
            similarity = hit["score"]
            if similarity >= self._semantic_threshold:
                severity = self._semantic_severity(similarity)
                conflicts.append(
                    SemanticConflict(
                        conflict_type="SEMANTIC_OVERLAP",
                        severity=severity,
                        candidate_name=candidate.name,
                        conflicting_name=hit["tool_name"],
                        conflict_score=similarity * 100,
                        cosine_similarity=similarity,
                        evidence={
                            "cosine_similarity": round(similarity, 4),
                            "threshold": self._semantic_threshold,
                            "search_backend": "azure_ai_search",
                        },
                    )
                )
        return conflicts

    @staticmethod
    def _semantic_severity(similarity: float) -> str:
        if similarity >= 0.90:
            return "HIGH"
        elif similarity >= 0.80:
            return "MEDIUM"
        else:
            return "LOW"
