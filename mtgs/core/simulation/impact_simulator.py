"""
Phase 2B — Impact Simulator (Stage 4 of conflict pipeline).

Simulates LLM tool-routing behaviour before and after adding a candidate tool,
measuring how many probe queries change their routing destination.

Key objects
-----------
ProbeResult   — per-query result comparing baseline vs candidate routing.
ImpactReport  — aggregated report for one simulation run.
ImpactSimulator — orchestrator that runs the simulation.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Protocol

from mtgs.core.tool_def import ToolDef

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ProbeResult:
    """Result for a single probe query in the simulation."""

    query: str
    """The natural-language probe query."""

    baseline_tool: str
    """Tool name selected by the LLM *without* the candidate tool in the registry."""

    candidate_tool: str
    """Tool name selected by the LLM *with* the candidate tool in the registry."""

    changed: bool
    """True when baseline_tool != candidate_tool (routing was disturbed)."""


@dataclass
class ImpactReport:
    """Aggregated result of one impact simulation run."""

    routing_shift_pct: float
    """Percentage of probe queries whose routing changed (0–100)."""

    at_risk_tools: list[str]
    """Existing tool names that lost routing share."""

    probe_results: list[ProbeResult]
    """Per-query routing comparison."""

    total_probes: int
    """Total number of probe queries evaluated."""

    changed_probes: int
    """Number of probes whose routing changed."""


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────


class ChatService(Protocol):
    """Minimal interface for the LLM routing simulation."""

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> str: ...


# ─────────────────────────────────────────────────────────────────────────────
# Simulator
# ─────────────────────────────────────────────────────────────────────────────


class ImpactSimulator:
    """
    Simulate the routing impact of adding a new tool to an existing registry.

    Algorithm
    ---------
    1. For each probe query, ask the LLM to pick the best tool from the *baseline*
       registry (existing tools only) — repeat `trials` times, take the majority vote.
    2. Repeat with the *candidate* tool added to the registry.
    3. Compare baseline vs candidate routing per query; compute shift %.
    """

    _SYSTEM_ROUTING = (
        "You are an AI assistant choosing the right tool from a list. "
        "Given a user request and a JSON list of tools (name + description), "
        "respond with ONLY the tool name that best handles the request. "
        "No explanation. No formatting. Just the tool name exactly as given."
    )

    def __init__(self, chat_service: ChatService) -> None:
        self._chat = chat_service

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def simulate(
        self,
        candidate_tool: ToolDef,
        existing_tools: list[ToolDef],
        probe_queries: list[str],
        trials: int = 3,
    ) -> ImpactReport:
        """
        Run the full impact simulation.

        Parameters
        ----------
        candidate_tool:
            The new tool being evaluated.
        existing_tools:
            Current tool registry (without the candidate).
        probe_queries:
            Natural-language queries to probe routing behaviour.
        trials:
            Number of LLM calls per query per configuration (majority vote).
        """
        if not probe_queries:
            return ImpactReport(
                routing_shift_pct=0.0,
                at_risk_tools=[],
                probe_results=[],
                total_probes=0,
                changed_probes=0,
            )

        # Step 1: baseline routing (existing tools only)
        baseline_routing = await self._run_routing_trials(
            tools=existing_tools,
            probe_queries=probe_queries,
            trials=trials,
        )

        # Step 2: candidate routing (existing + candidate)
        candidate_registry = existing_tools + [candidate_tool]
        candidate_routing = await self._run_routing_trials(
            tools=candidate_registry,
            probe_queries=probe_queries,
            trials=trials,
        )

        # Step 3: compare
        probe_results: list[ProbeResult] = []
        at_risk_set: set[str] = set()

        for query in probe_queries:
            baseline_winner = self._majority(baseline_routing.get(query, Counter()))
            candidate_winner = self._majority(candidate_routing.get(query, Counter()))
            changed = baseline_winner != candidate_winner
            if changed:
                at_risk_set.add(baseline_winner)
            probe_results.append(
                ProbeResult(
                    query=query,
                    baseline_tool=baseline_winner,
                    candidate_tool=candidate_winner,
                    changed=changed,
                )
            )

        total = len(probe_results)
        changed_count = sum(1 for r in probe_results if r.changed)
        shift_pct = (changed_count / total * 100.0) if total > 0 else 0.0

        return ImpactReport(
            routing_shift_pct=round(shift_pct, 2),
            at_risk_tools=sorted(at_risk_set),
            probe_results=probe_results,
            total_probes=total,
            changed_probes=changed_count,
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers (public for unit-testing)                         #
    # ------------------------------------------------------------------ #

    async def _run_routing_trials(
        self,
        tools: list[ToolDef],
        probe_queries: list[str],
        trials: int,
    ) -> dict[str, Counter]:
        """
        For each probe query, run `trials` LLM calls and collect tool-name votes.

        Returns
        -------
        dict[query -> Counter[tool_name -> vote_count]]
        """
        routing: dict[str, Counter] = {q: Counter() for q in probe_queries}

        tool_list_json = json.dumps(
            [{"name": t.name, "description": t.description} for t in tools],
            indent=2,
        )

        for _ in range(trials):
            for query in probe_queries:
                user_prompt = (
                    f"User request: {query}\n\n"
                    f"Available tools:\n{tool_list_json}"
                )
                try:
                    chosen = await self._chat.complete(
                        system_prompt=self._SYSTEM_ROUTING,
                        user_prompt=user_prompt,
                    )
                    chosen = chosen.strip()
                except Exception:
                    logger.exception("ImpactSimulator._run_routing_trials LLM error")
                    chosen = ""

                if chosen:
                    routing[query][chosen] += 1

        return routing

    @staticmethod
    def _majority(counter: Counter) -> str:
        """Return the most-voted tool name, or '' if counter is empty."""
        if not counter:
            return ""
        return counter.most_common(1)[0][0]
