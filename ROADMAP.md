# MTGS Roadmap

> **Last updated:** 2026-05-31  
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
| Stage 1 — Lexical | `mtgs/core/conflict_detection/lexical.py` | Exact name match · Levenshtein edit distance ≤ 2 · Jaccard token overlap ≥ 50% |
| Stage 2 — Schema | `mtgs/core/conflict_detection/schema_analysis.py` | Shared param names with type mismatches |
| Stage 3 — Semantic | `mtgs/core/embeddings/` | Azure OpenAI `text-embedding-3-large` + ANN cosine similarity (threshold 0.80) |
| Stage 4 — Behavioral | `mtgs/core/simulation/impact_simulator.py` | LLM routing simulation with probe queries, majority vote across 3 trials |
| Pipeline Orchestrator | `mtgs/core/conflict_detection/pipeline.py` | 4-stage runner with short-circuit on CRITICAL |
| Embedding Fingerprinter | `mtgs/core/embeddings/fingerprinter.py` | Composite embedding text builder + SHA256 fingerprint hash for stale detection |
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

**RBAC hierarchy:** `viewer` < `developer` < `reviewer` < `admin`

---

## ✅ Phase 4A — Resilience, Benchmarks & Docs

**Tests:** `tests/unit/test_circuit_breaker.py`

| Component | File | Description |
|-----------|------|-------------|
| Circuit Breaker | `mtgs/core/resilience/circuit_breaker.py` | CLOSED → OPEN → HALF_OPEN state machine; asyncio.Lock; `@protect` decorator |
| Named singletons | (same file) | `azure_openai_cb` (5/30s) · `azure_search_cb` (5/30s) · `mcp_sync_cb` (3/60s) · `notifications_cb` (3/120s) |
| Locust benchmarks | `benchmarks/locustfile.py` | ReadHeavy (60%) / WriteHeavy (30%) / AnalysisUser (10%); 15 endpoints covered |
| Workflow diagrams | `docs/workflow-diagrams.md` | 11 Mermaid diagrams covering every major workflow |
| README | `README.md` | Full rewrite — badges, capabilities table, architecture ASCII, all sections |

---

## ✅ Phase 4B — React Dashboard

**Location:** `dashboard/`  
**Stack:** Vite 5 · React 18 · TypeScript 5 · Tailwind CSS v3 · TanStack Query v5 · D3.js v7 · Recharts 2

| Page | Route | Description |
|------|-------|-------------|
| Dashboard Home | `/` | Health score gauge · 7-day conflict trend chart · D3 force-directed conflict map · KPI cards · recent conflicts |
| Conflicts | `/conflicts` | Filterable table (severity + status) · paginated · PATCH to acknowledge/resolve |
| Tools | `/tools` | Client-side search · status badges · 20 per page |
| Analysis Runs | `/analysis` | Run history · risk score colour coding · manual trigger |
| Approvals | `/approvals` | Pending approval cards · Approve/Reject · 15s polling |
| Audit Log | `/audit` | Filter by action + actor · JSON/CEF export |
| Settings | `/settings` | Circuit breaker live status · dashboard config |

**Test baseline at Phase 4B:** 194 unit tests · 82%+ core coverage · ~5s

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

| Signal | What's instrumented |
|--------|---------------------|
| Traces | FastAPI request spans, DB query spans, Celery task spans, Azure call spans |
| Metrics | `conflict_detections_total`, `routing_shift_pct` histogram, `circuit_breaker_state` gauge, `analysis_duration_seconds` |
| Logs | Structured JSON logs with `trace_id`/`span_id` correlation |
| Exporters | OTLP → Datadog Agent (prod), Prometheus scrape endpoint (local dev) |

---

## ⏳ Phase 5 — Action Classification + Ownership Lifecycle  *(Weeks 1–5)*

> **Status:** Not started  
> **Why first:** `action_class` is a hard dependency for Phase 6 (FINANCIAL/LEGAL zero-tolerance drift), Phase 7 (heat map), Phase 8 (sidecar enforcement), and the updated health score formula. Nothing else in v2.0 can be built meaningfully without it.

| Deliverable | Description |
|-------------|-------------|
| DB migration | Add `action_class` (READ \| WRITE_REVERSIBLE \| WRITE_IRREVERSIBLE \| FINANCIAL \| LEGAL), `action_class_inferred`, `action_class_confidence` to `Tool`; add `owner_user_id`; add `orphaned` to status enum |
| Action class inference engine | At registration, call Claude with tool name + description + schema; compare declared vs inferred; mismatch with confidence > 0.80 → `ACTION_CLASS_MISMATCH` conflict (CRITICAL for FINANCIAL/LEGAL, HIGH for WRITE_IRREVERSIBLE, MEDIUM otherwise) |
| Low-confidence gate | Inferred confidence < 0.80 → flag for human classification regardless of match; prompt developer to add explicit action verbs |
| `EscalationPolicy` table + CRUD API | Rules array: action_class, server_id_pattern, requires_approval, approval_timeout_seconds, escalation_target_team_id |
| FINANCIAL/LEGAL approval gate | These action classes always require Reviewer approval at registration — independent of whether any conflict was detected |
| Updated CI webhook response | Add `action_class_summary` (declared, inferred, mismatch, confidence) and `escalation_policy_preview` to `POST /environments/{id}/tools/check` |
| `OwnershipHistory` table | Immutable record of all ownership transfers |
| Ownership transfer workflow | Source owner or Admin initiates; target owner confirms; logged immutably |
| `ORPHANED_TOOL` conflict type | Daily Celery beat task: no active `owner_user_id` for > 30 days → status = `orphaned` + alert Admin; > 60 days → status = `flagged` + governance queue |
| New recommendation types | `ACTION_CLASS_CORRECTION`, `ESCALATION_POLICY_ADD`, `OWNERSHIP_TRANSFER` |
| Updated simulation impact report | Add `action_class_impact` field (does the new tool shift routing onto FINANCIAL/LEGAL tools?) |
| Notification routing | FINANCIAL/LEGAL alerts also route to finance/legal team lead |

---

## ⏳ Phase 6 — Behavioural Drift Detection  *(Weeks 4–9)*

> **Status:** Not started  
> **Why after Phase 5:** Needs `action_class` to apply the FINANCIAL/LEGAL zero-tolerance rule (any drift → CRITICAL immediately).  
> **Key concept:** Catches silent API changes after a tool is already registered — not from description text, but from live execution output.

| Deliverable | Description |
|-------------|-------------|
| DB migration | Add `behavioral_fingerprint` (JSONB output vector), `behavioral_drift_score` (NUMERIC 0–100), `behavioral_baseline_updated_at` to `Tool` |
| `BehavioralFingerprintCheck` table | `tool_id`, `check_timestamp`, `probe_query_ids`, `baseline_output_vector`, `current_output_vector`, `drift_score`, `affected_probes`, `conflict_raised`, `check_trigger` |
| Drift detection engine | Execute 20 probes against live MCP tool via `tools/call`; normalise each response into output vector (response_schema_hash, key_field_presence_flags, response_length_bucket, error_rate); compute `drift_score = 100 × (1 − cosine_similarity(baseline, current))` |
| Safe probe execution | Read-only or synthetic identifiers (`test_probe_do_not_execute_xyz`); server opt-in required; never fires without explicit configuration |
| `BEHAVIORAL_DRIFT` conflict type + severity | Drift 5–10% → LOW · 10–25% → MEDIUM · > 25% → HIGH · any drift on FINANCIAL/LEGAL → CRITICAL immediately; runtime sidecar notified to pause tool |
| Celery beat schedule | Daily drift check per active tool; on-demand via API |
| Baseline management | Updates only on: (a) explicit owner/Reviewer acknowledgment via CLI or API, or (b) confirmed tool version bump. Unacknowledged drift accumulates intentionally — captures unreported API changes |
| Escalation rule | Unacknowledged drift > 25% for > 7 days → escalate to Admin |
| Updated health score formula | Replaces current simple deduction model: conflict state 30% + behavioural drift 20% + action class coverage 20% + card freshness 15% + ownership completeness 15% |
| Alerts | Drift > 10% → owner team · unacknowledged > 25% for 7 days → Admin |

---

## ⏳ Phase 7 — Dashboard v2.0  *(Weeks 7–12)*

> **Status:** Not started  
> **Can begin** once Phase 5 data exists. Phase 6 data needed for the Drift Dashboard page.

| Deliverable | Description |
|-------------|-------------|
| Home page updates | Add FINANCIAL/LEGAL tool count KPI · escalation queue depth badge · updated health score display showing 5-component breakdown |
| Conflict Map — Action Risk Heat Map layer | Toggle overlay: nodes coloured by action class — gray (READ), blue (WRITE_REVERSIBLE), yellow (WRITE_IRREVERSIBLE), orange (FINANCIAL), red (LEGAL) |
| New page — Behavioural Drift Dashboard | Per-tool drift score time series · FINANCIAL/LEGAL tools pinned at top · top-10 drift leaderboard · annotation pins for version bumps, acknowledgments, unacknowledged alerts · drill-down showing before/after output vectors |
| New page — Escalation Queue | Pending FINANCIAL/LEGAL tool call approvals · timeout countdown · one-click Approve/Reject · mobile-optimised · filter by action class / server / team |
| New page — Antifragile Loop Panel | Placeholder wired to Phase 9 data: proposed policy updates list + false positive rate trend |
| Tool Registration Wizard | 4-step flow replacing plain POST form: upload JSON → live stage indicators → results with action class summary + escalation preview → register |
| Tools page updates | Add `action_class` badge column · add `behavioral_drift_score` column with colour coding |

---

## ⏳ Phase 8 — Runtime Enforcement Sidecar  *(Weeks 10–16)*

> **Status:** Not started  
> **Why after Phases 5–6:** Needs `action_class` for enforcement rules and `behavioral_drift_score` for drift-block logic.  
> **Key concept:** A proxy that sits between the LLM and the MCP tools, intercepting every tool call before it executes.

| Deliverable | Description |
|-------------|-------------|
| `SidecarToolCallEvent` model | `server_id`, `tool_name`, `action_class`, `decision` (ALLOWED \| BLOCKED \| ESCALATED), `block_reason`, `escalation_event_id`, `latency_ms`, `timestamp`; batch-ingested every 10s |
| `EscalationEvent` model | `tool_name`, `action_class`, `escalation_rule_id`, `status` (pending \| approved \| rejected \| timed_out), `assigned_to`, `decided_at`, `timeout_at` |
| `X-Sidecar-Token` auth | Short-lived signed JWT, 60-second expiry, auto-rotation; all sidecar↔MTGS communication TLS 1.3 |
| Enforcement rules | FINANCIAL/LEGAL → pause + dispatch escalation · drift > 25% unacknowledged → BLOCKED · orphaned/flagged tool → BLOCKED · unregistered tool → CRITICAL alert + block |
| FAIL_OPEN / FAIL_CLOSED | Configurable per action class; production defaults: FAIL_CLOSED for FINANCIAL/LEGAL, FAIL_OPEN for READ |
| Escalation timeouts | FINANCIAL: 15 min → auto-reject · LEGAL: 60 min → auto-reject · all decisions written as immutable audit log entries |
| Temporal.io integration | Durable escalation workflows — survives worker restart mid-approval; replaces simple DB-record approvals for FINANCIAL/LEGAL decisions |
| Sidecar deployments | Docker container · Kubernetes sidecar via admission webhook · Python SDK (in-process) |
| `Escalation Approver` role | Separate from existing `reviewer` — approves runtime calls, not registration conflicts |
| 5-week rollout playbook | Week 1–2: Observe mode · Week 3: classify all FINANCIAL/LEGAL tools · Week 4: Enforce for READ/WRITE_REVERSIBLE · Week 5+: full Enforce with FINANCIAL/LEGAL blocking |

---

## ⏳ Phase 9 — Antifragile Governance Loop  *(Weeks 15–18)*

> **Status:** Not started  
> **Why after Phase 8:** Needs meaningful event history from Phases 5–8 before the scan has patterns to detect.

| Deliverable | Description |
|-------------|-------------|
| `ProposedPolicyUpdate` model | `trigger_evidence` (JSONB), `proposed_change` (JSONB), `predicted_impact`, `status` (pending_review \| accepted \| rejected), `reviewed_by`, `antifragile_loop` flag on audit entry |
| Weekly Celery scan — 5 trigger patterns | (1) Same conflict type for same tool pair in 3+ consecutive runs → elevate severity + propose rule · (2) Same action class mismatch for 5+ tools → propose updating inference prompt · (3) Ghost break confirmed by owner → promote probe queries to permanent set · (4) Conflict suppressed as false positive → propose reducing threshold by 0.02 · (5) Action class triggers escalation > 5×/week on same server → propose permanent rule |
| False positive tracking | Reviewer suppresses conflict → optional `false_positive` flag; feeds weekly scan |
| Governance Intelligence Report | Auto-generated quarterly: rules added via loop · false positive rate trend · conflict resolution time trend · rules dormant > 90 days |
| Admin review workflow | All proposed updates require Admin approval before application — never auto-applied |
| Antifragile Loop Panel | Fully wired in dashboard: proposed updates with evidence · Approve/Reject per proposal · Report download |

---

## ⏳ Phase 10 — Production Hardening  *(Weeks 17–22)*

> **Status:** Not started · Runs partially in parallel with Phase 9.

| Deliverable | Description |
|-------------|-------------|
| Cascading deprecation workflow | Dependency graph of tools referencing the deprecated tool · semantic search for closest replacement · migration path with recommended definition update · 30-day warning timeline with weekly alerts + hard cutoff requiring Reviewer sign-off · shadow traffic routing to validate migration safety · block new registrations referencing deprecated tool after warning period |
| Production log import | Import real user queries that routed to specific tools as high-quality probes for simulation accuracy |
| Self-hosted LLM mode | Swap Azure OpenAI for Ollama / vLLM for air-gapped deployments; document accuracy trade-offs for action class inference |
| Native CI plugins | GitHub Actions published action (`mtgs-check`) · GitLab CI component · Jenkins shared library |
| Performance hardening | ANN index tuning · sidecar policy prefetch on start · embedding cache warm-up · probe batch parallelism |
| Benchmark suite | Nightly CI gates against all Section 15 NFR targets |
| SIEM export update | Include sidecar tool call events (ALLOWED/BLOCKED/ESCALATED) in CEF export stream |
| SSO (OIDC) | `Escalation Approver` role mapped from enterprise IdP groups for finance and legal teams |
| Documentation site | Runbook · sidecar deployment guide · action class cookbook · antifragile loop tuning guide |
| SOC 2 Type I | Audit log completeness · access control evidence · encryption at rest/in-transit · incident response procedure |
| AAGS shared platform | Unified PostgreSQL (separate schemas: `mtgs` / `aags`) · shared Temporal.io cluster · shared escalation event schema · shared antifragile loop Celery task · unified governance dashboard with environment selector |

---

## Summary

```
Phase 1    ✅  Conflict detection pipeline (4 stages)
Phase 2    ✅  Intelligence layer (probes · simulation · recommendations · sync · notifications)
Phase 3    ✅  REST API (analysis runs · approvals · audit log)
Phase 4A   ✅  Resilience (circuit breakers · benchmarks · docs)
Phase 4B   ✅  React dashboard (7 pages)
────────────────────────────────────────────────────────────────────────
Phase 4C   ⏳  CI/CD pipeline (.github/workflows)
Phase 4D   ⏳  Kubernetes / Helm chart
Phase 4E   ⏳  OpenTelemetry instrumentation
────────────────────────────────────────────────────────────────────────
Phase 5    ⏳  Action Classification + Ownership Lifecycle     (Weeks 1–5)
Phase 6    ⏳  Behavioural Drift Detection                     (Weeks 4–9)
Phase 7    ⏳  Dashboard v2.0 (4 new pages + updates)         (Weeks 7–12)
Phase 8    ⏳  Runtime Enforcement Sidecar                     (Weeks 10–16)
Phase 9    ⏳  Antifragile Governance Loop                     (Weeks 15–18)
Phase 10   ⏳  Production Hardening + SOC 2 + AAGS platform   (Weeks 17–22)
```

**Current test count:** 194 unit tests · **Core coverage:** 82%+
