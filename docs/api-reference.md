# API Reference

**Base URL:** `https://api.mtgs.yourdomain.com/v1`

All endpoints require authentication. See [Authentication](#authentication).

Interactive docs (non-production only):
- Swagger UI: `{base_url}/docs`
- ReDoc: `{base_url}/redoc`
- OpenAPI JSON: `{base_url}/openapi.json`

---

## Authentication

All API endpoints accept one of:

| Method | Header | Use Case |
|---|---|---|
| JWT | `Authorization: Bearer <access_token>` | User dashboard sessions |
| API Key | `X-API-Key: <raw_key>` | CI/CD pipelines, CLI, programmatic access |

API keys are displayed only once at creation. Store them in a secrets manager.

---

## Environments

Environments are the top-level scope for tool registries. Each environment (`dev`, `staging`, `prod`) has an independent tool set and conflict state.

### `POST /v1/environments`

Create a new environment.

**Request:**
```json
{
  "name": "prod",
  "policy": {
    "max_severity_to_block": "HIGH",
    "auto_approve_below": "LOW"
  }
}
```

**Response `201`:**
```json
{
  "env_id": "550e8400-e29b-41d4-a716-446655440000",
  "org_id": "...",
  "name": "prod",
  "policy": { "max_severity_to_block": "HIGH", "auto_approve_below": "LOW" }
}
```

### `GET /v1/environments`

List all environments for the authenticated organization.

### `GET /v1/environments/{env_id}`

Get environment details and current conflict summary.

---

## Tool Registry

### `POST /v1/environments/{env_id}/tools`

Register a new tool. Triggers async conflict analysis in the background.

**Request:**
```json
{
  "name": "create_salesforce_task",
  "description": "Creates a new task record in Salesforce CRM...",
  "input_schema": {
    "type": "object",
    "properties": {
      "contact_id": { "type": "string", "description": "Salesforce Contact ID" },
      "due_date":   { "type": "string", "description": "ISO 8601 date string" },
      "priority":   { "type": "string", "enum": ["high", "medium", "low"] }
    },
    "required": ["contact_id"]
  },
  "server_id": "abc-123",
  "owner_team_id": "team-456"
}
```

**Response `201`:**
```json
{
  "tool_id": "tool-789",
  "name": "create_salesforce_task",
  "status": "active",
  "analysis_run_id": "run-012",
  "message": "Tool registered. Full conflict analysis running in background."
}
```

**Response `409` (CRITICAL conflict found during sync check):**
```json
{
  "error": "Conflict detected",
  "blocking_conflicts": [
    {
      "type": "EXACT_NAME",
      "severity": "CRITICAL",
      "conflicting_tool": "create_salesforce_task",
      "conflicting_server": "sf-v1-mcp",
      "recommendation": "Rename to include server context, e.g. create_salesforce_v2_task"
    }
  ]
}
```

### `GET /v1/environments/{env_id}/tools`

List all tools in the environment.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `server_id` | UUID | Filter by MCP server |
| `status` | string | `active` \| `deprecated` \| `flagged` \| `pending_approval` |
| `team_id` | UUID | Filter by owner team |
| `has_conflicts` | bool | `true` to return only tools with open conflicts |
| `page` | int | Page number (default: 1) |
| `page_size` | int | Results per page (default: 50, max: 200) |

**Response `200`:**
```json
{
  "tools": [
    {
      "tool_id": "...",
      "name": "create_jira_issue",
      "server": { "id": "...", "name": "jira-mcp" },
      "status": "active",
      "version": 3,
      "open_conflict_count": 1,
      "highest_conflict_severity": "MEDIUM",
      "updated_at": "2025-05-26T10:00:00Z"
    }
  ],
  "total": 142,
  "page": 1,
  "page_size": 50
}
```

### `GET /v1/environments/{env_id}/tools/{tool_id}`

Get a tool with its current conflict summary.

**Response `200`:**
```json
{
  "tool_id": "...",
  "name": "create_jira_issue",
  "description": "...",
  "input_schema": { ... },
  "server": { "id": "...", "name": "jira-mcp" },
  "owner_team": { "id": "...", "name": "Engineering" },
  "status": "active",
  "version": 3,
  "embedding_model": "text-embedding-3-large",
  "created_at": "2025-05-01T09:00:00Z",
  "updated_at": "2025-05-20T14:30:00Z",
  "open_conflicts": [
    {
      "conflict_id": "...",
      "type": "SEMANTIC_OVERLAP",
      "severity": "MEDIUM",
      "conflicting_tool": "create_linear_task",
      "conflict_score": 83.4
    }
  ]
}
```

### `PUT /v1/environments/{env_id}/tools/{tool_id}`

Update a tool definition. Triggers re-analysis. Writes a version history entry.

**Request:** Same shape as `POST /tools` — include only changed fields.

**Response `200`:** Updated tool object with new `version` number and `analysis_run_id`.

### `DELETE /v1/environments/{env_id}/tools/{tool_id}`

Soft-delete (deprecate) a tool. Sets `status = "deprecated"`. Does not delete version history.

**Request body (optional):**
```json
{ "reason": "Superseded by create_jira_issue_v2" }
```

### `GET /v1/environments/{env_id}/tools/{tool_id}/history`

Get the full version history of a tool.

**Response `200`:**
```json
{
  "versions": [
    {
      "version": 3,
      "changed_by": { "id": "...", "name": "Alice" },
      "change_reason": "Narrowed scope to exclude GitHub issues",
      "diff": {
        "description": {
          "before": "Creates an issue in any project management system...",
          "after": "Creates an issue in Jira. Do not use for GitHub Issues..."
        }
      },
      "created_at": "2025-05-20T14:30:00Z"
    }
  ]
}
```

---

## Pre-Registration Check (CI/CD Gate)

### `POST /v1/environments/{env_id}/tools/check`

Dry-run conflict check for a candidate tool **without registering it**. The canonical CI/CD gate endpoint.

**Request:**
```json
{
  "name": "create_task",
  "description": "Creates a new task...",
  "input_schema": { ... },
  "server_id": "my-mcp-server"
}
```

**Response `200`:**
```json
{
  "passed": false,
  "conflicts": [
    {
      "type": "SEMANTIC_OVERLAP",
      "severity": "HIGH",
      "conflicting_tool": "create_jira_issue",
      "similarity_score": 0.91,
      "evidence": {
        "cosine_similarity": 0.91,
        "threshold": 0.80,
        "search_backend": "azure_ai_search"
      }
    }
  ],
  "impact_summary": {
    "routing_shift_pct": 34.0,
    "at_risk_tools": ["create_jira_issue", "create_linear_task"],
    "changed_probes": 17,
    "total_probes": 50
  },
  "recommendations": [
    {
      "type": "DESCRIPTION_REWRITE",
      "target_tool": "create_task",
      "proposed_change": {
        "field": "description",
        "before": "Creates a new task...",
        "after": "Creates a new task in [Your System]. Use this tool ONLY for [System] tasks, not for Jira or Linear issues."
      },
      "predicted_score_after": 42.0,
      "rationale": "Explicit system scoping reduces semantic overlap with Jira and Linear tools."
    }
  ],
  "analysis_run_id": "run-abc",
  "risk_score": 48.0
}
```

---

## CI/CD Webhook

### `POST /v1/webhooks/ci-check`

Intended for GitHub Actions, GitLab CI, Jenkins — accepts a raw tool payload and returns pass/fail.

**Headers:**
```
X-API-Key: <key>
X-Environment: prod
Content-Type: application/json
```

**Request:**
```json
{
  "tool": {
    "name": "create_salesforce_task",
    "description": "Creates a task in Salesforce...",
    "input_schema": { ... }
  },
  "server_id": "salesforce-mcp",
  "policy_override": null
}
```

**Response `200`:**
```json
{
  "status": "FAILED",
  "blocking_conflicts": [
    {
      "type": "SEMANTIC_OVERLAP",
      "severity": "HIGH",
      "conflicting_tool": "create_task",
      "similarity_score": 0.91,
      "recommendation": "Narrow description to specify 'Salesforce CRM only'..."
    }
  ],
  "warnings": [],
  "analysis_run_id": "run_xyz",
  "dashboard_url": "https://mtgs.yourdomain.com/runs/run_xyz"
}
```

HTTP status is always `200`. The `status` field (`PASSED`/`FAILED`) is what CI scripts check. The `mtgs` CLI handles exit code mapping.

---

## Conflict Management

### `GET /v1/environments/{env_id}/conflicts`

List conflicts for an environment.

**Query params:**
| Param | Type | Description |
|---|---|---|
| `severity` | string | Comma-separated: `CRITICAL,HIGH` |
| `status` | string | `open` \| `acknowledged` \| `resolved` \| `suppressed` |
| `type` | string | `EXACT_NAME`, `SEMANTIC_OVERLAP`, etc. |
| `tool_id` | UUID | All conflicts involving this tool |
| `since` | ISO8601 | Detected after this timestamp |

**Response `200`:**
```json
{
  "conflicts": [
    {
      "conflict_id": "...",
      "type": "SEMANTIC_OVERLAP",
      "severity": "HIGH",
      "status": "open",
      "tool_ids": ["tool-a", "tool-b"],
      "tool_names": ["create_jira_issue", "create_ticket"],
      "conflict_score": 91.0,
      "detected_at": "2025-05-26T11:00:00Z",
      "recommendations_count": 2
    }
  ],
  "total": 7
}
```

### `GET /v1/environments/{env_id}/conflicts/{conflict_id}`

Get full conflict detail including evidence and all recommendations.

### `PATCH /v1/environments/{env_id}/conflicts/{conflict_id}`

Update conflict status.

**Request:**
```json
{
  "status": "acknowledged",
  "resolution_notes": "Teams aligned — create_ticket will be deprecated in 2 weeks"
}
```

Valid `status` transitions:
- `open` → `acknowledged` (any EDITOR+)
- `acknowledged` → `resolved` | `suppressed` (APPROVER+ for CRITICAL suppressions)
- `suppressed` → `open` (re-activate)

---

## Analysis Runs

### `POST /v1/environments/{env_id}/analyze`

Trigger a full environment analysis run.

**Request:**
```json
{
  "probe_count": 50,
  "model": "claude-sonnet-4-6"
}
```

**Response `202`:**
```json
{
  "analysis_run_id": "run-abc",
  "status": "pending",
  "message": "Analysis started. Poll GET /analysis-runs/run-abc for status."
}
```

### `GET /v1/api/analysis-runs/{run_id}`

Get analysis run status and results.

**Response `200`:**
```json
{
  "run_id": "run-abc",
  "trigger": "manual",
  "status": "completed",
  "started_at": "2025-05-26T10:00:00Z",
  "completed_at": "2025-05-26T10:01:23Z",
  "tool_set_size": 47,
  "probe_query_count": 50,
  "llm_model": "claude-sonnet-4-6",
  "embedding_model": "text-embedding-3-large",
  "conflicts_found": 3,
  "risk_score": 28.5,
  "routing_shift_pct": 12.0,
  "conflict_ids": ["..."],
  "report_url": "https://storage.mtgs.yourdomain.com/reports/run-abc.json"
}
```

---

## Recommendations

### `GET /v1/conflicts/{conflict_id}/recommendations`

Get all recommendations for a conflict.

### `POST /v1/recommendations/{rec_id}/accept`

Accept a recommendation and optionally apply it to the tool definition.

**Request:**
```json
{ "apply": true }
```

If `apply: true`, the tool definition is updated in-place and a new version entry is created in `tool_versions`.

### `POST /v1/recommendations/{rec_id}/reject`

**Request:**
```json
{ "reason": "Team has decided to deprecate the conflicting tool instead." }
```

---

## Probe Queries

### `GET /v1/environments/{env_id}/probe-queries`

List all probe queries for an environment. Supports `source` filter (`system_generated`, `manual`, `production_log`).

### `POST /v1/environments/{env_id}/probe-queries`

Add a manual probe query.

**Request:**
```json
{
  "query_text": "I need to file a bug report for the login page",
  "expected_tool_id": "tool-jira-123"
}
```

### `POST /v1/environments/{env_id}/probe-queries/generate`

Auto-generate probe queries from the current tool set using Claude.

**Request:**
```json
{ "count": 50 }
```

**Response `202`:** Returns a `job_id`. Poll for completion.

### `DELETE /v1/environments/{env_id}/probe-queries/{query_id}`

Remove a probe query.

---

## Health & Metrics

### `GET /v1/environments/{env_id}/health`

Governance health score for an environment.

**Response `200`:**
```json
{
  "score": 74,
  "grade": "B",
  "active_tools": 142,
  "open_conflicts": {
    "CRITICAL": 0,
    "HIGH": 2,
    "MEDIUM": 5,
    "LOW": 11,
    "INFO": 3
  },
  "last_analysis": "2025-05-26T09:00:00Z",
  "coverage": {
    "probe_queries": 312,
    "tools_with_probes_pct": 87.3
  },
  "trend": "improving"
}
```

**Health score formula:**
```
base = 100
- CRITICAL conflicts: -20 each (max -60)
- HIGH conflicts:     -10 each (max -30)
- MEDIUM conflicts:   -3 each  (max -15)
- LOW conflicts:      -1 each  (max -10)
+ coverage_bonus = probe_coverage_pct × 0.15  (max +15)
```

### `GET /health`

Shallow liveness probe. Always returns `200` if the process is alive.

### `GET /readiness`

Deep readiness probe. Checks database and Redis connectivity. Returns `200` only if both are reachable.

---

## Error Responses

All error responses follow this shape:

```json
{
  "error": "Human-readable error message",
  "detail": [...],
  "request_id": "req-uuid-here"
}
```

| Status | Meaning |
|---|---|
| `400` | Bad request — invalid JSON or missing required fields |
| `401` | Missing or invalid authentication |
| `403` | Authenticated but insufficient role |
| `404` | Resource not found |
| `409` | Conflict — CRITICAL conflict detected on synchronous check |
| `422` | Validation error — Pydantic schema mismatch |
| `429` | Rate limit exceeded (60 req/min standard; 100 req/min CI webhook) |
| `500` | Unhandled server error — check logs |

---

## Rate Limits

| Endpoint group | Limit |
|---|---|
| Standard endpoints | 60 requests/minute per API key |
| `POST /webhooks/ci-check` | 100 requests/minute per API key |

Rate limit headers are included in all responses:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 47
X-RateLimit-Reset: 1716724560
```
