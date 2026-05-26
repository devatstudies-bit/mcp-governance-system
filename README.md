# MCP Tool Governance System (MTGS)

> **Enterprise-grade governance layer for MCP tool registries.**  
> Detects conflicts, predicts LLM routing failures, simulates routing impact,
> recommends fixes, enforces approval workflows, and maintains an immutable
> audit trail — all before broken tools reach production.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-196%20passing-brightgreen.svg)](#running-tests)
[![Coverage](https://img.shields.io/badge/coverage-82%25-green.svg)](#running-tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

---

## The Problem

When enterprises deploy MCP (Model Context Protocol) servers at scale — dozens of teams, hundreds of tools — LLM tool selection failures grow non-linearly. An LLM doesn't throw an error when it routes to the wrong tool. It silently succeeds with the wrong outcome.

```
"Create a Salesforce task" → LLM picks create_task (Jira) instead of create_sf_task
```

MTGS acts as a **linter + impact analyzer** for the MCP tool layer. It catches ambiguity, overlap, and routing risk before tools reach production.

---

## What It Does

| Capability | Description |
|---|---|
| **Conflict Detection** | 4-stage pipeline: lexical → schema → semantic (embeddings) → behavioral (LLM routing simulation) |
| **Impact Simulation** | Measures routing shift before/after adding a tool across N probe queries (majority-vote across trials) |
| **Recommendation Engine** | gpt-4o-powered rewrites, renames, and scope narrowings to resolve each conflict |
| **Approval Workflow** | CRITICAL/HIGH conflicts block activation until reviewer+ signs off; TTL auto-expiry |
| **Audit Log + SIEM** | Immutable audit entries for every governance action; JSON and CEF export for Splunk/Sentinel |
| **MCP Server Sync** | Periodic diff of live MCP server tool lists against DB; detect additions/removals/updates |
| **Notification Alerting** | Slack (Block Kit), email (SMTP), PagerDuty (Events API v2) on CRITICAL/HIGH conflicts |
| **CI/CD Gate** | Webhook endpoint — returns `200` (pass) or `409` (block) for any CI pipeline |
| **Circuit Breakers** | Per-dependency open/half-open/closed state machine on all Azure and webhook calls |
| **CLI** | `mtgs tools check/register`, `mtgs analyze`, `mtgs health`, `mtgs conflicts list` |

---

## Quick Start

### 1. Prerequisites

- Python 3.12+
- Docker + Docker Compose
- Azure OpenAI resource (for embeddings)
- Azure AI Search resource (for vector ANN search)

### 2. Clone and install

```bash
git clone https://github.com/your-org/mtgs.git
cd mtgs
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — set AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
#              AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY
```

### 4. Start the stack

```bash
docker compose -f docker/docker-compose.yml up -d db redis
alembic upgrade head
uvicorn mtgs.main:app --reload
```

### 5. Check a tool before registering it

```bash
# Dry-run conflict check
mtgs tools check --file my-tool.json --env prod

# Register if clean
mtgs tools register --file my-tool.json --server my-crm-mcp --env prod
```

---

## Architecture Overview

```
                    ┌───────────────────────────────────────┐
                    │           Client Layer                 │
                    │  Web Dashboard │ CLI (mtgs) │ CI Hook  │
                    └───────────┬───────────────────────────┘
                                │ HTTPS / REST
                    ┌───────────▼───────────────────────────┐
                    │        FastAPI (Python 3.12)           │
                    │   JWT/API Key Auth  │  Rate Limiting   │
                    └───┬───────────┬───────────────┬────────┘
                        │           │               │
             ┌──────────▼──┐  ┌─────▼──────┐  ┌───▼──────────┐
             │  Registry   │  │  Analysis  │  │  Simulation  │
             │  Service    │  │  Service   │  │  Service     │
             └──────┬──────┘  └─────┬──────┘  └──────┬───────┘
                    │               │                  │
         ┌──────────▼───────────────▼──────────────────▼──────┐
         │               Redis (Celery Broker)                  │
         └──────────────────────────┬──────────────────────────┘
                                    │
         ┌──────────────────────────▼──────────────────────────┐
         │  Celery Workers: analysis queue / simulation queue   │
         │  ┌──────────────────────┐  ┌───────────────────────┐│
         │  │ Conflict Detection   │  │ Impact Simulation     ││
         │  │ (Stages 1–3)         │  │ (Stage 4, LLM)        ││
         │  └──────────┬───────────┘  └───────────┬───────────┘│
         └─────────────┼─────────────────────────-┼────────────┘
                       │                          │
         ┌─────────────▼──────────┐  ┌────────────▼──────────┐
         │ Azure OpenAI Embeddings│  │ Claude Sonnet (Routing │
         │ text-embedding-3-large │  │ Simulation + Recs)     │
         └─────────────┬──────────┘  └──────────────────────-─┘
                       │
         ┌─────────────▼──────────────────────────────────────┐
         │  Data Layer                                         │
         │  PostgreSQL 16  │  Azure AI Search (ANN)  │  Redis  │
         └────────────────────────────────────────────────────┘
```

---

## Conflict Detection Pipeline

The analysis runs in 4 stages, cheapest to most expensive:

```
Stage 1  Lexical       < 100ms   Exact name, edit distance ≤ 2, token overlap
Stage 2  Schema        < 200ms   Shared parameter names with type mismatches
Stage 3  Semantic      1–3s      Embedding cosine similarity via ANN (threshold: 0.80)
Stage 4  Behavioral    10–60s    LLM routing simulation with probe queries (3 trials)
```

**Short-circuit logic:** If Stage 1 finds a CRITICAL conflict (exact name collision), Stage 3 is skipped entirely. Stage 4 only runs for pairs flagged by Stage 3.

---

## Approval Workflow

CRITICAL and HIGH conflicts require human sign-off before a tool can become ACTIVE:

```
Tool registered → Conflict detected (CRITICAL/HIGH)
      │
      ▼
ApprovalRequest created (status: PENDING)
      │   Slack/PagerDuty alert fired
      │
      ├─► reviewer+ approves → Tool set ACTIVE  · audit entry written
      └─► reviewer+ rejects  → Tool stays BLOCKED · audit entry written
          (auto-expires after 7 days if no decision)
```

RBAC hierarchy: `viewer` < `developer` < `reviewer` < `admin` < `ci-agent`

- **developer+** can create approval requests
- **reviewer+** can approve or reject
- Role enforcement is applied at both the HTTP layer and inside `ApprovalService.decide()`

---

## Audit Log & SIEM Export

Every state-changing governance action produces an immutable `AuditEntry`:

```
TOOL_REGISTERED · TOOL_UPDATED · TOOL_DELETED
CONFLICT_DETECTED · CONFLICT_STATUS_CHANGED
APPROVAL_REQUESTED · APPROVAL_APPROVED · APPROVAL_REJECTED
ANALYSIS_RUN_STARTED · ANALYSIS_RUN_COMPLETED
USER_LOGIN · API_KEY_CREATED · API_KEY_REVOKED
```

Entries are frozen dataclasses — mutation raises `FrozenInstanceError`.

**SIEM integration (CEF export):**

```bash
# Stream CEF lines to your SIEM forwarder
curl -s -H "Authorization: Bearer $TOKEN" \
     "$MTGS_URL/v1/api/audit-logs/export?format=cef" \
     >> /var/log/mtgs/audit.cef

# Sample output line:
# CEF:0|MTGS|MCPToolGovernance|1.0|CONFLICT_DETECTED|CONFLICT_DETECTED|8|
#   rt=Jan 15 2025 14:23:01 suser=<actor-id> src=<tool-id> envId=<env-id> ...
```

Compatible with Microsoft Sentinel, Splunk, IBM QRadar, and any CEF-capable SIEM.

---

## Circuit Breakers

All external calls are protected by `CircuitBreaker` instances in `mtgs/core/resilience/`:

| Breaker | Dependency | Failure threshold | Recovery timeout |
|---|---|---|---|
| `azure-openai` | Azure OpenAI (embed + chat) | 5 | 30s |
| `azure-search` | Azure AI Search | 5 | 30s |
| `mcp-sync` | Live MCP server HTTP calls | 3 | 60s |
| `notifications` | Slack / PagerDuty webhooks | 3 | 120s |

States: `CLOSED` → `OPEN` (fail-fast) → `HALF_OPEN` (probe) → `CLOSED`

```python
from mtgs.core.resilience.circuit_breaker import azure_openai_cb

@azure_openai_cb.protect
async def call_embeddings(text: str) -> list[float]:
    ...
```

Circuit health is exposed via the `/readiness` endpoint and observable through `get_all_breakers()`.

---

## Repository Layout

```
mtgs/
├── mtgs/                       # Python package
│   ├── main.py                 # FastAPI app factory
│   ├── config.py               # Pydantic Settings (env-driven)
│   ├── database.py             # SQLAlchemy async engine
│   ├── api/
│   │   ├── middleware.py       # RequestID, access logging
│   │   └── v1/                 # REST endpoints
│   │       ├── tools.py        # Tool CRUD + registration
│   │       ├── conflicts.py    # Conflict management
│   │       ├── analysis_runs.py
│   │       ├── webhooks.py     # CI/CD gate endpoint
│   │       └── health.py       # Health score endpoint
│   ├── auth/
│   │   ├── security.py         # JWT, API keys, RBAC
│   │   └── dependencies.py     # FastAPI dependencies
│   ├── core/
│   │   ├── tool_def.py         # ToolDef dataclass
│   │   ├── conflict_detection/
│   │   │   ├── pipeline.py     # 4-stage orchestrator
│   │   │   ├── lexical.py      # Stage 1 + 2
│   │   │   └── schema_analysis.py
│   │   ├── embeddings/
│   │   │   ├── fingerprinter.py       # Builds composite embedding text
│   │   │   ├── openai_client.py       # Azure OpenAI embedding calls
│   │   │   └── azure_search_client.py # ANN vector search
│   │   ├── simulation/
│   │   │   └── impact_simulator.py    # Stage 4 LLM routing tests
│   │   ├── recommendations/
│   │   │   └── engine.py              # Claude-powered rewrite engine
│   │   ├── probe_generation/
│   │   │   └── generator.py           # Auto-generate probe queries
│   │   ├── approval/
│   │   │   └── workflow.py            # High-severity registration approval
│   │   ├── audit/
│   │   │   └── logger.py              # Immutable audit trail
│   │   ├── notifications/
│   │   │   └── service.py             # Slack / Email / PagerDuty
│   │   ├── sync/
│   │   │   └── mcp_sync.py            # Sync from live MCP servers
│   │   └── orchestrator.py            # Full Phase 2 analysis runner
│   ├── models/                 # SQLAlchemy ORM models
│   ├── schemas/                # Pydantic request/response schemas
│   └── workers/
│       ├── celery_app.py       # Celery application
│       └── tasks.py            # Async job definitions
├── cli/
│   └── main.py                 # `mtgs` CLI (Typer + Rich)
├── tests/
│   ├── unit/                   # 13 unit test modules
│   ├── integration/            # Integration tests (real DB)
│   ├── e2e/                    # End-to-end tests
│   └── performance/            # Locust load tests (Phase 4)
├── alembic/                    # DB migrations
├── docker/                     # Dockerfile + docker-compose.yml
├── docs/                       # Full documentation
│   ├── architecture.md
│   ├── getting-started.md
│   ├── api-reference.md
│   ├── conflict-detection.md
│   ├── dashboard.md
│   ├── cli.md
│   ├── deployment.md
│   ├── configuration.md
│   └── adr/                    # Architecture Decision Records
└── .github/workflows/ci.yml
```

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| API | FastAPI + Python 3.12 | Async, auto OpenAPI docs, Pydantic |
| Database | PostgreSQL 16 | ACID, JSONB for schemas |
| Vector Search | Azure AI Search | ANN over tool embeddings |
| Cache / Queue | Redis | Celery broker + embedding cache |
| Workers | Celery | Async analysis and simulation jobs |
| Embeddings | Azure OpenAI `text-embedding-3-large` | State-of-the-art at 3072 dims |
| LLM (Routing + Recs) | Claude Sonnet via Anthropic API | Best tool-use routing fidelity |
| Frontend | React + TypeScript + Tailwind CSS | Modern, component-driven |
| Graph Visualization | D3.js | Conflict map force-directed graph |
| CLI | Typer + Rich | Cross-platform, pip-installable |
| Auth | JWT + API keys | CI/CD compatible; OIDC in Phase 3 |
| Observability | OpenTelemetry → Datadog/Grafana | Traces, metrics, structured logs |

---

## Documentation

| Document | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation, first run, dev setup |
| [Architecture](docs/architecture.md) | Component design, data flow, scaling |
| [API Reference](docs/api-reference.md) | All REST endpoints with examples |
| [Conflict Detection](docs/conflict-detection.md) | Deep dive into the 4-stage pipeline |
| [Dashboard](docs/dashboard.md) | React dashboard, views, conflict map |
| [CLI Reference](docs/cli.md) | All `mtgs` commands |
| [Deployment](docs/deployment.md) | Production deployment on Azure/K8s |
| [Configuration](docs/configuration.md) | All environment variables |
| [ADR Index](docs/adr/) | Architecture Decision Records |
| [Workflow Diagrams](docs/workflow-diagrams.md) | 11 Mermaid diagrams — architecture, pipelines, state machines |
| [Roadmap](ROADMAP.md) | Build phases — what's shipped and what's planned |

---

## Running Tests

```bash
# All unit tests (196 tests, all external calls mocked — no Azure needed)
pytest tests/unit/ -v

# With coverage gate (≥80% on mtgs/core)
pytest tests/unit/ --cov=mtgs/core --cov-fail-under=80 -q

# Specific phase
pytest tests/unit/test_circuit_breaker.py -v
pytest tests/unit/test_recommendation_engine.py -v
pytest tests/unit/test_approval_workflow.py -v

# Integration tests (require running PostgreSQL via docker compose)
pytest tests/integration/ -v
```

Current baseline: **196 unit tests · 82%+ core coverage · ~5s**

---

## Benchmarks

```bash
# Install locust (included in dev deps)
pip install locust

# Headless: 50 users, 10/s ramp, 60s run
locust -f benchmarks/locustfile.py --headless \
    -u 50 -r 10 -t 60s \
    --host http://localhost:8000 \
    --html benchmarks/report.html

# Interactive web UI at http://localhost:8089
locust -f benchmarks/locustfile.py --host http://localhost:8000
```

Three simulated user profiles:

| Profile | Weight | Behaviour |
|---|---|---|
| `ReadHeavyUser` | 60% | Health checks, conflict lists, audit log reads |
| `WriteHeavyUser` | 30% | Tool registration, webhook CI gate |
| `AnalysisUser` | 10% | Triggering analysis runs, SIEM export |

Expected p95 latencies (single Uvicorn worker, stages 1+2 only):
- `GET /health` → < 5ms
- `GET /v1/environments/:id/conflicts` → < 50ms
- `POST /v1/webhooks/ci-check` → < 100ms

---

## Development

```bash
# Lint + format
ruff check mtgs/ && ruff format mtgs/

# Type check
mypy mtgs/

# Start Celery workers
celery -A mtgs.workers.celery_app worker -Q analysis,embeddings --loglevel=info
celery -A mtgs.workers.celery_app worker -Q simulation --concurrency=2 --loglevel=info

# Start periodic sync beat
celery -A mtgs.workers.celery_app beat --loglevel=info
```

---

## Contributing

1. Fork the repo and create a feature branch
2. Add tests — target ≥80% coverage on new code
3. Run `ruff check` and `mypy` before opening a PR
4. PR description must include: what changed, why, any ADR implications

---

## License

MIT — see [LICENSE](LICENSE).
