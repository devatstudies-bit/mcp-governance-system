"""
MTGS Load Benchmark — Phase 4A.

Uses Locust to simulate concurrent governance API traffic.

Run (headless, 50 users, 10 spawn/s, 60s):
    cd benchmarks
    locust -f locustfile.py --headless -u 50 -r 10 -t 60s \
        --host http://localhost:8000 \
        --html report.html

Run (web UI):
    locust -f locustfile.py --host http://localhost:8000

Key scenarios
-------------
ReadHeavy   — typical dashboard user: health checks, conflict lists, audit log reads
WriteHeavy  — CI/CD pipeline: tool registration + webhook gate
AnalysisRun — analyst: triggering analysis runs and reading results
"""

from __future__ import annotations

import json
import random
import uuid

from locust import HttpUser, between, task


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_TOOL_NAMES = [
    "send_message", "create_task", "query_database",
    "send_email", "create_ticket", "fetch_user",
    "update_record", "delete_item", "list_resources",
]

_SERVERS = ["slack-mcp", "jira-mcp", "db-mcp", "email-mcp", "crm-mcp"]

_ENV_ID = str(uuid.uuid4())    # shared fixture env id
_SERVER_ID = str(uuid.uuid4()) # shared fixture server id


def _tool_payload() -> dict:
    return {
        "name": random.choice(_TOOL_NAMES) + f"_{random.randint(1, 999)}",
        "description": f"A test tool registered at {uuid.uuid4()}",
        "server_id": _SERVER_ID,
        "input_schema": {
            "type": "object",
            "properties": {"input": {"type": "string"}},
        },
    }


_AUTH = {"Authorization": "Bearer benchmark-token"}


# ─────────────────────────────────────────────────────────────────────────────
# User classes
# ─────────────────────────────────────────────────────────────────────────────


class ReadHeavyUser(HttpUser):
    """
    Simulates a dashboard user making read-only requests.
    Weight: 60% of traffic.
    """

    weight = 6
    wait_time = between(0.5, 2.0)

    @task(5)
    def health_check(self) -> None:
        self.client.get("/health", name="/health")

    @task(4)
    def readiness_check(self) -> None:
        self.client.get("/readiness", name="/readiness")

    @task(3)
    def list_conflicts(self) -> None:
        self.client.get(
            f"/v1/environments/{_ENV_ID}/conflicts",
            headers=_AUTH,
            name="/v1/environments/:id/conflicts",
        )

    @task(3)
    def list_tools(self) -> None:
        self.client.get(
            f"/v1/environments/{_ENV_ID}/tools",
            headers=_AUTH,
            name="/v1/environments/:id/tools",
        )

    @task(2)
    def environment_health(self) -> None:
        self.client.get(
            f"/v1/environments/{_ENV_ID}/health",
            headers=_AUTH,
            name="/v1/environments/:id/health",
        )

    @task(2)
    def list_analysis_runs(self) -> None:
        self.client.get(
            "/v1/api/analysis-runs/",
            headers=_AUTH,
            name="/v1/api/analysis-runs/",
        )

    @task(1)
    def list_audit_logs(self) -> None:
        self.client.get(
            "/v1/api/audit-logs/",
            headers=_AUTH,
            name="/v1/api/audit-logs/",
        )

    @task(1)
    def list_pending_approvals(self) -> None:
        self.client.get(
            "/v1/api/approvals/pending",
            headers=_AUTH,
            name="/v1/api/approvals/pending",
        )


class WriteHeavyUser(HttpUser):
    """
    Simulates a CI/CD pipeline registering tools and running webhook checks.
    Weight: 30% of traffic.
    """

    weight = 3
    wait_time = between(1.0, 3.0)

    @task(3)
    def register_tool(self) -> None:
        self.client.post(
            f"/v1/environments/{_ENV_ID}/tools",
            json=_tool_payload(),
            headers=_AUTH,
            name="POST /v1/environments/:id/tools",
        )

    @task(2)
    def ci_webhook_check(self) -> None:
        self.client.post(
            "/v1/webhooks/ci-check",
            json=_tool_payload(),
            headers={
                **_AUTH,
                "X-Environment": _ENV_ID,
                "X-API-Key": "benchmark-api-key",
            },
            name="POST /v1/webhooks/ci-check",
        )

    @task(1)
    def check_tool(self) -> None:
        self.client.post(
            f"/v1/environments/{_ENV_ID}/tools/check",
            json=_tool_payload(),
            headers=_AUTH,
            name="POST /v1/environments/:id/tools/check",
        )


class AnalysisUser(HttpUser):
    """
    Simulates a governance analyst triggering analysis runs and reading reports.
    Weight: 10% of traffic.
    """

    weight = 1
    wait_time = between(2.0, 5.0)

    @task(2)
    def trigger_analysis(self) -> None:
        self.client.post(
            "/v1/api/analysis-runs/",
            json={
                "tool_id": str(uuid.uuid4()),
                "environment_id": _ENV_ID,
                "probe_count": 10,
                "run_simulation": True,
            },
            headers=_AUTH,
            name="POST /v1/api/analysis-runs/",
        )

    @task(3)
    def get_analysis_stats(self) -> None:
        self.client.get(
            "/v1/api/analysis-runs/stats",
            headers=_AUTH,
            name="GET /v1/api/analysis-runs/stats",
        )

    @task(1)
    def export_audit_json(self) -> None:
        self.client.get(
            "/v1/api/audit-logs/export?format=json",
            headers=_AUTH,
            name="GET /v1/api/audit-logs/export",
        )
