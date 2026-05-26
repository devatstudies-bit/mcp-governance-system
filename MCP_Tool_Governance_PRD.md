# MCP Tool Governance System (MTGS)
### Production-Grade Application Document v1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Why This Matters for Enterprises](#3-why-this-matters-for-enterprises)
4. [System Overview](#4-system-overview)
5. [Core Concepts & Terminology](#5-core-concepts--terminology)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [System Architecture](#8-system-architecture)
9. [Data Models](#9-data-models)
10. [API Specification](#10-api-specification)
11. [Core Engine Design](#11-core-engine-design)
12. [UI/UX Specification](#12-uiux-specification)
13. [Integration Contracts](#13-integration-contracts)
14. [Security & Access Control](#14-security--access-control)
15. [Evaluation & Benchmarking](#15-evaluation--benchmarking)
16. [Deployment Architecture](#16-deployment-architecture)
17. [Implementation Roadmap](#17-implementation-roadmap)
18. [Open Questions & Decision Log](#18-open-questions--decision-log)

---

## 1. Executive Summary

**Product Name:** MCP Tool Governance System (MTGS)

**One-Line Description:** A governance layer that statically and semantically analyzes MCP tool registries to detect conflicts, predict LLM routing failures, and recommend definition improvements before deployment.

**Core Value Proposition:**
As enterprises deploy MCP servers at scale — spanning dozens of teams and hundreds of tools — the risk of LLM tool selection failures grows non-linearly. MTGS acts as a "linter + impact analyzer" for the MCP tool layer, catching ambiguity, overlap, and routing risk before tools reach production. It integrates into CI/CD pipelines, provides a governance dashboard, and maintains an audit trail of tool definition changes.

**Target Users:**
- Platform/AI infrastructure teams managing enterprise MCP servers
- Developers registering new tools via CLI or API
- AI Governance leads auditing tool quality and change impact

---

## 2. Problem Statement

### 2.1 The Core Issue

MCP (Model Context Protocol) tools are described to LLMs through a combination of:
- Tool **name** (e.g., `create_ticket`)
- Tool **description** (natural language, parsed by the LLM)
- Tool **input schema** (parameters, types, required fields)

When an LLM receives a user request, it uses these three signals to select which tool to invoke. This selection process is **probabilistic and sensitive to lexical and semantic similarity** across tool definitions.

### 2.2 Failure Modes

| Failure Mode | Example | Impact |
|---|---|---|
| **Name collision** | `send_message` exists in both a Slack MCP and an Email MCP | LLM picks wrong channel |
| **Semantic overlap** | `create_task` vs `add_todo` — different systems, same intent | Non-deterministic routing |
| **Description drift** | A tool's behavior changed but description wasn't updated | Stale routing signals |
| **Parameter ambiguity** | Two tools share parameter name `user_id` with different semantics | Silent data corruption |
| **Scope bleed** | A general-purpose tool's description accidentally matches narrow intents | Overfitting to wrong tool |
| **Superseded tools** | Old tool kept active after new one added, both respond to same intent | Duplicate side effects |

### 2.3 Why It's Hard to Detect Manually

- Tool definitions are authored by different teams with no central review process
- Conflicts may be **semantic** (not syntactic) — standard JSON schema validation won't catch them
- Impact is **contextual** — whether a conflict matters depends on the full set of active tools
- LLM routing behavior is **emergent** — you cannot predict it from a single tool's definition in isolation

---

## 3. Why This Matters for Enterprises

### 3.1 Scale of the Problem

| Company Size | Estimated MCP Tools | Teams Contributing | Avg New Tools/Month |
|---|---|---|---|
| Mid-size (500–2000 employees) | 30–80 | 5–15 | 4–8 |
| Large (2000–10000) | 100–300 | 20–60 | 15–30 |
| Enterprise (10000+) | 300–1000+ | 60–200+ | 50–100+ |

At 200+ tools, the probability of at least one ambiguous tool pair approaches near-certainty without active governance.

### 3.2 Business Risk

- **Silent failures:** LLMs don't throw errors when routing to the wrong tool — they succeed silently with wrong outcomes (e.g., creating a Jira ticket when the user wanted a Salesforce task)
- **Compliance risk:** In regulated industries (finance, healthcare), a tool routing to the wrong system can trigger audit violations
- **Cost amplification:** Wrong tool calls in agentic flows create cascading failures that are expensive to debug and reverse
- **Trust erosion:** Users and business stakeholders lose confidence in AI agents when they behave inconsistently

### 3.3 Why This Is a Gap Today

There is no existing standard tooling for MCP tool governance. The MCP specification defines the protocol but not the governance layer above it. MTGS fills this gap and positions the enterprise to scale MCP adoption safely.

---

## 4. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     MCP Tool Governance System                      │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────────┐  │
│  │  Tool        │   │  Conflict    │   │  Recommendation        │  │
│  │  Registry    │──▶│  Detection   │──▶│  Engine                │  │
│  │  (Source of  │   │  Engine      │   │  (Rewrites + Scoring)  │  │
│  │   Truth)     │   │              │   │                        │  │
│  └──────────────┘   └──────┬───────┘   └────────────────────────┘  │
│         ▲                  │                        │               │
│         │           ┌──────▼───────┐                │               │
│         │           │  Impact      │                │               │
│  ┌──────┴───────┐   │  Simulator   │                │               │
│  │  Ingestion   │   │  (LLM-based  │                │               │
│  │  API / CLI   │   │   routing    │                │               │
│  │  / CI Hook   │   │   tests)     │                │               │
│  └──────────────┘   └──────┬───────┘                │               │
│                             │                        │               │
│                    ┌────────▼────────────────────────▼─────────┐    │
│                    │         Governance Dashboard               │    │
│                    │   (Conflict map, audit log, approvals)     │    │
│                    └───────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.1 Key Subsystems

| Subsystem | Responsibility |
|---|---|
| **Tool Registry** | Persistent store of all registered tools, versions, and metadata |
| **Conflict Detection Engine** | Multi-layered analysis: lexical, semantic, schema, behavioral |
| **Impact Simulator** | Runs LLM routing tests across probe queries to quantify routing risk |
| **Recommendation Engine** | Generates improved tool definitions with explanations |
| **Ingestion Layer** | CLI, REST API, CI/CD webhook for registering tools |
| **Governance Dashboard** | Web UI for visualizing and managing conflict state |
| **Audit & Notification Layer** | Logs all changes, alerts on high-severity conflicts |

---

## 5. Core Concepts & Terminology

| Term | Definition |
|---|---|
| **Tool** | An MCP tool definition: `{name, description, inputSchema}` |
| **Tool Registry** | The authoritative catalog of all active tools in an environment (dev/staging/prod) |
| **Conflict** | A detected condition where two or more tools create ambiguity for LLM routing |
| **Conflict Score** | A 0–100 numerical severity score for a conflict pair or group |
| **Probe Query** | A synthetic or real natural language query used to simulate LLM tool selection |
| **Routing Test** | Sending a probe query to an LLM with the full tool set and observing which tool is selected |
| **Impact Report** | Analysis of how adding/modifying a tool changes routing behavior across probe queries |
| **Governance Policy** | Organization-defined rules (e.g., "no two tools may have cosine similarity > 0.85") |
| **Environment** | A scoped registry (dev / staging / prod) with independent tool sets |
| **Fingerprint** | A normalized embedding vector representing a tool's semantic intent |

---

## 6. Functional Requirements

### 6.1 Tool Registry Management

**FR-REG-001:** The system shall maintain a versioned registry of all MCP tool definitions per environment (dev, staging, prod).

**FR-REG-002:** Each tool entry shall store: name, description, inputSchema, server_id, owner_team, version, created_at, updated_at, status (active/deprecated/flagged).

**FR-REG-003:** The system shall support bulk import of tools from a running MCP server via its `tools/list` endpoint.

**FR-REG-004:** The system shall track a full version history for every tool definition with diff visibility.

**FR-REG-005:** Tools shall be associated with a named MCP server and a team/owner for access control purposes.

### 6.2 Conflict Detection

**FR-CON-001:** On registration of any new tool (or update to an existing one), the system shall automatically run a full conflict analysis against all active tools in the same environment.

**FR-CON-002:** The system shall detect the following conflict types:
- **EXACT_NAME:** Two tools share an identical name across different servers
- **SIMILAR_NAME:** Tool names have edit distance ≤ 2 or share all tokens
- **SEMANTIC_OVERLAP:** Embedding cosine similarity between descriptions exceeds configurable threshold (default: 0.80)
- **SCHEMA_COLLISION:** Two tools share a parameter name with different types or semantics
- **INTENT_AMBIGUITY:** LLM routing simulation shows >30% routing split between two tools for the same probe queries
- **SCOPE_BLEED:** A tool's description matches probe queries clearly intended for a different, existing tool
- **SUPERSEDED:** A new tool's description subsumes an older tool's scope entirely

**FR-CON-003:** Each detected conflict shall be assigned a severity level: CRITICAL, HIGH, MEDIUM, LOW, INFO.

| Severity | Trigger Conditions |
|---|---|
| CRITICAL | Exact name collision across servers; Routing ambiguity >60% on 5+ probes |
| HIGH | Semantic similarity >0.90; Intent ambiguity >40% |
| MEDIUM | Semantic similarity 0.80–0.90; Similar names; Schema collision |
| LOW | Semantic similarity 0.70–0.80; Scope bleed on ≤2 probes |
| INFO | Minor description similarity; Advisory only |

**FR-CON-004:** Conflicts shall be persisted with: conflict_id, type, severity, tool_ids_involved, detection_timestamp, evidence (similarity scores, affected probe queries), resolution_status.

**FR-CON-005:** The system shall re-evaluate all existing conflicts when any tool in the registry is modified or removed.

### 6.3 Impact Simulation

**FR-SIM-001:** When a new tool is proposed for registration, the system shall run an impact simulation before committing it to the registry.

**FR-SIM-002:** The impact simulation shall:
1. Take a set of probe queries (system-generated + user-provided)
2. Run LLM tool selection with the current tool set (baseline)
3. Run LLM tool selection with the proposed new tool added (candidate)
4. Diff the routing outcomes and report any routing shifts

**FR-SIM-003:** The system shall maintain a library of probe queries that can be:
- Auto-generated by the system based on existing tool descriptions
- Manually added by team members
- Imported from production logs (user queries that previously routed to specific tools)

**FR-SIM-004:** The impact report shall include:
- Routing shift matrix (which existing tools lose/gain routing for which probe queries)
- Risk score: percentage of probe queries that changed routing outcome
- A list of "at-risk" existing tools whose routing share decreased by >10%

**FR-SIM-005:** The simulation shall be configurable: number of probe queries (default: 50), LLM model to use, number of routing trials per query (for stability estimation), temperature.

### 6.4 Recommendation Engine

**FR-REC-001:** For any detected conflict, the system shall generate concrete recommendations to resolve it.

**FR-REC-002:** Recommendations shall cover:
- **Rename suggestion:** Alternative tool name that is more distinct
- **Description rewrite:** Revised description that reduces semantic overlap while preserving tool behavior
- **Scope narrowing:** Suggestions to add explicit exclusions to ambiguous descriptions (e.g., "Use this tool only when X; do not use for Y")
- **Schema clarification:** Parameter renaming or documentation improvements
- **Deprecation advisory:** When a tool is fully superseded, recommend deprecation with migration path

**FR-REC-003:** Each recommendation shall include:
- The specific proposed change (diff format)
- The predicted conflict score after applying the change
- The rationale in plain English

**FR-REC-004:** Users shall be able to accept, reject, or partially apply recommendations. Accepted recommendations shall be tracked in the audit log.

### 6.5 CI/CD Integration

**FR-CI-001:** The system shall expose a webhook endpoint that accepts a tool definition payload and returns a pass/fail result with a full conflict report — suitable for use as a CI/CD gate.

**FR-CI-002:** The CI gate shall be configurable with a policy that defines the minimum severity level that causes a pipeline failure (e.g., "fail on CRITICAL or HIGH").

**FR-CI-003:** The system shall provide a CLI tool (`mtgs check`) that:
- Accepts a tool definition file (JSON or YAML)
- Runs the full conflict check against a named environment
- Outputs a structured report (human-readable and JSON)
- Exits with code 0 (pass) or 1 (fail) based on configured policy

**FR-CI-004:** The system shall support GitHub Actions, GitLab CI, and Jenkins via native plugins or generic webhook.

### 6.6 Governance Dashboard

**FR-DASH-001:** The dashboard shall provide a real-time view of the tool registry for each environment.

**FR-DASH-002:** The dashboard shall include a **Conflict Map**: a visual graph where nodes are tools, edges are conflicts, edge color/thickness encodes severity.

**FR-DASH-003:** The dashboard shall display an active conflict queue with filter/sort by severity, server, team, and conflict type.

**FR-DASH-004:** The dashboard shall support an **approval workflow**: high-severity tool registrations require explicit approval from a designated reviewer before being promoted to the active registry.

**FR-DASH-005:** The dashboard shall display a **Health Score** per environment: a 0–100 composite metric reflecting overall conflict state, coverage of probe queries, and governance policy compliance.

**FR-DASH-006:** The dashboard shall include a full **audit log** of all tool registrations, modifications, deletions, conflict detections, and approvals.

### 6.7 Notification & Alerting

**FR-ALERT-001:** The system shall send notifications (email, Slack, PagerDuty) when:
- A CRITICAL or HIGH conflict is detected
- A tool registration is blocked by governance policy
- A tool's conflict status changes (resolved, regressed)
- The environment health score drops below a configurable threshold

**FR-ALERT-002:** Notifications shall be routable to the owning team of the affected tools.

---

## 7. Non-Functional Requirements

### 7.1 Performance

| Metric | Requirement |
|---|---|
| Conflict analysis latency (new tool, registry ≤500 tools) | < 10 seconds end-to-end |
| Impact simulation (50 probe queries, 500-tool registry) | < 60 seconds |
| Dashboard load time | < 2 seconds |
| CI webhook response (conflict check only, no simulation) | < 5 seconds |
| Registry API read latency (p99) | < 200ms |

### 7.2 Scalability

- The system shall support registries of up to 10,000 tools per environment without architectural changes
- Embedding computation shall be batched and cached; re-embedding occurs only on tool definition changes
- Impact simulation shall support parallel probe query execution

### 7.3 Reliability

- The conflict detection engine shall be idempotent: re-running analysis on the same inputs always produces the same result
- The system shall maintain 99.9% uptime SLA for the registry API and CI webhook
- All LLM API calls shall have retry logic with exponential backoff and configurable fallback behavior

### 7.4 Accuracy

- Semantic similarity detection shall achieve >90% precision on a labeled conflict benchmark dataset (see Section 15)
- Impact simulation routing results shall be stable: running the same simulation twice should produce routing outcomes that differ by <5% across probe queries

### 7.5 Auditability

- All state changes to the registry shall be logged with actor, timestamp, and before/after diff
- Conflict detection results shall be reproducible: the system shall store the exact inputs (tool set snapshot, probe queries, LLM model/version) used for each analysis run

---

## 8. System Architecture

### 8.1 Component Diagram

```
                          ┌───────────────────────────────────────┐
                          │           Client Layer                 │
                          │  Web Dashboard │ CLI (mtgs) │ CI Hook  │
                          └───────────┬───────────────────────────┘
                                      │ HTTPS / REST
                          ┌───────────▼───────────────────────────┐
                          │           API Gateway (FastAPI)        │
                          │   Auth (JWT/API Key) │ Rate Limiting   │
                          └───┬───────────┬───────────────┬────────┘
                              │           │               │
                   ┌──────────▼──┐  ┌─────▼──────┐  ┌───▼──────────┐
                   │  Registry   │  │  Analysis  │  │  Simulation  │
                   │  Service    │  │  Service   │  │  Service     │
                   └──────┬──────┘  └─────┬──────┘  └──────┬───────┘
                          │               │                  │
              ┌───────────▼───────────────▼──────────────────▼──────┐
              │                   Message Queue (Redis/SQS)          │
              │         (async job dispatch for heavy analysis)       │
              └──────────────────────────┬──────────────────────────┘
                                         │
              ┌──────────────────────────▼──────────────────────────┐
              │                    Worker Pool                        │
              │  ┌─────────────────────┐  ┌────────────────────────┐│
              │  │  Conflict Detection │  │  Impact Simulation     ││
              │  │  Worker             │  │  Worker                ││
              │  └──────────┬──────────┘  └──────────┬─────────────┘│
              └─────────────┼────────────────────────┼──────────────┘
                            │                        │
              ┌─────────────▼──────────┐  ┌──────────▼─────────────┐
              │  Embedding Service     │  │  LLM Routing Service   │
              │  (text-embedding-3-    │  │  (Claude Sonnet via    │
              │   large or equivalent) │  │   Anthropic API)       │
              └─────────────┬──────────┘  └──────────┬─────────────┘
                            │                        │
              ┌─────────────▼──────────────────────────────────────┐
              │                  Data Layer                          │
              │  PostgreSQL (registry, conflicts, audit)             │
              │  PgVector (tool fingerprint embeddings)              │
              │  Redis (cache, job queue)                            │
              │  S3/Blob (analysis artifacts, snapshots)             │
              └────────────────────────────────────────────────────┘
```

### 8.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| API Framework | FastAPI (Python) | Async support, auto OpenAPI docs, type safety via Pydantic |
| Database | PostgreSQL 16 | Mature, ACID, native JSONB for schema storage |
| Vector Search | pgvector extension | Co-located with registry DB, no separate vector DB needed at scale ≤10K tools |
| Cache / Queue | Redis | Job queue (Celery), embedding cache, session cache |
| Worker Framework | Celery + Redis broker | Reliable async job processing |
| Embeddings | OpenAI text-embedding-3-large or Claude (via Anthropic API) | State-of-the-art semantic similarity |
| LLM for Routing Simulation | Claude Sonnet (Anthropic API) | Strong tool-use capability for realistic routing simulation |
| LLM for Recommendations | Claude Sonnet (Anthropic API) | Strong instruction-following for definition rewrites |
| Frontend | React + TypeScript + Tailwind | Modern, maintainable, component-driven |
| Graph Visualization | D3.js or Sigma.js | For conflict map rendering |
| Auth | Auth0 / Okta (OIDC) + API keys | Enterprise SSO compatibility |
| CLI | Python + Click + Rich | Cross-platform, installable via pip |
| Container | Docker + Kubernetes | Standard enterprise deployment |
| CI/CD Plugins | GitHub Actions + GitLab CI templates | First-class integrations |
| Observability | OpenTelemetry → Datadog/Grafana | Traces, metrics, logs |

---

## 9. Data Models

### 9.1 Tool

```sql
CREATE TABLE tools (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id  UUID NOT NULL REFERENCES environments(id),
    server_id       UUID NOT NULL REFERENCES mcp_servers(id),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    input_schema    JSONB NOT NULL,
    owner_team_id   UUID REFERENCES teams(id),
    status          TEXT NOT NULL DEFAULT 'active',
        -- active | deprecated | flagged | pending_approval
    version         INTEGER NOT NULL DEFAULT 1,
    embedding       VECTOR(3072),  -- text-embedding-3-large dimension
    embedding_model TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      UUID REFERENCES users(id),
    UNIQUE(environment_id, server_id, name)
);

CREATE INDEX ON tools USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### 9.2 Tool Version History

```sql
CREATE TABLE tool_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id         UUID NOT NULL REFERENCES tools(id),
    version         INTEGER NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    input_schema    JSONB NOT NULL,
    changed_by      UUID REFERENCES users(id),
    change_reason   TEXT,
    diff            JSONB,  -- JSON patch format
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 9.3 Conflict

```sql
CREATE TABLE conflicts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id      UUID NOT NULL REFERENCES environments(id),
    conflict_type       TEXT NOT NULL,
        -- EXACT_NAME | SIMILAR_NAME | SEMANTIC_OVERLAP | SCHEMA_COLLISION |
        -- INTENT_AMBIGUITY | SCOPE_BLEED | SUPERSEDED
    severity            TEXT NOT NULL,
        -- CRITICAL | HIGH | MEDIUM | LOW | INFO
    status              TEXT NOT NULL DEFAULT 'open',
        -- open | acknowledged | resolved | suppressed
    tool_ids            UUID[] NOT NULL,  -- 2+ tool IDs involved
    conflict_score      NUMERIC(5,2),     -- 0.00–100.00
    evidence            JSONB NOT NULL,
        -- {similarity_score, affected_probe_ids, routing_split, schema_diff, ...}
    analysis_run_id     UUID REFERENCES analysis_runs(id),
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         UUID REFERENCES users(id),
    resolution_notes    TEXT
);
```

### 9.4 Probe Query

```sql
CREATE TABLE probe_queries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id  UUID NOT NULL REFERENCES environments(id),
    query_text      TEXT NOT NULL,
    source          TEXT NOT NULL,  -- 'system_generated' | 'manual' | 'production_log'
    expected_tool_id UUID REFERENCES tools(id),  -- optional ground truth
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      UUID REFERENCES users(id),
    is_active       BOOLEAN NOT NULL DEFAULT true
);
```

### 9.5 Analysis Run

```sql
CREATE TABLE analysis_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id      UUID NOT NULL REFERENCES environments(id),
    trigger             TEXT NOT NULL,
        -- 'tool_registration' | 'scheduled' | 'manual' | 'ci_webhook'
    trigger_tool_id     UUID REFERENCES tools(id),  -- for registration-triggered runs
    tool_set_snapshot   JSONB NOT NULL,  -- full snapshot of tool registry at run time
    probe_query_ids     UUID[],
    llm_model           TEXT NOT NULL,
    embedding_model     TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | completed | failed
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    conflict_ids        UUID[],
    risk_score          NUMERIC(5,2),
    routing_shift_pct   NUMERIC(5,2),
    report_url          TEXT
);
```

### 9.6 Recommendation

```sql
CREATE TABLE recommendations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conflict_id         UUID NOT NULL REFERENCES conflicts(id),
    recommendation_type TEXT NOT NULL,
        -- RENAME | DESCRIPTION_REWRITE | SCOPE_NARROWING | SCHEMA_CLARIFICATION | DEPRECATE
    target_tool_id      UUID NOT NULL REFERENCES tools(id),
    proposed_change     JSONB NOT NULL,
        -- {field: 'description', before: '...', after: '...'}
    predicted_score_after NUMERIC(5,2),
    rationale           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
        -- pending | accepted | rejected | partially_applied
    reviewed_by         UUID REFERENCES users(id),
    reviewed_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 9.7 Environment & MCP Server

```sql
CREATE TABLE environments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL REFERENCES organizations(id),
    name        TEXT NOT NULL,  -- 'dev' | 'staging' | 'prod'
    policy      JSONB NOT NULL DEFAULT '{}',
        -- {max_severity_to_block: "HIGH", auto_approve_below: "LOW", ...}
    UNIQUE(org_id, name)
);

CREATE TABLE mcp_servers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    environment_id  UUID NOT NULL REFERENCES environments(id),
    name            TEXT NOT NULL,
    url             TEXT,
    owner_team_id   UUID REFERENCES teams(id),
    sync_enabled    BOOLEAN DEFAULT false,
    last_synced_at  TIMESTAMPTZ
);
```

---

## 10. API Specification

### 10.1 Base URL

```
https://api.mtgs.yourdomain.com/v1
```

### 10.2 Authentication

All endpoints require one of:
- `Authorization: Bearer <JWT>` (user session)
- `X-API-Key: <api_key>` (CI/CD and programmatic access)

### 10.3 Core Endpoints

#### Tool Registry

```
POST   /environments/{env_id}/tools
       Register a new tool. Triggers async conflict analysis.
       Body: { name, description, input_schema, server_id, owner_team_id }
       Response: { tool_id, status, analysis_run_id }

GET    /environments/{env_id}/tools
       List all tools. Supports filters: server_id, status, team_id.

GET    /environments/{env_id}/tools/{tool_id}
       Get tool with current conflict summary.

PUT    /environments/{env_id}/tools/{tool_id}
       Update a tool definition. Triggers re-analysis.

DELETE /environments/{env_id}/tools/{tool_id}
       Deprecate (soft delete) a tool.

GET    /environments/{env_id}/tools/{tool_id}/history
       Get version history with diffs.
```

#### Conflict Analysis

```
POST   /environments/{env_id}/analyze
       Trigger a full environment analysis run.
       Body: { probe_count: 50, model: "claude-sonnet-4" }
       Response: { analysis_run_id }

GET    /environments/{env_id}/analysis-runs/{run_id}
       Get analysis run status and results.

GET    /environments/{env_id}/conflicts
       List conflicts. Filter by: severity, status, tool_id, type.

GET    /environments/{env_id}/conflicts/{conflict_id}
       Get conflict detail with evidence and recommendations.

PATCH  /environments/{env_id}/conflicts/{conflict_id}
       Update conflict status (acknowledge, suppress, resolve).
       Body: { status, resolution_notes }
```

#### Pre-Registration Check (CI/CD Gate)

```
POST   /environments/{env_id}/tools/check
       Dry-run conflict check for a candidate tool WITHOUT registering it.
       Body: { name, description, input_schema, server_id }
       Response:
       {
         passed: boolean,
         conflicts: [...],
         impact_summary: {
           routing_shift_pct: number,
           at_risk_tools: [...],
           probe_results: [...]
         },
         recommendations: [...],
         analysis_run_id: string
       }
```

#### Recommendations

```
GET    /conflicts/{conflict_id}/recommendations
       Get all recommendations for a conflict.

POST   /recommendations/{rec_id}/accept
       Accept and optionally apply a recommendation.
       Body: { apply: boolean }

POST   /recommendations/{rec_id}/reject
       Body: { reason: string }
```

#### Probe Queries

```
GET    /environments/{env_id}/probe-queries
POST   /environments/{env_id}/probe-queries
       Body: { query_text, expected_tool_id? }

POST   /environments/{env_id}/probe-queries/generate
       Auto-generate probe queries from current tool descriptions.
       Body: { count: 50 }

DELETE /environments/{env_id}/probe-queries/{query_id}
```

#### Health & Metrics

```
GET    /environments/{env_id}/health
       Response: {
         score: 0–100,
         active_tools: number,
         open_conflicts: { CRITICAL, HIGH, MEDIUM, LOW, INFO },
         last_analysis: timestamp,
         coverage: { probe_queries: number, tools_with_probes_pct: number }
       }

GET    /environments/{env_id}/metrics
       Time-series data for health score, conflict counts, routing shift trends.
```

### 10.4 Webhook (CI/CD Gate)

**Endpoint:** `POST /webhooks/ci-check`

**Headers:** `X-API-Key: <key>`, `X-Environment: prod`

**Request Body:**
```json
{
  "tool": {
    "name": "create_salesforce_task",
    "description": "Creates a new task in Salesforce CRM...",
    "input_schema": { ... }
  },
  "server_id": "abc-123",
  "policy_override": null
}
```

**Response:**
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
  "warnings": [...],
  "analysis_run_id": "run_xyz",
  "dashboard_url": "https://mtgs.yourdomain.com/runs/run_xyz"
}
```

---

## 11. Core Engine Design

### 11.1 Conflict Detection Pipeline

The analysis pipeline runs in stages, from cheapest to most expensive:

```
Stage 1: Lexical Analysis (< 100ms)
  ├── Exact name match check (O(1) hash lookup)
  ├── Edit distance name similarity (Levenshtein, threshold ≤2)
  └── Token overlap in name (Jaccard similarity on tokenized names)

Stage 2: Schema Analysis (< 200ms)
  ├── Parameter name intersection across tool pairs
  ├── Type conflict detection for shared param names
  └── Required field overlap analysis

Stage 3: Semantic Analysis (1–3s, uses embeddings)
  ├── Compute embedding for new tool description
  ├── ANN search in pgvector for top-K nearest tools (K=20)
  ├── Compute exact cosine similarity for top-K candidates
  └── Flag pairs above threshold (default: 0.80)

Stage 4: Behavioral Simulation (10–60s, uses LLM)
  ├── For pairs flagged in Stage 3, run targeted routing tests
  ├── Select 10–20 probe queries most relevant to conflicting tools
  ├── Run LLM tool selection with full tool set (3 trials per query)
  ├── Measure routing split between conflicting tools
  └── Compute final conflict score and severity
```

**Short-circuit logic:** Stages 1 and 2 are always run. Stage 3 is skipped if Stage 1 already produces a CRITICAL finding (exact name match). Stage 4 is only run for pairs flagged by Stage 3, keeping overall latency manageable.

### 11.2 Embedding Strategy

```python
class ToolFingerprinter:
    """
    Generates a semantic fingerprint for a tool.
    Combines name, description, and schema signal into one embedding.
    """
    def build_fingerprint_text(self, tool: Tool) -> str:
        # Structured prompt engineered to maximize semantic differentiation
        param_summary = self._summarize_schema(tool.input_schema)
        return f"""Tool name: {tool.name}
Purpose: {tool.description}
Parameters accepted: {param_summary}
Server context: {tool.server.name}"""

    def _summarize_schema(self, schema: dict) -> str:
        props = schema.get("properties", {})
        return ", ".join([
            f"{k} ({v.get('type','any')}): {v.get('description','')}"
            for k, v in props.items()
        ])
```

**Key design decisions:**
- Embed a **structured composite** of name + description + schema summary, not just description. This prevents false positives from tools with similar descriptions but entirely different parameter sets.
- Store embeddings in pgvector for ANN queries. Re-embed only on definition change.
- Use the same embedding model across all tools in a registry to ensure comparability.
- Cache embeddings keyed on `SHA256(fingerprint_text + model_version)`.

### 11.3 Impact Simulation Design

```python
class ImpactSimulator:
    """
    Simulates LLM tool routing with and without the candidate tool
    to measure routing shift.
    """
    async def simulate(
        self,
        candidate_tool: ToolDefinition,
        existing_tools: list[ToolDefinition],
        probe_queries: list[ProbeQuery],
        trials: int = 3
    ) -> ImpactReport:
        baseline_tools = existing_tools
        candidate_tools = existing_tools + [candidate_tool]

        baseline_results = await self._run_routing_trials(
            baseline_tools, probe_queries, trials)
        candidate_results = await self._run_routing_trials(
            candidate_tools, probe_queries, trials)

        return self._diff_results(baseline_results, candidate_results)

    async def _run_routing_trials(
        self, tools, probe_queries, trials
    ) -> dict[str, Counter]:
        """
        For each probe query, run 'trials' LLM calls and record
        which tool was selected each time. Returns routing distribution.
        """
        results = {}
        for query in probe_queries:
            counter = Counter()
            for _ in range(trials):
                selected = await self._llm_tool_select(tools, query.text)
                counter[selected] += 1
            results[query.id] = counter
        return results
```

**LLM Prompt for Routing Simulation:**

```
You are an AI assistant with access to the following tools.
Given the user's request, respond ONLY with the name of the single best tool to use.
Do not call the tool. Do not explain. Output only the tool name.

Available tools:
{tool_definitions_formatted}

User request: {probe_query}

Best tool name:
```

This minimal prompt isolates tool selection from execution, giving clean, auditable routing decisions.

### 11.4 Recommendation Engine Design

```python
class RecommendationEngine:
    """
    Uses Claude to generate conflict-resolution recommendations.
    """
    async def generate(
        self,
        conflict: Conflict,
        tools: list[Tool]
    ) -> list[Recommendation]:
        prompt = self._build_recommendation_prompt(conflict, tools)
        response = await claude_api.complete(prompt)
        return self._parse_recommendations(response)

    def _build_recommendation_prompt(self, conflict, tools):
        return f"""
You are an expert in MCP tool design and LLM tool routing.

CONFLICT DETECTED:
Type: {conflict.conflict_type}
Severity: {conflict.severity}
Evidence: {conflict.evidence}

CONFLICTING TOOLS:
{self._format_tools(tools)}

Your task: Generate specific, actionable recommendations to resolve this conflict.
For each recommendation, provide:
1. recommendation_type: one of [RENAME, DESCRIPTION_REWRITE, SCOPE_NARROWING, SCHEMA_CLARIFICATION, DEPRECATE]
2. target_tool: which tool to change
3. proposed_change: the exact before/after
4. rationale: why this resolves the conflict
5. predicted_improvement: estimated % reduction in conflict score

Respond in JSON format only. Be specific — provide actual rewritten text, not placeholders.
"""
```

### 11.5 Probe Query Auto-Generation

```python
class ProbeQueryGenerator:
    """
    Generates diverse, realistic probe queries for a tool set.
    Uses Claude to generate queries that stress-test tool selection.
    """
    async def generate_for_tool(self, tool: Tool, count: int = 10) -> list[str]:
        prompt = f"""
Generate {count} diverse natural language user requests that would logically cause
an AI assistant to use this tool:

Tool name: {tool.name}
Description: {tool.description}

Requirements:
- Vary phrasing, formality, and specificity
- Include edge cases and ambiguous phrasings
- Some should be highly specific, some vague
- Avoid using the tool name literally in the query

Output as a JSON array of strings only.
"""
        ...

    async def generate_adversarial(
        self, tool_a: Tool, tool_b: Tool, count: int = 10
    ) -> list[str]:
        """Generates queries that are maximally ambiguous between two tools."""
        ...
```

---

## 12. UI/UX Specification

### 12.1 Pages & Key Views

#### Dashboard Home
- Environment health score (large prominent metric, 0–100)
- Active conflicts breakdown by severity (stacked bar or donut)
- Recent activity feed (last 10 registrations, detections, resolutions)
- Quick action: "Check a tool before registering"

#### Tool Registry View
- Table with columns: Name, Server, Team, Status, Last Updated, Conflict Count
- Filter by: server, team, status, conflict severity
- Row click → tool detail panel (description, schema, active conflicts, version history)
- "Register New Tool" button → inline form or modal

#### Conflict Map
- Force-directed graph: nodes = tools, edges = conflicts
- Edge color: RED (CRITICAL), ORANGE (HIGH), YELLOW (MEDIUM), BLUE (LOW)
- Node size proportional to number of conflict edges
- Click node → highlight all conflicts for that tool
- Click edge → open conflict detail panel
- Filter: by severity, server, team
- Toggle: show/hide resolved conflicts

#### Conflict Queue
- List view of open conflicts, sorted by severity then age
- For each: conflict type badge, severity badge, tools involved (with links), detected timestamp, evidence summary, assigned reviewer
- Bulk actions: acknowledge, assign, suppress
- Click → conflict detail with full evidence, routing simulation results, recommendations

#### Tool Registration Wizard (CI-equivalent UI)
- Step 1: Paste or form-fill tool definition (name, description, schema)
- Step 2: Run check → show live progress (stage indicators)
- Step 3: Results page:
  - PASS / FAIL badge
  - Conflict findings (with expand for evidence)
  - Impact matrix: probe queries that would change routing
  - Recommendations panel
- Step 4: Accept recommendations → rerun check → register if passing

#### Analysis Run Detail
- Run metadata (trigger, timestamp, model, tool set size)
- Probe query results table: query text | baseline tool | candidate tool | changed? (Y/N)
- Routing shift summary
- Conflict list detected in this run
- Full report download (JSON/PDF)

#### Audit Log
- Filterable timeline: tool registrations, updates, deletions, conflict detections, approvals, recommendation acceptances
- Actor, timestamp, diff viewer for tool changes

### 12.2 CLI Reference (`mtgs`)

```bash
# Register a tool
mtgs tools register \
  --file tool.json \
  --server my-crm-mcp \
  --env prod

# Check (dry run) a tool before registering
mtgs tools check \
  --file tool.json \
  --env prod \
  --output report.json

# List conflicts
mtgs conflicts list --env prod --severity HIGH,CRITICAL

# Run full analysis
mtgs analyze --env prod --probes 100

# Pull current registry health
mtgs health --env prod

# Sync tools from a live MCP server
mtgs servers sync --server-url http://my-mcp-server:8080 --env dev

# Generate probe queries for a tool
mtgs probes generate --tool-id abc-123 --count 20
```

---

## 13. Integration Contracts

### 13.1 GitHub Actions Integration

```yaml
# .github/workflows/mcp-tool-governance.yml
name: MCP Tool Governance Check

on:
  pull_request:
    paths:
      - 'mcp-tools/**/*.json'

jobs:
  check-tools:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install MTGS CLI
        run: pip install mtgs-cli

      - name: Check new/modified tool definitions
        env:
          MTGS_API_KEY: ${{ secrets.MTGS_API_KEY }}
          MTGS_API_URL: ${{ secrets.MTGS_API_URL }}
        run: |
          for file in $(git diff --name-only origin/main HEAD -- 'mcp-tools/*.json'); do
            mtgs tools check --file $file --env prod --fail-on HIGH
          done

      - name: Comment PR with results
        if: always()
        uses: mtgs/pr-comment-action@v1
        with:
          report-path: mtgs-report.json
```

### 13.2 MCP Server Sync Contract

MTGS can pull tool definitions directly from a running MCP server:

```http
GET http://your-mcp-server/tools HTTP/1.1
Accept: application/json
```

Expected response (standard MCP `tools/list` format):
```json
{
  "tools": [
    {
      "name": "create_ticket",
      "description": "...",
      "inputSchema": { ... }
    }
  ]
}
```

MTGS syncs on a configurable schedule (default: hourly for prod, on-demand for dev) and diffs against its registry to detect definition drift.

### 13.3 Audit Log Export Contract

MTGS exposes audit logs in OpenTelemetry-compatible format for SIEM integration:

```json
{
  "timestamp": "2025-01-15T10:23:45Z",
  "event_type": "tool.conflict_detected",
  "severity": "HIGH",
  "actor": "ci-webhook",
  "environment": "prod",
  "tool_ids": ["uuid-1", "uuid-2"],
  "conflict_type": "SEMANTIC_OVERLAP",
  "conflict_score": 88.4,
  "metadata": { ... }
}
```

---

## 14. Security & Access Control

### 14.1 Role-Based Access Control (RBAC)

| Role | Capabilities |
|---|---|
| **Viewer** | Read-only access to registry, conflicts, and reports |
| **Developer** | Register tools, run checks, view own team's tools and conflicts |
| **Reviewer** | All Developer capabilities + approve/reject flagged tool registrations |
| **Admin** | Full access + manage environments, policies, users, API keys |
| **CI Agent** | API key–based; can run checks and register tools only (no dashboard access) |

### 14.2 Data Security

- All API communication over TLS 1.3
- Tool definitions and descriptions treated as potentially sensitive; stored encrypted at rest (AES-256)
- LLM API calls made via backend (never expose API keys to frontend)
- API keys are hashed before storage (bcrypt); shown once at creation
- Multi-tenant: organizations are strictly isolated at the database row level via `org_id` scoping

### 14.3 LLM Privacy Considerations

- Tool descriptions sent to LLM APIs for simulation may contain internal business logic. Enterprises must configure MTGS with an appropriate LLM endpoint (Anthropic's API with DPA, Azure OpenAI, or self-hosted models)
- A **self-hosted LLM mode** is provided for air-gapped environments (lower accuracy, but zero data egress)
- All LLM prompts and responses are logged for auditability and stored within the org's data boundary

---

## 15. Evaluation & Benchmarking

### 15.1 Conflict Detection Accuracy

**Method:** Build a labeled benchmark dataset of tool pairs with human-annotated conflict labels (conflict / no-conflict / partial).

**Benchmark construction:**
- 200 tool pairs labeled by 3 domain experts (majority vote for ground truth)
- Distribution: 30% true conflicts (across all types), 70% non-conflicting pairs

**Target metrics:**

| Metric | Target | Notes |
|---|---|---|
| Precision | > 90% | Minimize false positives (don't block legitimate tools) |
| Recall | > 85% | Minimize missed conflicts |
| F1 Score | > 87% | Overall quality |
| CRITICAL/HIGH precision | > 95% | Must be near-perfect for blocking conflicts |

### 15.2 Routing Simulation Stability

**Method:** Run the same impact simulation 5 times with the same inputs. Measure variance in routing outcomes.

**Target:** Routing outcome agreement across 5 runs ≥ 95% (i.e., the same tool is selected for the same query ≥ 95% of the time).

**Mitigation for instability:** Use temperature=0 for routing simulation LLM calls; use majority vote across 3 trials per query.

### 15.3 Recommendation Quality

**Evaluation:** Present recommendations to 5 MCP tool authors. They rate each on:
1. Specificity (1–5): Is it actionable?
2. Correctness (1–5): Would it actually resolve the conflict?
3. Clarity (1–5): Is the rationale understandable?

**Target:** Average score ≥ 4.0 across all dimensions.

### 15.4 Performance Benchmarks

Run nightly against reference datasets:

| Scenario | SLO |
|---|---|
| Check single tool, 100-tool registry | < 5s |
| Check single tool, 500-tool registry | < 10s |
| Check single tool, 1000-tool registry | < 20s |
| Full environment analysis, 500 tools, 100 probes | < 5 min |
| Dashboard load (500 tools, 50 conflicts) | < 2s |

---

## 16. Deployment Architecture

### 16.1 Kubernetes Deployment (Production)

```yaml
# Core services
- mtgs-api              (FastAPI, 3 replicas, HPA on CPU/RPS)
- mtgs-worker-analysis  (Celery, 5 replicas, HPA on queue depth)
- mtgs-worker-sim       (Celery, 3 replicas — expensive LLM calls)
- mtgs-frontend         (React, 2 replicas, CDN-fronted)
- mtgs-scheduler        (Celery Beat, 1 replica)

# Data
- PostgreSQL (with pgvector) — RDS/CloudSQL or self-managed with HA
- Redis — ElastiCache or self-managed cluster

# Infrastructure
- Ingress: Nginx or AWS ALB
- Secrets: Kubernetes Secrets + Vault integration
- TLS: cert-manager + Let's Encrypt (or enterprise CA)
```

### 16.2 Environment Strategy

| Environment | Purpose | Sync Policy |
|---|---|---|
| dev | Developer testing | On-demand only |
| staging | Pre-prod validation; CI gates run here | Auto-sync from staging MCP servers, hourly |
| prod | Live tool governance | Auto-sync from prod MCP servers, hourly; approval required for CRITICAL/HIGH |

### 16.3 Backup & Recovery

- PostgreSQL: continuous WAL archiving + daily snapshots, 30-day retention
- Tool version history: immutable — never deleted
- RTO: < 1 hour; RPO: < 5 minutes

---

## 17. Implementation Roadmap

### Phase 1 — Core Engine (Weeks 1–6)

**Goal:** Working conflict detection and registry, usable via API.

- [ ] Database schema, migrations
- [ ] Tool Registry CRUD API
- [ ] Lexical conflict detection (Stage 1 + Stage 2)
- [ ] Embedding integration + pgvector setup
- [ ] Semantic conflict detection (Stage 3)
- [ ] Basic REST API with API key auth
- [ ] CLI (`mtgs tools check`, `mtgs tools register`)
- [ ] CI webhook endpoint
- [ ] Unit + integration tests, 80% coverage

### Phase 2 — Simulation & Recommendations (Weeks 7–12)

**Goal:** Full impact simulation and actionable recommendations.

- [ ] Probe query library (manual + auto-generation)
- [ ] LLM routing simulation (Stage 4)
- [ ] Impact report generation
- [ ] Recommendation engine (Claude-powered)
- [ ] Recommendation review workflow
- [ ] Async job processing (Celery)
- [ ] Scheduled sync from MCP servers
- [ ] GitHub Actions plugin

### Phase 3 — Dashboard & Governance (Weeks 13–18)

**Goal:** Full governance dashboard, approval workflows, team management.

- [ ] Web dashboard (React)
- [ ] Conflict Map (D3.js)
- [ ] Approval workflow for flagged registrations
- [ ] Environment health score
- [ ] RBAC + SSO (OIDC)
- [ ] Notification system (Slack, email, PagerDuty)
- [ ] Audit log UI

### Phase 4 — Hardening & Scale (Weeks 19–24)

**Goal:** Production-grade reliability, performance, and enterprise features.

- [ ] Performance optimization (ANN tuning, caching)
- [ ] Benchmark suite + CI performance gates
- [ ] Self-hosted LLM mode (for air-gapped)
- [ ] Multi-tenant isolation hardening
- [ ] SIEM audit log export
- [ ] GitLab CI + Jenkins plugins
- [ ] Documentation site
- [ ] SOC 2 Type I readiness

---

## 18. Open Questions & Decision Log

| # | Question | Options | Status | Decision |
|---|---|---|---|---|
| 1 | Which embedding model to use as default? | OpenAI text-embedding-3-large, Cohere embed-v3, self-hosted | Open | Lean toward OpenAI for quality; offer pluggable interface |
| 2 | How to handle multi-language tool descriptions? | English-only v1; multilingual embeddings later | Decided | English-only for v1; add multilingual in Phase 4 |
| 3 | Should the system modify tool definitions directly, or only recommend? | Auto-apply; Recommendation only; Hybrid | Open | Recommendation-only for v1 (preserves human control) |
| 4 | Conflict score formula | Weighted linear; ML-trained; LLM-judged | Open | Weighted linear for v1 (transparent, debuggable); ML in Phase 4 |
| 5 | How to handle tool sets from MCP servers that don't support tools/list? | Manual import only; Agent-based crawl | Open | Manual import + JSON upload for v1 |
| 6 | Self-hosted LLM candidates for air-gapped mode | Llama 3, Mistral, Qwen | Open | Evaluate in Phase 4 |
| 7 | Should conflict suppression require approval? | Yes always; No; Only for CRITICAL | Open | Require approval for CRITICAL suppressions |

---

*Document Version: 1.0 | Status: Ready for Engineering Kickoff*
*Last Updated: 2025*
*Owner: AI Platform Team*
