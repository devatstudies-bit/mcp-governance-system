# Architecture

This document describes the internal design of MTGS — how components relate, how data flows, and the key engineering decisions behind each layer.

---

## Table of Contents

1. [System Context](#1-system-context)
2. [Component Diagram](#2-component-diagram)
3. [Data Flow: Tool Registration](#3-data-flow-tool-registration)
4. [Data Flow: CI/CD Gate](#4-data-flow-cicd-gate)
5. [Conflict Detection Pipeline](#5-conflict-detection-pipeline)
6. [Embedding Strategy](#6-embedding-strategy)
7. [Impact Simulation Design](#7-impact-simulation-design)
8. [Recommendation Engine](#8-recommendation-engine)
9. [Async Job Architecture](#9-async-job-architecture)
10. [Data Models](#10-data-models)
11. [Authentication & Authorization](#11-authentication--authorization)
12. [Observability](#12-observability)
13. [Scalability Considerations](#13-scalability-considerations)

---

## 1. System Context

MTGS sits between your development workflow and your MCP server deployment. It intercepts tool definitions before they go live and validates them against the existing registry.

```
  Developer         CI/CD Pipeline       MCP Server
     │                    │                  │
     │  mtgs check tool   │                  │
     ├───────────────────►│                  │
     │                    │ POST /webhooks/  │
     │                    │   ci-check       │
     │                    ├─────────────────►│ (MTGS API)
     │                    │  pass/fail + recs│
     │                    │◄─────────────────┤
     │     Only if PASS   │                  │
     │                    ├──────────────────► MCP Server
     │                    │  register tool   │
```

---

## 2. Component Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                         Client Layer                               │
│                                                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │  React Dashboard│  │  CLI (mtgs)      │  │  CI/CD Webhook   │ │
│  │  (React + D3.js)│  │  (Typer + Rich)  │  │  (GH Actions etc)│ │
│  └────────┬────────┘  └────────┬─────────┘  └────────┬─────────┘ │
└───────────┼────────────────────┼────────────────────  ┼───────────┘
            │        HTTPS/REST   │                      │
┌───────────▼────────────────────▼──────────────────────▼───────────┐
│                        FastAPI Application                         │
│                                                                   │
│  ┌────────────────┐  ┌─────────────┐  ┌───────────┐  ┌─────────┐ │
│  │RequestID Middle│  │ Access Log  │  │   CORS    │  │  Auth   │ │
│  │ware            │  │ Middleware  │  │           │  │  Layer  │ │
│  └────────────────┘  └─────────────┘  └───────────┘  └────┬────┘ │
│                                                            │      │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  ┌──────▼────┐ │
│  │ /v1/tools   │  │/v1/conflicts │  │/v1/health│  │ /v1/web-  │ │
│  │ (Registry)  │  │(Conflict Mgmt│  │          │  │  hooks    │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────┘  └──────┬────┘ │
└─────────┼────────────────┼────────────────────────────────┼──────┘
          │                │                                 │
┌─────────▼────────────────▼─────────────────────────────────▼──────┐
│                      Core Services                                  │
│                                                                    │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐ │
│  │  ConflictDetectionPipeline  │  │  AnalysisOrchestrator       │ │
│  │  Stage 1: LexicalAnalyzer   │  │  (ties Phase 2 together)    │ │
│  │  Stage 2: SchemaAnalyzer    │  └──────────┬──────────────────┘ │
│  │  Stage 3: AzureSearchClient │             │                    │
│  │  Stage 4: ImpactSimulator   │  ┌──────────▼──────────────────┐ │
│  └──────────────────────────── ┘  │  RecommendationEngine       │ │
│                                   │  ProbeQueryGenerator        │ │
│  ┌─────────────────────────────┐  │  NotificationRouter         │ │
│  │  ApprovalWorkflow           │  └─────────────────────────────┘ │
│  │  AuditLogger                │                                  │
│  │  MCPSyncService             │                                  │
│  └─────────────────────────────┘                                  │
└────────────────────────┬───────────────────────────────────────────┘
                         │  Celery tasks dispatched here
┌────────────────────────▼───────────────────────────────────────────┐
│                     Celery Worker Pool                              │
│                                                                    │
│  Queue: analysis          Queue: simulation       Queue: embeddings │
│  ┌────────────────────┐  ┌─────────────────────┐  ┌──────────────┐│
│  │run_conflict_       │  │run_impact_simulation│  │compute_      ││
│  │analysis_task       │  │_task                │  │embeddings    ││
│  └──────────┬─────────┘  └──────────┬──────────┘  └──────┬───────┘│
└─────────────┼───────────────────────┼────────────────────-┼────────┘
              │                       │                      │
┌─────────────▼───────────────────────▼──────────────────────▼───────┐
│                     External Services                               │
│                                                                    │
│  ┌──────────────────┐  ┌──────────────────────┐  ┌───────────────┐│
│  │  Azure OpenAI    │  │  Azure AI Search      │  │ Anthropic API ││
│  │  Embeddings      │  │  (ANN vector search)  │  │ Claude Sonnet ││
│  │  text-emb-3-large│  │                       │  │ (sim + recs)  ││
│  └──────────────────┘  └──────────────────────┘  └───────────────┘│
└────────────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼───────────────────────────────────────────┐
│                       Data Layer                                    │
│                                                                    │
│  PostgreSQL 16           Redis 7             Azure Blob Storage    │
│  ┌────────────────────┐  ┌──────────────┐   ┌────────────────────┐│
│  │ tools              │  │ Embedding    │   │ Analysis artifacts ││
│  │ conflicts          │  │ cache (24h)  │   │ (snapshots, reports││
│  │ analysis_runs      │  │ Rate limit   │   │  PDF exports)      ││
│  │ probe_queries      │  │ counters     │   └────────────────────┘│
│  │ recommendations    │  │              │                         │
│  │ environments       │  │              │                         │
│  │ audit_log          │  └──────────────┘                         │
│  └────────────────────┘                                           │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Data Flow: Tool Registration

When a developer registers a new tool, the following sequence executes:

```
1.  POST /v1/environments/{env_id}/tools
    ├── Auth middleware validates JWT or API key
    ├── ApprovalWorkflow checks: does this org require pre-approval?
    │   └── If yes → tool written with status=pending_approval, returns 202
    │   └── If no  → continues
    │
2.  ToolDef validated against Pydantic schema
    ├── name pattern check
    ├── description length check
    └── inputSchema JSON Schema validation
    │
3.  Stages 1+2 run synchronously (lexical + schema, < 300ms total)
    └── If CRITICAL found → return 409 Conflict immediately with blocking detail
    │
4.  Tool written to DB with status=active
    │
5.  Celery task dispatched: run_conflict_analysis_task(tool_id, env_id)
    │
6.  API returns 201 with { tool_id, status, analysis_run_id }
    │   (analysis continues asynchronously)
    │
7.  Worker picks up task:
    ├── Stage 3: Azure AI Search ANN → semantic conflicts
    ├── Stage 4: Claude Sonnet probe queries → routing simulation
    ├── RecommendationEngine → generate fixes
    ├── AuditLogger → immutable record
    └── NotificationRouter → Slack/email if CRITICAL/HIGH
```

**Key latency properties:**
- Synchronous path (steps 1–6): < 500ms
- Full analysis (step 7): 10–60s depending on registry size

---

## 4. Data Flow: CI/CD Gate

The CI/CD gate is a dry-run path — tools are **not** committed to the registry.

```
1.  POST /v1/webhooks/ci-check
    Headers: X-API-Key, X-Environment

    Body: { tool: { name, description, input_schema }, server_id }
    │
2.  Synchronous full analysis (all 4 stages)
    ├── Stage 1: Lexical (hash lookup, edit distance)
    ├── Stage 2: Schema (parameter overlap)
    ├── Stage 3: Semantic (embedding cosine similarity)
    └── Stage 4: Behavioral (LLM routing simulation)
    │
3.  Policy check: does highest conflict severity exceed CI_FAIL_ON_SEVERITY?
    └── Default: fail on HIGH or CRITICAL
    │
4.  Return:
    {
      "status": "PASSED" | "FAILED",
      "blocking_conflicts": [...],
      "warnings": [...],
      "recommendations": [...],
      "analysis_run_id": "...",
      "dashboard_url": "..."
    }
    │
5.  HTTP 200 with status=PASSED → CI continues
    HTTP 200 with status=FAILED → CI pipeline fails on non-zero exit (mtgs CLI handles this)
```

---

## 5. Conflict Detection Pipeline

See [Conflict Detection deep-dive](conflict-detection.md) for full details. Summary:

### Stage 1 — Lexical (< 100ms)

Implemented in `mtgs/core/conflict_detection/lexical.py`.

- **Exact name match:** O(1) hash set lookup across all active tool names in the environment
- **Edit distance:** Levenshtein distance ≤ 2 via `rapidfuzz` → `SIMILAR_NAME` conflict
- **Token overlap:** Jaccard similarity on whitespace+underscore tokenized names → `SIMILAR_NAME`

### Stage 2 — Schema Analysis (< 200ms)

Implemented in `mtgs/core/conflict_detection/schema_analysis.py`.

- Extracts `properties` from each tool's `inputSchema`
- For each shared parameter name: checks type mismatch, description mismatch
- Reports `SCHEMA_COLLISION` when parameter names collide with different semantics

### Stage 3 — Semantic (1–3s)

Implemented in `mtgs/core/conflict_detection/pipeline.py` (`_run_semantic_stage`).

- Calls `ToolFingerprinter.build_fingerprint_text()` — composite of name + description + schema summary
- Embeds via Azure OpenAI `text-embedding-3-large` (3072 dims)
- ANN search via Azure AI Search: retrieves top-20 nearest tools
- Cosine similarity above 0.80 → `SEMANTIC_OVERLAP`

**Severity mapping:**
```
≥ 0.90  →  HIGH
0.80–0.90 →  MEDIUM
0.70–0.80 →  LOW (advisory)
```

### Stage 4 — Behavioral (10–60s)

Implemented in `mtgs/core/simulation/impact_simulator.py`.

- Runs only for pairs flagged by Stage 3
- Generates probe queries (via `ProbeQueryGenerator`) and runs LLM routing tests
- 3 trials per probe query → majority vote → routing distribution
- `routing_split > 0.30` between two tools → `INTENT_AMBIGUITY` conflict
- Computes final `conflict_score` (0–100) and `risk_score`

### Short-circuit Logic

```python
# In pipeline.py
has_critical = any(c.severity == "CRITICAL" for c in all_conflicts)
if not has_critical and self._embedding_service is not None:
    # Run Stage 3
```

If Stage 1 finds a CRITICAL (exact name collision across servers), Stage 3 is skipped entirely. LLM calls are expensive; a name collision is already definitively unacceptable.

---

## 6. Embedding Strategy

`ToolFingerprinter` (`mtgs/core/embeddings/fingerprinter.py`) builds a structured composite text rather than embedding just the description:

```
Tool name: create_salesforce_task
Purpose: Creates a new task record in Salesforce CRM for the specified contact.
Parameters accepted: contact_id (string): Salesforce Contact ID, due_date (string): ISO8601 date, priority (string): high|medium|low
Server context: salesforce-mcp
```

**Why composite embedding:**
- Prevents false positives: `create_ticket` (Jira) and `create_record` (Salesforce) may have similar descriptions but completely different parameter sets
- The server context adds implicit domain signal

**Cache strategy:**
- Embeddings cached keyed on `SHA256(fingerprint_text + model_version)` with 24h TTL in Redis
- Re-embedding only occurs when the tool definition changes
- The fingerprint hash is stored in the DB alongside the tool — stale check is O(1)

---

## 7. Impact Simulation Design

`ImpactSimulator` (`mtgs/core/simulation/impact_simulator.py`) answers the question: *"If we add this tool, which existing tool routing shifts?"*

```
baseline_tools = [all existing active tools]
candidate_tools = baseline_tools + [candidate_tool]

For each probe_query in probe_queries:
  baseline_routing  = LLM_select(baseline_tools,  probe_query) × 3 trials
  candidate_routing = LLM_select(candidate_tools, probe_query) × 3 trials

routing_shift = queries where winner changed / total queries
at_risk_tools = tools whose routing share dropped > 10%
```

The LLM prompt is deliberately minimal:
```
You are an AI assistant with access to the following tools.
Given the user's request, respond ONLY with the name of the single best tool.
Do not call the tool. Do not explain. Output only the tool name.

Available tools: {tool_definitions_formatted}
User request: {probe_query}
Best tool name:
```

This isolates the routing signal from explanation noise and gives clean, reproducible, auditable routing decisions.

**Risk Score Formula** (in `orchestrator.py`):
```
base = Σ severity_weight(conflict)  →  capped at 60
       { CRITICAL: 40, HIGH: 20, MEDIUM: 10, LOW: 5 }
simulation_component = routing_shift_pct × 0.4   →  max 40
risk_score = min(base + simulation_component, 100)
```

---

## 8. Recommendation Engine

`RecommendationEngine` (`mtgs/core/recommendations/engine.py`) uses Claude Sonnet to generate specific, actionable fixes for each detected conflict.

**Recommendation types:**

| Type | Description |
|---|---|
| `RENAME` | Alternative tool name that is more distinct |
| `DESCRIPTION_REWRITE` | Revised description reducing semantic overlap |
| `SCOPE_NARROWING` | Explicit exclusions (e.g., "Use this only for X; not Y") |
| `SCHEMA_CLARIFICATION` | Parameter renaming or documentation additions |
| `DEPRECATE` | Advisory when a tool is fully superseded |

Each recommendation includes:
- The exact before/after text (not a placeholder)
- `predicted_score_after`: estimated conflict score after applying the change
- `rationale`: plain-English explanation

Users can **accept**, **reject**, or **partially apply** recommendations. All decisions are written to the audit log.

---

## 9. Async Job Architecture

Heavy work (Stage 3 semantic + Stage 4 simulation) runs in Celery workers, not in the request path.

**Queues:**

| Queue | Workers | Tasks |
|---|---|---|
| `analysis` | 4 concurrent | Conflict detection, embedding computation |
| `simulation` | 2 concurrent | LLM routing simulation (rate-limited by API) |
| `embeddings` | 4 concurrent | Batch embedding updates |

**Why separate queues?** Simulation workers are intentionally limited to 2 to respect Anthropic API rate limits. Analysis workers can run higher concurrency since embedding calls are cheaper.

**Task lifecycle:**
```
status: pending → running → completed | failed

On failure: Celery retry with exponential backoff (3 retries, 60s base)
On permanent failure: analysis_run.status = "failed", notification dispatched
```

---

## 10. Data Models

### Core tables

| Table | Purpose |
|---|---|
| `organizations` | Top-level tenant |
| `environments` | dev / staging / prod scoped registry per org |
| `mcp_servers` | Named MCP server instances |
| `tools` | Registered tool definitions (with embedding vector) |
| `tool_versions` | Immutable version history with JSON diff |
| `conflicts` | Detected conflicts with evidence and status |
| `probe_queries` | Reusable probe queries per environment |
| `analysis_runs` | Metadata for each analysis execution |
| `recommendations` | Claude-generated fix proposals |
| `audit_log` | Immutable record of all state changes |

### Key schema decisions

- `tools.embedding` is `VECTOR(3072)` — matches `text-embedding-3-large` dimensions
- `tools.input_schema` is `JSONB` — allows structured querying without a fixed schema
- `conflicts.tool_ids` is `UUID[]` — supports N-way conflicts (not just pairs)
- `conflicts.evidence` is `JSONB` — stores similarity scores, probe IDs, routing splits in one column
- `analysis_runs.tool_set_snapshot` is `JSONB` — reproducibility: the exact tool set used is always stored

---

## 11. Authentication & Authorization

### Two auth modes

**JWT (user sessions):**
- `POST /v1/auth/login` → returns `access_token` (60min) + `refresh_token` (7 days)
- `Authorization: Bearer <token>` header

**API keys (CI/CD + programmatic):**
- Generated via `mtgs auth create-key` or API
- Stored as `SHA256(raw_key)` — raw key shown only once at creation
- `X-API-Key: <key>` header

### RBAC roles

| Role | Capabilities |
|---|---|
| `VIEWER` | Read-only access to registry, conflicts, reports |
| `EDITOR` | Register/update tools, manage probe queries |
| `APPROVER` | Approve pending tool registrations |
| `ADMIN` | Full access including environment policy configuration |

Roles are checked via `has_minimum_role(user.role, required_role)` — hierarchical (ADMIN ≥ APPROVER ≥ EDITOR ≥ VIEWER).

> **Note:** OIDC/SSO integration is planned for Phase 3. Current auth is JWT + API key only.

---

## 12. Observability

**Structured logging** via `structlog` — all logs are JSON with `request_id`, `env`, `version` fields. The `RequestIDMiddleware` generates and propagates a UUID per request.

**OpenTelemetry** instrumentation is configured via environment:
```
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
OTEL_SERVICE_NAME=mtgs-api
```

Traces cover:
- HTTP request spans (FastAPI auto-instrumentation)
- Database query spans (SQLAlchemy instrumentation)
- External API calls (Azure OpenAI, Azure Search, Anthropic)

**Health endpoints:**
- `GET /health` — shallow liveness check (always returns 200 if process is up)
- `GET /readiness` — deep check: database + Redis connectivity
- `GET /v1/environments/{id}/health` — governance health score (0–100)

---

## 13. Scalability Considerations

**Registry up to 10,000 tools:** Azure AI Search handles ANN at this scale with sub-second latency. No architectural changes needed.

**Embedding cache:** 24h Redis TTL means most tools never re-embed on read paths. Only definition changes trigger re-embedding.

**Probe query parallelism:** `asyncio.gather()` in `AnalysisOrchestrator._generate_probes()` runs probe generation and adversarial queries concurrently.

**Celery horizontal scaling:** Workers are stateless. Add worker replicas to increase analysis throughput linearly.

**Database connection pooling:** `pool_size=10`, `max_overflow=20` per API instance. For > 3 API replicas, add a PgBouncer sidecar.

**Future (Phase 4):** ANN index tuning (IVFFlat `lists` parameter scales with `sqrt(n_tools)`), read replicas for the registry API, and self-hosted LLM mode for air-gapped deployments.
