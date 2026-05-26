"""
Phase 2F — Analysis Run Orchestrator.

Ties together the full Phase 2 pipeline:

  1. Generate probe queries for the candidate tool
  2. Run impact simulation (before/after routing comparison)
  3. For each detected conflict → generate recommendations
  4. Dispatch notifications for CRITICAL/HIGH conflicts
  5. Return a structured AnalysisResult

Designed to be called from:
  - Celery task `run_conflict_analysis_task`
  - FastAPI background task on tool registration
  - CLI `mtgs analyze`
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from mtgs.core.tool_def import ToolDef
from mtgs.core.recommendations.engine import Recommendation
from mtgs.core.simulation.impact_simulator import ImpactReport

logger = logging.getLogger(__name__)

# Severity → numeric weight for risk score calculation
_SEVERITY_WEIGHT = {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 10, "LOW": 5}
_MAX_RISK_SCORE = 100.0

# Severities that trigger notifications
_NOTIFY_SEVERITIES = frozenset({"CRITICAL", "HIGH"})


# ─────────────────────────────────────────────────────────────────────────────
# Protocols
# ─────────────────────────────────────────────────────────────────────────────


class ProbeGenerator(Protocol):
    async def generate_for_tool(self, tool: ToolDef, count: int = 10) -> list[str]: ...
    async def generate_adversarial(
        self, tool_a: ToolDef, tool_b: ToolDef, count: int = 5
    ) -> list[str]: ...


class ImpactSimulatorProtocol(Protocol):
    async def simulate(
        self,
        candidate_tool: ToolDef,
        existing_tools: list[ToolDef],
        probe_queries: list[str],
        trials: int = 3,
    ) -> ImpactReport: ...


class RecommendationEngineProtocol(Protocol):
    async def generate(
        self,
        conflict: dict[str, Any],
        tools: list[ToolDef],
    ) -> list[Recommendation]: ...


class NotificationRouterProtocol(Protocol):
    async def dispatch(self, event: dict[str, Any]) -> dict[str, bool]: ...


# ─────────────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    """Full output of one analysis run."""

    candidate_tool: ToolDef
    """The tool that was analysed."""

    conflicts: list[dict[str, Any]]
    """Conflict dicts as produced by the conflict detection pipeline."""

    impact_report: ImpactReport
    """Routing-shift simulation report."""

    recommendations: list[Recommendation]
    """Actionable improvement recommendations (one set per conflict)."""

    risk_score: float
    """Composite risk score 0–100 derived from conflict severity + routing shift."""

    notification_results: dict[str, bool] = field(default_factory=dict)
    """Results from the notification router per channel."""


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────────────────────


class AnalysisOrchestrator:
    """
    Full Phase 2 analysis pipeline.

    Parameters
    ----------
    probe_generator:
        Generates natural-language probe queries.
    impact_simulator:
        Simulates LLM routing with/without the candidate tool.
    recommendation_engine:
        Generates conflict-resolution recommendations.
    notification_router:
        Dispatches alerts to Slack/email/PagerDuty.
    probe_count:
        Number of probe queries to generate per tool.
    simulation_trials:
        LLM routing trials per probe query (majority vote).
    """

    def __init__(
        self,
        probe_generator: Any,
        impact_simulator: Any,
        recommendation_engine: Any,
        notification_router: Any,
        probe_count: int = 10,
        simulation_trials: int = 3,
    ) -> None:
        self._probes = probe_generator
        self._simulator = impact_simulator
        self._recommender = recommendation_engine
        self._notifier = notification_router
        self._probe_count = probe_count
        self._trials = simulation_trials

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def run(
        self,
        candidate_tool: ToolDef,
        existing_tools: list[ToolDef],
        conflicts: list[dict[str, Any]],
    ) -> AnalysisResult:
        """
        Execute the full analysis pipeline.

        Parameters
        ----------
        candidate_tool:
            The new or updated tool being evaluated.
        existing_tools:
            Current tool registry (without the candidate).
        conflicts:
            Conflict dicts produced by the upstream conflict detection pipeline.
            Pass an empty list if no conflicts were found.
        """
        # Fast path: no existing tools → nothing to conflict with
        if not existing_tools:
            empty_report = ImpactReport(
                routing_shift_pct=0.0,
                at_risk_tools=[],
                probe_results=[],
                total_probes=0,
                changed_probes=0,
            )
            return AnalysisResult(
                candidate_tool=candidate_tool,
                conflicts=[],
                impact_report=empty_report,
                recommendations=[],
                risk_score=0.0,
            )

        # Step 1: generate probe queries
        probe_queries = await self._generate_probes(candidate_tool, existing_tools, conflicts)

        # Step 2: run impact simulation
        impact_report = await self._simulator.simulate(
            candidate_tool=candidate_tool,
            existing_tools=existing_tools,
            probe_queries=probe_queries,
            trials=self._trials,
        )

        # Step 3: generate recommendations for each conflict (concurrent)
        recommendations = await self._generate_recommendations(
            conflicts, candidate_tool, existing_tools
        )

        # Step 4: compute risk score
        risk_score = self._compute_risk_score(conflicts, impact_report)

        # Step 5: dispatch notifications for high-severity conflicts
        notification_results = await self._maybe_notify(
            candidate_tool, conflicts, impact_report
        )

        return AnalysisResult(
            candidate_tool=candidate_tool,
            conflicts=conflicts,
            impact_report=impact_report,
            recommendations=recommendations,
            risk_score=risk_score,
            notification_results=notification_results,
        )

    # ------------------------------------------------------------------ #
    #  Internal steps                                                      #
    # ------------------------------------------------------------------ #

    async def _generate_probes(
        self,
        candidate: ToolDef,
        existing: list[ToolDef],
        conflicts: list[dict[str, Any]],
    ) -> list[str]:
        """Generate probe queries: candidate-specific + adversarial for each conflict."""
        tasks = [self._probes.generate_for_tool(candidate, count=self._probe_count)]

        for conflict in conflicts:
            evidence = conflict.get("evidence", {})
            conflicting_name = (
                evidence.get("conflicting_tool")
                or evidence.get("candidate_tool")
            )
            conflicting_tool = next(
                (t for t in existing if t.name == conflicting_name), None
            )
            if conflicting_tool:
                tasks.append(
                    self._probes.generate_adversarial(
                        candidate, conflicting_tool, count=5
                    )
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        queries: list[str] = []
        for r in results:
            if isinstance(r, list):
                queries.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Probe generation task failed: %s", r)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for q in queries:
            if q not in seen:
                seen.add(q)
                unique.append(q)
        return unique

    async def _generate_recommendations(
        self,
        conflicts: list[dict[str, Any]],
        candidate: ToolDef,
        existing: list[ToolDef],
    ) -> list[Recommendation]:
        """Ask the recommendation engine for each conflict (concurrent)."""
        if not conflicts:
            return []

        tasks = [
            self._recommender.generate(conflict=c, tools=[candidate] + existing)
            for c in conflicts
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_recs: list[Recommendation] = []
        for r in results:
            if isinstance(r, list):
                all_recs.extend(r)
            elif isinstance(r, Exception):
                logger.warning("Recommendation generation failed: %s", r)
        return all_recs

    async def _maybe_notify(
        self,
        candidate: ToolDef,
        conflicts: list[dict[str, Any]],
        impact_report: ImpactReport,
    ) -> dict[str, bool]:
        """Dispatch notification if any conflict meets the severity threshold."""
        notify_conflicts = [
            c for c in conflicts if c.get("severity") in _NOTIFY_SEVERITIES
        ]
        if not notify_conflicts:
            return {}

        # Use the highest severity conflict as the event payload
        top_conflict = max(
            notify_conflicts,
            key=lambda c: _SEVERITY_WEIGHT.get(c.get("severity", "LOW"), 0),
        )

        event: dict[str, Any] = {
            "event_type": "CONFLICT_DETECTED",
            "severity": top_conflict.get("severity"),
            "conflict_type": top_conflict.get("conflict_type"),
            "tool_names": [candidate.name],
            "server_names": [candidate.server_name],
            "routing_shift_pct": impact_report.routing_shift_pct,
            "at_risk_tools": impact_report.at_risk_tools,
            "total_conflicts": len(conflicts),
        }

        try:
            return await self._notifier.dispatch(event)
        except Exception:
            logger.exception("AnalysisOrchestrator._maybe_notify failed")
            return {}

    @staticmethod
    def _compute_risk_score(
        conflicts: list[dict[str, Any]],
        impact_report: ImpactReport,
    ) -> float:
        """
        Composite risk score (0–100).

        Formula:
          base = sum(severity_weight per conflict), capped at 60
          simulation_component = routing_shift_pct * 0.4 (max 40)
          risk_score = min(base + simulation_component, 100)
        """
        base = sum(
            _SEVERITY_WEIGHT.get(c.get("severity", "LOW"), 0) for c in conflicts
        )
        base = min(base, 60)
        simulation_component = impact_report.routing_shift_pct * 0.4
        return round(min(base + simulation_component, _MAX_RISK_SCORE), 2)
