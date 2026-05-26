# MTGS Roadmap

> **Last updated:** 2026-05-26  
> Tracks every build phase — what's shipped, what's next.

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Shipped — tests written, implementation complete, passing |
| 🔄 | In progress |
| ⏳ | Planned — not yet started |

---

## ✅ Phase 1 — Core Conflict Detection Pipeline

**Tests:** `tests/unit/test_conflict_detection*.py` · `tests/unit/test_pipeline.py`

| Component | File | Description |
|-----------|------|-------------|
| ToolDef DTO | `mtgs/core/tool_def.py` | Canonical tool definition dataclass used across all stages |
| Stage 1 — Lexical | `mtgs/core/conflict_detection/lexical.py` | Exact name match, edit distance ≤ 2, token overlap |
| Stage 2 — Schema | `mtgs/core/conflict_detection/schema_analysis.py` | Shared param names with type mismatches |
| Stage 3 — Semantic | `mtgs/core/embeddings/` | Azure OpenAI `text-embedding-3-large` + ANN cosine similarity (threshold 0.80) |
| Stage 4 — Behavioral | `mtgs/core/simulation/impact_simulator.py` | LLM routing simulation with probe queries, majority vote across 3 trials |
| Pipeline Orchestrator | `mtgs/core/conflict_detection/pipeline.py` | 4-stage runner with short-circuit on CRITICAL |
| Embedding Fingerprinter | `mtgs/core/embeddings/fingerprinter.py` | Composite embedding text builder |
| Azure Search Client | `mtgs/core/embeddings/azure_search_client.py` | HNSW index, 3072-dim vector ANN |

---

## ✅ Phase 2 — Analysis Intelligence Layer

**Tests:** `tests/unit/test_probe_generation.py` · `tests/unit/test_impact_simulator.py` · `tests/unit/test_recommendation_engine.py` · `tests/unit/test_mcp_sync.py` · `tests/unit/test_notifications.py` · `tests/unit/test_orchestrator.py`

| Sub-phase | Component | File | Description |
|-----------|-----------|------|-------------|
| 2A | Probe Query Generator | `mtgs/core/probe_generation/generator.py` | LLM generates natural-language queries per tool + adversarial overlap pairs |
| 2B | Impact Simulator | `mtgs/core/simulation/impact_simulator.py` | Before/after routing comparison; `routing_shift_pct`; `ImpactReport` |
| 2C | Recommendation Engine | `mtgs/core/recommendations/engine.py` | gpt-4o rewrites: RENAME / DESCRIPTION_REWRITE / SCOPE_NARROWING / SCHEMA_CLARIFICATION / DEPRECATE |
| 2D | MCP Server Sync | `mtgs/core/sync/mcp_sync.py` | Diffs live MCP server tool lists vs DB snapshot; `SyncReport` (added/removed/updated/unchanged) |
| 2E | Notification Router | `mtgs/core/notifications/service.py` | Slack (Block Kit), SMTP email (aiosmtplib), PagerDuty (Events API v2); severity filtering; never raises |
| 2F | Analysis Orchestrator | `mtgs/core/orchestrator.py` | Ties probe gen → simulation → recommendations → notifications; `risk_score` computation |

---

## ✅ Phase 3 — REST API Layer

**Tests:** `tests/unit/test_analysis_runs_api.py` · `tests/unit/test_approval_workflow.py` · `tests/unit/test_audit_log.py`

| Sub-phase | Endpoints | File | Description |
|-----------|-----------|------|-------------|
| 3A | `/v1/api/analysis-runs/` | `mtgs/api/v1/analysis_runs.py` | Trigger analysis, list runs, get by ID, stats endpoint |
| 3B | `/v1/api/approvals/` | `mtgs/api/v1/approvals.py` | PENDING → APPROVED/REJECTED/EXPIRED state machine; reviewer+ RBAC |
| 3C | `/v1/api/audit-logs/` | `mtgs/api/v1/audit_logs.py` | Filterable audit log; JSON + CEF export for Splunk/Sentinel/QRadar |

**RBAC hierarchy:** `viewer` < `developer` < `reviewer` < `admin` < `ci-agent`

---

## ✅ Phase 4A — Resilience, Benchmarks & Docs

**Tests:** `tests/unit/test_circuit_breaker.py`

| Component | File | Description |
|-----------|------|-------------|
| Circuit Breaker | `mtgs/core/resilience/circuit_breaker.py` | CLOSED → OPEN → HALF_OPEN state machine; asyncio.Lock; `@protect` decorator |
| Named singletons | (same file) | `azure_openai_cb`, `azure_search_cb`, `mcp_sync_cb`, `notifications_cb` |
| Locust benchmarks | `benchmarks/locustfile.py` | ReadHeavy (60%) / WriteHeavy (30%) / AnalysisUser (10%); 15 endpoints covered |
| Workflow diagrams | `docs/workflow-diagrams.md` | 11 colorful Mermaid diagrams covering every major workflow |
| README | `README.md` | Full rewrite — badges, capabilities table, architecture ASCII, all sections |

**Test baseline at Phase 4A:** 196 unit tests · 82%+ core coverage · ~5s

---

## ⏳ Phase 4B — React Dashboard

> **Status:** Not started

**Planned stack:** Vite 5 + React 18 + TypeScript 5 + Tailwind CSS v3 + TanStack Query v5 + D3.js v7 + Recharts 2

**Planned location:** `dashboard/`

| View | Description |
|------|-------------|
| Dashboard Home | Health score gauge, risk trend chart (Recharts), top conflicts summary |
| Conflict Map | D3.js force-directed graph — tools as nodes, conflicts as edges, severity-coloured |
| Tools Registry | Paginated table with status badges; register + dry-run check from the UI |
| Analysis Runs | Timeline of runs; trigger new analysis; view per-run report |
| Approvals Queue | Pending approvals card grid; approve/reject with reviewer role gating |
| Audit Log | Filterable table; export JSON / CEF directly from the browser |
| Settings | Circuit breaker health panel; MCP server sync status; environment selector |

---

## ⏳ Phase 4C — CI/CD Pipeline

> **Status:** Not started · **File:** `.github/workflows/ci.yml`

Planned jobs:

```
lint        ruff check + ruff format --check
type-check  mypy mtgs/
test        pytest tests/unit/ --cov=mtgs/core --cov-fail-under=80
build       docker build -f docker/Dockerfile .
```

- Runs on: `push` to `main`/`develop`, all pull requests  
- Matrix: Python 3.12  
- Caches: pip dependencies, Docker layer cache  
- Artifacts: coverage HTML report, test results XML  

---

## ⏳ Phase 4D — Kubernetes / Helm Chart

> **Status:** Not started · **Location:** `deploy/helm/mtgs/`

Planned manifests:

| Resource | Description |
|----------|-------------|
| `Deployment` (api) | FastAPI + Uvicorn; HPA min=2 max=10 on CPU 70% |
| `Deployment` (worker-analysis) | Celery analysis+embeddings queues; min=1 max=5 |
| `Deployment` (worker-simulation) | Celery simulation queue; concurrency=2 |
| `Deployment` (beat) | Celery beat scheduler; single replica |
| `Service` / `Ingress` | NGINX ingress with TLS termination |
| `HorizontalPodAutoscaler` | API + worker tiers |
| `ConfigMap` | Non-secret environment variables |
| `ExternalSecret` | Azure Key Vault → K8s secrets via ESO |
| `PodDisruptionBudget` | minAvailable=1 for API tier |

Target platform: **Azure Kubernetes Service (AKS)**

---

## ⏳ Phase 4E — OpenTelemetry Instrumentation

> **Status:** Not started · **File:** `mtgs/core/telemetry.py`

Planned coverage:

| Signal | What's instrumented |
|--------|---------------------|
| Traces | FastAPI request spans, DB query spans, Celery task spans, Azure call spans |
| Metrics | `conflict_detections_total`, `routing_shift_pct` histogram, `circuit_breaker_state` gauge, `analysis_duration_seconds` |
| Logs | Structured JSON logs with `trace_id`/`span_id` correlation |
| Exporters | OTLP → Datadog Agent (prod), Prometheus scrape endpoint (local dev) |

---

## Summary

```
Phase 1   ✅  Conflict detection pipeline (4 stages)
Phase 2   ✅  Intelligence layer (probes · simulation · recommendations · sync · notifications · orchestrator)
Phase 3   ✅  REST API (analysis runs · approvals · audit log)
Phase 4A  ✅  Resilience (circuit breakers · benchmarks · docs · README)
──────────────────────────────────────────────────────
Phase 4B  ⏳  React dashboard
Phase 4C  ⏳  CI/CD pipeline (.github/workflows)
Phase 4D  ⏳  Kubernetes / Helm chart
Phase 4E  ⏳  OpenTelemetry instrumentation
```

**Current test count:** 196 unit tests · **Core coverage:** 82%+
