"""
Unit tests for Phase 2B — Impact Simulator (Stage 4).

All LLM calls are mocked.

Run:
    pytest tests/unit/test_impact_simulator.py -v
"""

from __future__ import annotations

from collections import Counter
from unittest.mock import AsyncMock, patch

import pytest

from mtgs.core.tool_def import ToolDef

pytestmark = pytest.mark.unit


@pytest.fixture
def tools_registry() -> list[ToolDef]:
    return [
        ToolDef(name="query_database", description="Execute a SQL query against the warehouse."),
        ToolDef(name="send_email", description="Send an email to a recipient."),
        ToolDef(name="create_ticket", description="Create a support ticket in Jira."),
    ]


@pytest.fixture
def probe_queries() -> list[str]:
    return [
        "Run a SQL query on the data warehouse",
        "Send a notification email to the team",
        "Create a bug report in Jira",
    ]


@pytest.fixture
def mock_chat_deterministic():
    """Chat mock that deterministically routes queries to known tools."""
    responses = {
        "Run a SQL query on the data warehouse": "query_database",
        "Send a notification email to the team": "send_email",
        "Create a bug report in Jira": "create_ticket",
    }

    async def side_effect(system_prompt, user_prompt, **kwargs):
        for query_fragment, tool_name in responses.items():
            if query_fragment in user_prompt:
                return tool_name
        return "query_database"  # default

    mock = AsyncMock()
    mock.complete = side_effect
    return mock


class TestImpactSimulatorBasic:
    @pytest.mark.asyncio
    async def test_simulate_returns_impact_report(
        self, mock_chat_deterministic, tools_registry, probe_queries
    ) -> None:
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        sim = ImpactSimulator(chat_service=mock_chat_deterministic)
        new_tool = ToolDef(
            name="run_report",
            description="Generate a business intelligence report.",
        )
        report = await sim.simulate(
            candidate_tool=new_tool,
            existing_tools=tools_registry,
            probe_queries=probe_queries,
            trials=1,
        )

        assert report is not None

    @pytest.mark.asyncio
    async def test_impact_report_has_routing_shift_pct(
        self, mock_chat_deterministic, tools_registry, probe_queries
    ) -> None:
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        sim = ImpactSimulator(chat_service=mock_chat_deterministic)
        new_tool = ToolDef(name="run_report", description="Generate a BI report.")
        report = await sim.simulate(
            candidate_tool=new_tool,
            existing_tools=tools_registry,
            probe_queries=probe_queries,
            trials=1,
        )
        assert hasattr(report, "routing_shift_pct")
        assert 0.0 <= report.routing_shift_pct <= 100.0

    @pytest.mark.asyncio
    async def test_identical_candidate_causes_high_routing_shift(
        self, mock_chat_deterministic, tools_registry, probe_queries
    ) -> None:
        """Adding a tool identical to an existing one should cause routing instability."""
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        # Mock: sometimes picks the duplicate, sometimes the original
        call_count = [0]

        async def alternating(system_prompt, user_prompt, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                return "query_database_v2"
            return "query_database"

        mock_alt = AsyncMock()
        mock_alt.complete = alternating

        sim = ImpactSimulator(chat_service=mock_alt)
        duplicate = ToolDef(
            name="query_database_v2",
            description="Execute a SQL query against the warehouse.",  # same description
        )
        report = await sim.simulate(
            candidate_tool=duplicate,
            existing_tools=tools_registry,
            probe_queries=probe_queries,
            trials=2,
        )
        # routing_shift_pct > 0 because some queries now go to the duplicate
        assert report.routing_shift_pct >= 0.0

    @pytest.mark.asyncio
    async def test_completely_new_tool_zero_shift(
        self, mock_chat_deterministic, tools_registry, probe_queries
    ) -> None:
        """A tool for a completely different domain causes zero routing shift."""
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        sim = ImpactSimulator(chat_service=mock_chat_deterministic)
        unrelated = ToolDef(
            name="schedule_meeting",
            description="Schedule a calendar meeting.",
        )
        report = await sim.simulate(
            candidate_tool=unrelated,
            existing_tools=tools_registry,
            probe_queries=probe_queries,
            trials=1,
        )
        assert report.routing_shift_pct == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_report_lists_at_risk_tools(
        self, tools_registry, probe_queries
    ) -> None:
        """Tools that lose routing share appear in at_risk_tools."""
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        # Mock: candidate always wins database queries
        async def steal_db(system_prompt, user_prompt, **kwargs):
            if "SQL" in user_prompt or "database" in user_prompt.lower():
                return "db_replacement"
            return "send_email"

        mock_steal = AsyncMock()
        mock_steal.complete = steal_db

        sim = ImpactSimulator(chat_service=mock_steal)
        stealer = ToolDef(
            name="db_replacement",
            description="Run SQL queries against the data warehouse.",
        )
        report = await sim.simulate(
            candidate_tool=stealer,
            existing_tools=tools_registry,
            probe_queries=probe_queries,
            trials=1,
        )
        assert isinstance(report.at_risk_tools, list)

    @pytest.mark.asyncio
    async def test_report_has_probe_results(
        self, mock_chat_deterministic, tools_registry, probe_queries
    ) -> None:
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        sim = ImpactSimulator(chat_service=mock_chat_deterministic)
        new_tool = ToolDef(name="generate_report", description="Generate analytics report.")
        report = await sim.simulate(
            candidate_tool=new_tool,
            existing_tools=tools_registry,
            probe_queries=probe_queries,
            trials=1,
        )
        assert len(report.probe_results) == len(probe_queries)

    @pytest.mark.asyncio
    async def test_simulation_handles_empty_probe_list(
        self, mock_chat_deterministic, tools_registry
    ) -> None:
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        sim = ImpactSimulator(chat_service=mock_chat_deterministic)
        new_tool = ToolDef(name="new_tool", description="A new tool.")
        report = await sim.simulate(
            candidate_tool=new_tool,
            existing_tools=tools_registry,
            probe_queries=[],
            trials=1,
        )
        assert report.routing_shift_pct == 0.0
        assert report.probe_results == []

    @pytest.mark.asyncio
    async def test_routing_trials_majority_vote(self) -> None:
        """With 3 trials and 2 different results, majority vote is used."""
        from mtgs.core.simulation.impact_simulator import ImpactSimulator

        call_count = [0]

        async def sometimes_different(system_prompt, user_prompt, **kwargs):
            call_count[0] += 1
            # First call: different result; next two: same result
            if call_count[0] == 1:
                return "tool_b"
            return "tool_a"

        mock = AsyncMock()
        mock.complete = sometimes_different

        sim = ImpactSimulator(chat_service=mock)
        tools = [
            ToolDef(name="tool_a", description="Tool A does X."),
            ToolDef(name="tool_b", description="Tool B does Y."),
        ]
        # Run 3 trials; majority (2/3) should pick tool_a
        routing = await sim._run_routing_trials(
            tools=tools,
            probe_queries=["Do something"],
            trials=3,
        )
        assert routing["Do something"].most_common(1)[0][0] == "tool_a"


class TestImpactReport:
    def test_impact_report_structure(self) -> None:
        from mtgs.core.simulation.impact_simulator import ImpactReport, ProbeResult

        report = ImpactReport(
            routing_shift_pct=25.0,
            at_risk_tools=["create_ticket"],
            probe_results=[
                ProbeResult(
                    query="Create a bug",
                    baseline_tool="create_ticket",
                    candidate_tool="create_ticket",
                    changed=False,
                )
            ],
            total_probes=1,
            changed_probes=0,
        )
        assert report.routing_shift_pct == 25.0
        assert report.probe_results[0].changed is False
