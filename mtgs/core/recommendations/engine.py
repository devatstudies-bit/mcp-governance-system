"""
Phase 2C — Recommendation Engine.

Given a detected conflict and the tools involved, asks an LLM (Azure OpenAI gpt-4o)
to generate actionable recommendations that would resolve the conflict.

Key objects
-----------
Recommendation   — a single, structured improvement suggestion.
RecommendationEngine — orchestrator that builds the prompt and parses the LLM response.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from mtgs.core.tool_def import ToolDef

logger = logging.getLogger(__name__)

# Valid recommendation types (closed vocabulary)
VALID_RECOMMENDATION_TYPES = frozenset(
    {"RENAME", "DESCRIPTION_REWRITE", "SCOPE_NARROWING", "SCHEMA_CLARIFICATION", "DEPRECATE"}
)


# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Recommendation:
    """A single actionable recommendation for resolving a tool conflict."""

    recommendation_type: str
    """One of RENAME | DESCRIPTION_REWRITE | SCOPE_NARROWING | SCHEMA_CLARIFICATION | DEPRECATE."""

    target_tool_name: str
    """Name of the tool this recommendation applies to."""

    proposed_change: dict[str, Any]
    """Structured description of the proposed change (field, before, after)."""

    rationale: str
    """Plain-English explanation of why this change helps."""

    predicted_improvement: float
    """Estimated % reduction in routing errors (0–100)."""


# ─────────────────────────────────────────────────────────────────────────────
# Protocol
# ─────────────────────────────────────────────────────────────────────────────


class ChatService(Protocol):
    """Minimal interface expected from the Azure OpenAI chat wrapper."""

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> Any: ...


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────


class RecommendationEngine:
    """
    Use gpt-4o to generate conflict-resolution recommendations.

    Usage
    -----
    engine = RecommendationEngine(chat_service=azure_chat)
    recs = await engine.generate(conflict=conflict_dict, tools=[tool_a, tool_b])
    """

    _SYSTEM_PROMPT = (
        "You are an MCP tool governance expert. "
        "Given a conflict detected between two MCP tools, you propose concrete, "
        "actionable changes to tool names, descriptions, or schemas that would "
        "eliminate or reduce the conflict. "
        "You always respond with valid JSON matching the schema you are given."
    )

    def __init__(self, chat_service: ChatService) -> None:
        self._chat = chat_service

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    async def generate(
        self,
        conflict: dict[str, Any],
        tools: list[ToolDef],
    ) -> list[Recommendation]:
        """
        Generate recommendations for resolving *conflict* between *tools*.

        Returns an empty list on any LLM/parsing failure (never raises).
        """
        prompt = self._build_prompt(conflict, tools)
        try:
            raw = await self._chat.complete_json(
                system_prompt=self._SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            return self._parse_recommendations(raw)
        except Exception:
            logger.exception("RecommendationEngine.generate failed")
            return []

    # ------------------------------------------------------------------ #
    #  Prompt builder (public for testing)                                #
    # ------------------------------------------------------------------ #

    def _build_prompt(
        self,
        conflict: dict[str, Any],
        tools: list[ToolDef],
    ) -> str:
        """Construct the user-facing prompt passed to gpt-4o."""
        conflict_type = conflict.get("conflict_type", "UNKNOWN")
        severity = conflict.get("severity", "UNKNOWN")
        evidence = conflict.get("evidence", {})

        tools_section = "\n".join(
            f"- {t.name} (server: {t.server_name}): {t.description}"
            for t in tools
        )

        evidence_json = json.dumps(evidence, indent=2)

        response_schema = json.dumps(
            {
                "recommendations": [
                    {
                        "recommendation_type": "<RENAME|DESCRIPTION_REWRITE|SCOPE_NARROWING|SCHEMA_CLARIFICATION|DEPRECATE>",
                        "target_tool": "<tool_name>",
                        "proposed_change": {
                            "field": "<name|description|parameter_name>",
                            "before": "<current value>",
                            "after": "<proposed value>",
                        },
                        "rationale": "<plain-English explanation>",
                        "predicted_improvement": "<integer 0-100>",
                    }
                ]
            },
            indent=2,
        )

        return (
            f"## Conflict Report\n\n"
            f"Conflict type : {conflict_type}\n"
            f"Severity      : {severity}\n\n"
            f"### Involved Tools\n\n"
            f"{tools_section}\n\n"
            f"### Evidence\n\n"
            f"```json\n{evidence_json}\n```\n\n"
            f"## Your Task\n\n"
            f"Analyse the conflict above and propose up to 3 actionable recommendations "
            f"that would eliminate or significantly reduce it. Each recommendation must "
            f"target one of the tools listed above.\n\n"
            f"Respond with a JSON object that exactly matches this schema:\n\n"
            f"```json\n{response_schema}\n```\n\n"
            f"Rules:\n"
            f"- `recommendation_type` must be one of: "
            f"RENAME, DESCRIPTION_REWRITE, SCOPE_NARROWING, SCHEMA_CLARIFICATION, DEPRECATE\n"
            f"- `predicted_improvement` is an integer between 0 and 100 estimating the "
            f"% reduction in routing errors if this change is applied.\n"
            f"- Return only the JSON object — no markdown fences, no prose outside JSON."
        )

    # ------------------------------------------------------------------ #
    #  Internal parsing                                                    #
    # ------------------------------------------------------------------ #

    def _parse_recommendations(self, raw: Any) -> list[Recommendation]:
        """
        Coerce LLM output into a list[Recommendation].

        Returns an empty list if the response is structurally invalid.
        """
        if not isinstance(raw, dict):
            logger.warning("Unexpected LLM response type: %s", type(raw))
            return []

        recs_raw = raw.get("recommendations")
        if not isinstance(recs_raw, list):
            logger.warning("Missing 'recommendations' key in LLM response")
            return []

        results: list[Recommendation] = []
        for item in recs_raw:
            if not isinstance(item, dict):
                continue
            rec_type = item.get("recommendation_type", "")
            if rec_type not in VALID_RECOMMENDATION_TYPES:
                logger.warning("Skipping unknown recommendation_type: %s", rec_type)
                continue
            target = item.get("target_tool") or item.get("target_tool_name") or ""
            proposed = item.get("proposed_change") or {}
            rationale = item.get("rationale") or ""
            improvement = item.get("predicted_improvement", 0)
            try:
                improvement = float(improvement)
            except (TypeError, ValueError):
                improvement = 0.0

            if not target or not proposed or not rationale:
                continue

            results.append(
                Recommendation(
                    recommendation_type=rec_type,
                    target_tool_name=str(target),
                    proposed_change=proposed if isinstance(proposed, dict) else {},
                    rationale=str(rationale),
                    predicted_improvement=improvement,
                )
            )

        return results
