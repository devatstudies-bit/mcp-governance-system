"""
Unit tests for Phase 2F — Analysis Run Orchestrator.

The orchestrator ties together:
  1. Conflict detection pipeline
  2. Probe query generation
  3. Impact simulation
  4. Recommendation engine
  5. Notification dispatch

All sub-services are mocked.

Run:
    pytest tests/unit/test_analysis_orchestrator.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mtgs.core.tool_def import ToolDef

pytestmark = pytest.mark.unit


@pytest.fixture
def tool_a() -> ToolDef:
    return ToolDef(
        name="send_message",
        description="Send a Slack message to a channel.",
        server_name="slack-mcp",
    )


@pytest.fixture
def tool_b() -> ToolDef:
    return ToolDef(
        name="send_message",
        description="Send an email message to a recipient.",
        server_name="email-mcp",
    )


@pytest.fixture
def mock_conflict() -> dict:
    return {
        "conflict_type": "EXACT_NAME",
        "severity": "CRITICAL",
        "evidence": {},
    }


@pytest.fixture
def mock_probe_generator():
    gen = AsyncMock()
    gen.generate_for_tool = AsyncMock(return_value=["Send hello to the team."])
    gen.generate_adversarial = AsyncMock(
        return_value=["Notify the team about the deployment."]
    )
    return gen


@pytest.fixture
def mock_impact_simulator():
    from mtgs.core.simulation.impact_simulator import ImpactReport, ProbeResult

    sim = AsyncMock()
    sim.simulate = AsyncMock(
        return_value=ImpactReport(
            routing_shift_pct=50.0,
            at_risk_tools=["send_message"],
            probe_results=[
                ProbeResult(
                    query="Send hello to the team.",
                    baseline_tool="send_message",
                    candidate_tool="send_message",
                    changed=False,
                )
            ],
            total_probes=1,
            changed_probes=0,
        )
    )
    return sim


@pytest.fixture
def mock_recommendation_engine():
    from mtgs.core.recommendations.engine import Recommendation

    engine = AsyncMock()
    engine.generate = AsyncMock(
        return_value=[
            Recommendation(
                recommendation_type="RENAME",
                target_tool_name="send_message",
                proposed_change={"field": "name", "before": "send_message", "after": "send_slack_message"},
                rationale="Add server prefix to disambiguate.",
                predicted_improvement=95.0,
            )
        ]
    )
    return engine


@pytest.fixture
def mock_notification_router():
    router = AsyncMock()
    router.dispatch = AsyncMock(return_value={"SlackNotifier": True})
    return router


class TestAnalysisOrchestrator:
    @pytest.mark.asyncio
    async def test_run_returns_analysis_result(
        self,
        tool_a,
        tool_b,
        mock_conflict,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator, AnalysisResult

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        result = await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[mock_conflict],
        )

        assert isinstance(result, AnalysisResult)

    @pytest.mark.asyncio
    async def test_result_contains_impact_report(
        self,
        tool_a,
        tool_b,
        mock_conflict,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator
        from mtgs.core.simulation.impact_simulator import ImpactReport

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        result = await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[mock_conflict],
        )

        assert isinstance(result.impact_report, ImpactReport)

    @pytest.mark.asyncio
    async def test_result_contains_recommendations(
        self,
        tool_a,
        tool_b,
        mock_conflict,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator
        from mtgs.core.recommendations.engine import Recommendation

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        result = await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[mock_conflict],
        )

        assert isinstance(result.recommendations, list)
        assert all(isinstance(r, Recommendation) for r in result.recommendations)

    @pytest.mark.asyncio
    async def test_probe_generator_called_for_candidate(
        self,
        tool_a,
        tool_b,
        mock_conflict,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[mock_conflict],
        )

        mock_probe_generator.generate_for_tool.assert_called()

    @pytest.mark.asyncio
    async def test_notification_dispatched_for_critical(
        self,
        tool_a,
        tool_b,
        mock_conflict,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[mock_conflict],  # CRITICAL
        )

        mock_notification_router.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_notification_when_no_conflicts(
        self,
        tool_a,
        tool_b,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[],  # no conflicts
        )

        mock_notification_router.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_result_has_risk_score(
        self,
        tool_a,
        tool_b,
        mock_conflict,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        from mtgs.core.orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        result = await orch.run(
            candidate_tool=tool_a,
            existing_tools=[tool_b],
            conflicts=[mock_conflict],
        )

        assert isinstance(result.risk_score, (int, float))
        assert 0.0 <= result.risk_score <= 100.0

    @pytest.mark.asyncio
    async def test_run_with_no_existing_tools(
        self,
        tool_a,
        mock_probe_generator,
        mock_impact_simulator,
        mock_recommendation_engine,
        mock_notification_router,
    ) -> None:
        """Candidate added to an empty registry — no conflicts, no recommendations needed."""
        from mtgs.core.orchestrator import AnalysisOrchestrator

        orch = AnalysisOrchestrator(
            probe_generator=mock_probe_generator,
            impact_simulator=mock_impact_simulator,
            recommendation_engine=mock_recommendation_engine,
            notification_router=mock_notification_router,
        )
        result = await orch.run(
            candidate_tool=tool_a,
            existing_tools=[],
            conflicts=[],
        )

        assert result.risk_score == 0.0
        assert result.recommendations == []
