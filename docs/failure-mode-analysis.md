# MTGS — Failure Mode Analysis

> **Scope:** Every layer of the MCP Tool Governance System — infrastructure, application, core logic, external integrations, security, and operations.  
> **Format:** For each failure mode: *what breaks → effect on the system → severity → current mitigation already built → recommended hardening.*  
> **Last updated:** 2026-05-26

---

## Severity Scale

| Level | Meaning |
|-------|---------|
| 🔴 **CRITICAL** | System is down or silently producing wrong governance decisions |
| 🟠 **HIGH** | A core workflow is broken; workaround exists but requires manual intervention |
| 🟡 **MEDIUM** | Degraded capability; system still runs but output quality is reduced |
| 🟢 **LOW** | Minor UX or operational inconvenience; no governance impact |

---

## 1. Infrastructure Layer

### 1.1 PostgreSQL Unavailable

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | DB host unreachable, OOM, or disk full |
| **Effect** | All API endpoints return 500; tool registration blocked; analysis results cannot be persisted; audit trail stops |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | `pool_pre_ping=True` in `database.py` detects stale connections before every query; `pool_size`, `pool_timeout`, and `max_overflow` are all configurable via Pydantic Settings (`database_pool_size=10`, `database_pool_timeout=30`); Docker Compose `restart: unless-stopped` |
| **Recommended hardening** | Deploy PostgreSQL with a hot-standby replica (Azure Database for PostgreSQL — Flexible Server with zone-redundant HA); add a `/readiness` probe that actively tests the DB connection and fails when the pool is exhausted |

---

### 1.2 Redis Unavailable

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Redis crashes, evicts keys under memory pressure, or network partition |
| **Effect** | Celery cannot accept new tasks (analysis and simulation jobs queue silently drop); embedding cache cold; beat scheduler stops firing periodic sync and scan tasks |
| **Severity** | 🔴 CRITICAL for async workers; 🟡 MEDIUM for API (sync endpoints still respond) |
| **Current mitigation** | `CELERY_TASK_ACKS_LATE = True` in worker config means tasks are not acknowledged until complete; Docker Compose restart policy |
| **Recommended hardening** | Redis Sentinel or Azure Cache for Redis with geo-replication; set `maxmemory-policy allkeys-lru` to prevent OOM eviction of task payloads; add Redis health to `/readiness`; implement task result backend fallback to PostgreSQL |

---

### 1.3 Azure OpenAI Rate Limited or Unavailable

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | HTTP 429 (TPM/RPM rate limit), 503 (regional service outage), or deployment-level quota exhausted |
| **Effect** | Stage 3 semantic similarity cannot compute embeddings → conflict detection stops at Stage 2; Stage 4 behavioral simulation returns empty; recommendation engine produces no suggestions; probe generator returns `[]` |
| **Severity** | 🟠 HIGH (Stages 1–2 still run; lexical conflicts still caught) |
| **Note** | Azure OpenAI is **fully managed PaaS** — Microsoft handles infrastructure HA, patching, and within-region redundancy. The two failure modes that are **your responsibility** are: (1) staying within your allocated TPM/RPM quota, and (2) handling regional outages by routing to a secondary deployment. |
| **Current mitigation** | `azure_openai_cb` circuit breaker trips after 5 consecutive failures, fail-fasts for 30s to prevent thundering herd; `CircuitOpenError` is caught and surfaced in API responses; probe generator and recommendation engine return gracefully on LLM errors |
| **Recommended hardening** | Implement exponential back-off with jitter on 429s before the circuit opens; cache embeddings in Redis (keyed on `sha256(fingerprint_text)`) with TTL 24h to survive short outages without re-calling the API; provision a secondary Azure OpenAI deployment in a paired region and configure `azure_openai_cb` to failover to it on OPEN state; set per-deployment TPM quotas and monitor via Azure Monitor alerts before hitting the cap |

---

### 1.4 Azure AI Search Unavailable

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Azure region outage, service-level incident, or throttled indexing quota |
| **Effect** | ANN similarity search for Stage 3 fails; no semantic conflict detection; new tool embeddings cannot be indexed |
| **Severity** | 🟠 HIGH |
| **Note** | Azure AI Search is **fully managed PaaS** — Microsoft handles all infrastructure, hardware failover, sharding, and automatic replica management within a region. You do not manage replicas yourself; the service tier you select determines the SLA (Standard tier = 99.9% with Availability Zones enabled = 99.99%). Within-region HA is Microsoft's responsibility. |
| **Current mitigation** | `azure_search_cb` circuit breaker (threshold 5, recovery 30s); Stage 3 raises and pipeline short-circuits cleanly; Stages 1+2 continue operating |
| **Recommended hardening** | Choose **Standard S1+** tier with **Availability Zones** enabled for 99.99% SLA; for true DR, provision a second Azure AI Search service in a paired region and use Azure Traffic Manager to route between them; store raw embedding vectors in a PostgreSQL `vector` column (pgvector) as a cold fallback for brute-force cosine search when ANN is unavailable; expose index staleness metric (`last_indexed_at` vs `tool.updated_at`) |

---

## 2. Application Layer

### 2.1 FastAPI Worker Crash

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Unhandled exception kills the Uvicorn worker process |
| **Effect** | In-flight HTTP requests dropped; clients see connection reset |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | `RequestID` middleware adds `X-Request-ID` to every request for tracing; FastAPI global exception handler returns structured JSON errors |
| **Recommended hardening** | Run multiple Uvicorn workers (`--workers 4`) or behind Gunicorn; add process-level supervisor (systemd / K8s Deployment with `restartPolicy: Always`); integrate Sentry SDK for automatic crash capture with full request context |

---

### 2.2 Celery Worker Dies Mid-Task

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Worker OOM-killed or host reboots during a long analysis task |
| **Effect** | Analysis task disappears from queue; no result written; `AnalysisRun` stays in `RUNNING` state forever (zombie run) |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | `task_acks_late=True` in `celery_app.py` — task is not acknowledged until it completes, so Redis re-queues it if the worker dies; `run_conflict_analysis_task` and `sync_mcp_server_task` both call `self.retry(exc=exc)` on failure; `asyncio.gather(..., return_exceptions=True)` in the orchestrator catches partial failures in probe generation and recommendation generation individually without aborting the whole run; separate `simulation` queue with `--concurrency=2` limits resource contention |
| **Recommended hardening** | Add `task_soft_time_limit` (e.g. 300s) and `task_time_limit` (360s) to kill runaway LLM calls; implement a watchdog Celery beat task that sets any `AnalysisRun` stuck in `RUNNING` for >10 min back to `FAILED`; store `worker_hostname` on the run record for post-mortem |

---

### 2.3 Celery Beat Scheduler Stops

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Beat process crashes or loses its schedule state |
| **Effect** | `sync-all-mcp-servers` (every 15 min) and `hourly-conflict-scan` stop firing; tool registry drift goes undetected |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | Beat process is a separate Docker service; Docker Compose `restart: unless-stopped` |
| **Recommended hardening** | Use `django-celery-beat` or `redbeat` (Redis-backed schedule) so the schedule survives a beat restart without losing next-fire timestamps; add a Prometheus/Datadog metric `celery_beat_last_fire_time` and alert if it goes stale |

---

### 2.4 Memory Leak in Long-Running Worker

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Worker accumulates large embedding arrays or LLM response objects in memory over many tasks |
| **Effect** | Worker eventually OOM-killed; task re-queued; cycle repeats |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | None explicitly implemented |
| **Recommended hardening** | Set `--max-tasks-per-child=100` on Celery workers to recycle processes; add `max-memory-per-child=512000` (512 MB) to auto-restart bloated workers; profile with `tracemalloc` in staging |

---

## 3. Conflict Detection Pipeline

### 3.1 Stage 1 False Negative — Missed Lexical Conflict

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Two tools have the same semantic meaning but very different names (e.g. `send_msg` vs `dispatch_message`) |
| **Effect** | Stage 1 returns no conflict; Stage 3 must catch it — but only if embeddings are current |
| **Severity** | 🟡 MEDIUM (Stage 3 is the safety net) |
| **Current mitigation** | 4-stage pipeline design ensures multiple independent detection layers |
| **Recommended hardening** | Add synonym expansion to Stage 1 using a domain-specific verb dictionary (create/add/new, delete/remove/drop, etc.); log Stage 1 miss rate as a metric and tune token overlap threshold |

---

### 3.2 Stage 3 Stale Embeddings

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | A tool's description is updated in the DB but its embedding vector in Azure AI Search is not re-indexed |
| **Effect** | ANN search returns the old similarity score; a newly introduced conflict may not be detected at Stage 3 |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | `MCPServerSyncService.diff()` detects `updated` tools in the `SyncReport` |
| **Recommended hardening** | On every `TOOL_UPDATED` event, enqueue a `reindex_tool_embedding_task` Celery job; add `embedding_updated_at` column to the `Tool` model and alert when it lags `updated_at` by >1 hour; nightly full re-index job as a safety net |

---

### 3.3 Stage 4 LLM Hallucination in Routing Simulation

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | The routing simulation LLM picks a tool for reasons unrelated to the probe query (e.g. alphabetical bias, positional bias in the tool list) |
| **Effect** | `routing_shift_pct` is inflated or deflated; false CRITICAL/HIGH conflicts or missed conflicts |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | Majority vote across 3 trials (`_majority()` in `impact_simulator.py`) reduces single-trial noise |
| **Recommended hardening** | Shuffle tool list order between trials to eliminate positional bias; increase trial count to 5 for CRITICAL severity decisions; add a confidence score (how often did trials agree?) to `ImpactReport`; log all raw trial results for auditability |

---

### 3.4 Short-Circuit Skips Stage 3 for a True CRITICAL

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Stage 1 marks a conflict CRITICAL (exact name collision) and Stage 3 is skipped — but the conflict pair also has a subtle schema conflict that would affect the recommendation |
| **Effect** | Recommendation engine has less context; generated fix may be incomplete |
| **Severity** | 🟢 LOW (CRITICAL is still caught; only recommendation quality is affected) |
| **Current mitigation** | Conflict is blocked at Stage 1; approval workflow triggers |
| **Recommended hardening** | For CRITICAL conflicts, still run Stage 2 schema analysis (it's cheap, <200ms) before short-circuiting Stage 3; pass schema diff to recommendation engine even when semantic stage is skipped |

---

## 4. Recommendation Engine

### 4.1 LLM Returns Malformed JSON

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | gpt-4o returns a partial JSON array, markdown-wrapped code block, or truncated response |
| **Effect** | `_parse_recommendations()` raises `json.JSONDecodeError`; no recommendations returned; conflict stays unresolved |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | `RecommendationEngine.generate()` wraps the entire LLM call + parse in `try/except Exception` and returns `[]` — never raises; `_parse_recommendations()` separately logs warnings for unexpected response types (`logger.warning("Unexpected LLM response type: %s")`), missing `recommendations` key, and unknown recommendation types; the analysis run continues even with empty recommendations |
| **Recommended hardening** | Use OpenAI Structured Outputs (JSON schema enforcement) to guarantee valid JSON; add a retry with explicit "return ONLY a JSON array" re-prompt on parse failure; log malformed raw responses for prompt engineering review |

---

### 4.2 Recommendation Type Not in Allowed Set

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | LLM invents a new type like `"MERGE"` or `"SPLIT"` not in `VALID_RECOMMENDATION_TYPES` |
| **Effect** | That recommendation is silently filtered out |
| **Severity** | 🟢 LOW |
| **Current mitigation** | `VALID_RECOMMENDATION_TYPES` frozenset validation in `_parse_recommendations()` already calls `logger.warning("Skipping unknown recommendation_type: %s", rec_type)` — the rejection is logged, not silent |
| **Recommended hardening** | Include the allowed types explicitly in the LLM prompt system message to reduce frequency; track warning frequency as a metric to detect model drift |

---

## 5. Approval Workflow

### 5.1 Approval Request Never Decided (TTL Expiry)

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Reviewer is on leave or Slack alert is missed; request expires after 7 days |
| **Effect** | Tool stays `BLOCKED` permanently; developer re-registers and creates a new request — potential duplicate approvals |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | `ApprovalRequest.expires_at` is set at creation; `decide()` rejects decisions on expired requests |
| **Recommended hardening** | Add escalation: if no decision within 24h, re-alert on PagerDuty at HIGH priority; at 6 days, escalate to `admin` role; provide a CLI command `mtgs approvals list --pending` to make the queue visible; track `time-to-decision` as a governance KPI |

---

### 5.2 Role Escalation Bypass

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | API caller presents a JWT or API key claiming `reviewer` role for an account that should only have `developer` |
| **Effect** | Unauthorized approval of a CRITICAL conflict; tool becomes active without proper sign-off |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | RBAC enforced at HTTP layer (FastAPI dependency) AND inside `ApprovalService.decide()` — double enforcement; every decision produces an `AuditEntry` |
| **Recommended hardening** | Integrate with an external IdP (Azure AD / Entra ID) for role assignment rather than embedding roles in JWT claims; add anomaly detection: alert when the same user both registers a tool AND approves its own conflict within a short window |

---

### 5.3 In-Process Approval Store Lost on Restart

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | `ApprovalService._store` is an in-process dict; a process restart clears all pending approvals |
| **Effect** | All pending approval requests disappear; tools that were blocked become untracked |
| **Severity** | 🔴 CRITICAL in production |
| **Current mitigation** | This is a known v1 limitation (in-process store is acceptable for testing/dev) |
| **Recommended hardening** | Persist `ApprovalRequest` objects to a PostgreSQL `approvals` table (ORM model + Alembic migration); this is the **highest priority hardening item** for production readiness |

---

## 6. Audit Log

### 6.1 Audit Logger Lost on Process Restart

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | `AuditLogger._entries` is in-process memory; a crash or deploy loses all entries not yet exported |
| **Effect** | Governance audit trail has gaps; compliance requirements may be violated |
| **Severity** | 🔴 CRITICAL in production |
| **Current mitigation** | `AuditEntry` is marked `@dataclass(frozen=True)` — any attempt to mutate a field raises `FrozenInstanceError` (immutability is enforced at the Python level, not just by convention); `AuditLogger` already has a `_persist(entry)` async hook method designed explicitly for a production storage override — the docstring reads *"Hook for production persistence (DB / event bus / log aggregator). Default no-op — override in a subclass or inject a storage backend."*; CEF and JSON export endpoints exist so entries can be streamed out on demand |
| **Recommended hardening** | Implement the `_persist()` hook: write each `AuditEntry` to a PostgreSQL `audit_log` table in a separate append-only transaction immediately on creation; use DB row-level security (DENY UPDATE/DELETE) on that table; ship CEF lines to a SIEM in real-time via a background Celery task rather than on-demand export only |

---

### 6.2 CEF Export Injection

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | A tool name or description contains pipe (`\|`) or newline characters that break the CEF format |
| **Effect** | SIEM ingestion fails or misparses entries; audit record is corrupted in the SIEM |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | `to_cef()` constructs CEF strings from structured fields |
| **Recommended hardening** | Sanitize all user-supplied string values in `to_cef()` — escape `\|`, `\n`, `\r`; add a test with a tool name containing CEF-unsafe characters |

---

## 7. Notification Router

### 7.1 Slack Webhook Returns 4xx Permanently

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Slack webhook URL is rotated or workspace is deleted; every call returns 403/4xx |
| **Effect** | CRITICAL conflict alerts silently fail; on-call team not paged |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | `NotificationRouter` dispatches each channel concurrently with `asyncio.gather` and wraps every channel in its own `try/except Exception` — one channel failure never blocks others; `SlackNotifier`, `EmailNotifier`, and `PagerDutyNotifier` all have independent `try/except` blocks and log via `logger.exception()`; HTTP non-2xx responses are logged as `logger.warning("Slack webhook returned HTTP %d")`; `notifications_cb` circuit breaker opens after 3 failures (recovery 120s) to stop hammering a dead endpoint; `NotificationRouter` returns a `dict[str, bool]` of per-channel results so callers can inspect which channels succeeded |
| **Recommended hardening** | Log a `NOTIFICATION_FAILED` audit entry on every failed dispatch so the failure surfaces in the audit trail and SIEM; add a `/v1/api/notifications/test` health-ping endpoint; alert on `notifications_cb.state == OPEN` via the `/readiness` endpoint |

---

### 7.2 PagerDuty Dedup Key Collision

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Two different conflict pairs generate the same PagerDuty `dedup_key` |
| **Effect** | Second alert is silently merged into the first; incident appears to be the same event |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | Not yet implemented |
| **Recommended hardening** | Use `f"mtgs-{conflict_id}"` as the dedup key where `conflict_id` is the UUID from the DB; this guarantees uniqueness |

---

## 8. MCP Server Sync

### 8.1 MCP Server Returns Malformed Tool Payload

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | An MCP server returns a tool list with missing required fields (no `name`, invalid `inputSchema`) or the HTTP call itself fails |
| **Effect** | `remote_to_tooldef()` raises `KeyError` or `ValidationError`; entire sync for that server fails |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | `sync_mcp_server_task` in `workers/tasks.py` calls `resp.raise_for_status()` and wraps the full fetch in `try/except Exception` — logs the error and calls `self.retry(exc=exc)` with Celery's built-in retry back-off; `mcp_sync_cb` circuit breaker (threshold 3, recovery 60s) prevents repeated hammering of an unreachable server; tools not found in the DB are skipped with `logger.warning("MCPServer not found; skipping sync")` |
| **Recommended hardening** | Wrap `remote_to_tooldef()` in a per-tool try/except — skip malformed individual entries, log them, and continue syncing valid ones (currently a single bad payload aborts the whole server's sync); add a `SyncReport.malformed_count` field |

---

### 8.2 Ghost Tools After MCP Server Decommission

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | An MCP server is decommissioned but its tools remain `ACTIVE` in the MTGS registry |
| **Effect** | Stale tools keep generating conflicts with newly registered tools; false positives in analysis |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | `SyncReport.removed` detects tools present in DB but absent from live server |
| **Recommended hardening** | When a tool appears in `SyncReport.removed`, automatically set its status to `DEPRECATED` and fire a `TOOL_DELETED` audit entry; do not hard-delete (preserve history); exclude `DEPRECATED` tools from conflict detection queries |

---

## 9. Security Layer

### 9.1 JWT Secret Compromise

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | `JWT_SECRET_KEY` in `.env` is leaked via logs, error responses, or a compromised developer machine |
| **Effect** | Attacker can forge tokens for any role including `admin` and `ci-agent`; full system compromise |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | Secret loaded from environment variable (not hardcoded); `.env` is in `.gitignore` |
| **Recommended hardening** | Rotate to short-lived JWTs (15 min expiry) with refresh tokens; store `JWT_SECRET_KEY` in Azure Key Vault with automatic rotation; log all token issuances as audit events; implement JWT revocation via Redis blocklist |

---

### 9.2 API Key Brute Force

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Attacker brute-forces the `/v1/webhooks/ci-check` endpoint using enumerated API keys |
| **Effect** | Unauthorized CI gate bypass; malicious tools registered as approved |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | API key validation in `auth/security.py`; rate limiting middleware |
| **Recommended hardening** | Enforce rate limiting specifically on auth endpoints (e.g. 5 failures/minute → 15 min lockout); use 256-bit random API keys with `secrets.token_urlsafe(32)`; hash API keys in the DB (store only `sha256(key)`); add IP-based rate limiting at the ingress/WAF layer |

---

### 9.3 SQL Injection via Tool Metadata

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | A tool name or description contains SQL metacharacters passed into a raw query |
| **Effect** | Data exfiltration or schema corruption |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | All queries use SQLAlchemy ORM with parameterised bindings — no raw SQL string interpolation |
| **Recommended hardening** | Add an integration test with SQL-injection payloads in tool names/descriptions to confirm parameterisation; enable PostgreSQL `pg_audit` extension for query logging |

---

### 9.4 Sensitive Data in LLM Prompts

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Tool descriptions contain PII or proprietary schema field names that are sent verbatim to Azure OpenAI |
| **Effect** | Sensitive data leaves the enterprise perimeter; potential compliance violation (GDPR, SOC 2) |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | Azure OpenAI is used (data stays within the Azure tenant by default with Data Privacy addendum) |
| **Recommended hardening** | Add a pre-prompt scrubbing step that redacts patterns matching email, phone, SSN, credit card before sending to LLM; document data handling in the governance policy; allow opt-in prompt logging only (disabled by default) |

---

## 10. Operational / Configuration

### 10.1 Misconfigured Conflict Severity Thresholds

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | `CONFLICT_SCORE_CRITICAL_THRESHOLD` is set too low — every tool pair flags as CRITICAL |
| **Effect** | Approval queue floods; reviewers ignore alerts (alert fatigue); governance breaks down socially |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | Thresholds are environment-variable–driven (Pydantic Settings) |
| **Recommended hardening** | Add a dry-run mode that reports "this threshold would flag N% of existing tool pairs as CRITICAL" before applying; enforce a minimum threshold floor in `config.py` validation |

---

### 10.2 Vector Index Dimension Mismatch After Model Upgrade

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | Azure OpenAI embedding model is upgraded from `text-embedding-3-large` (3072 dims) to a future model with different dimensions; existing index becomes incompatible |
| **Effect** | ANN search returns garbage results or throws dimension errors; Stage 3 silently produces wrong similarity scores |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | `AZURE_OPENAI_EMBEDDING_MODEL` is configuration-driven |
| **Recommended hardening** | Store `embedding_model` and `embedding_dimensions` on each `Tool` record; validate on every ANN query that the model matches the index; create a migration script that re-embeds all tools and rebuilds the index atomically before switching models in production |

---

### 10.3 Alembic Migration Failure on Deploy

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | `alembic upgrade head` fails mid-migration (e.g. adding a NOT NULL column without a default on a populated table) |
| **Effect** | DB schema is in a partial state; application fails to start; rollback required |
| **Severity** | 🔴 CRITICAL |
| **Current mitigation** | Alembic versioned migrations with `downgrade()` functions |
| **Recommended hardening** | Always test migrations on a staging DB snapshot before production; use expand-contract pattern for dangerous changes (add nullable column → backfill → add NOT NULL constraint → drop old column); never run `alembic upgrade head` in the same Kubernetes init container that starts the app — run it as a separate pre-deploy job |

---

### 10.4 Environment Variable Missing at Startup

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | `AZURE_OPENAI_API_KEY` or `DATABASE_URL` missing from environment |
| **Effect** | App fails to start (Pydantic Settings raises `ValidationError`) or starts but crashes on first Azure call |
| **Severity** | 🟠 HIGH |
| **Current mitigation** | Pydantic `Settings` class validates all required fields at import time — startup fails immediately with a clear `ValidationError` listing every missing field; `validate_production_settings()` model validator additionally checks that `DEBUG=False`, `APP_SECRET_KEY` and `JWT_SECRET_KEY` are not left as `"change-me"` defaults in production — startup is rejected before the server ever accepts traffic |
| **Recommended hardening** | Add a `mtgs health --startup-check` CLI command that validates connectivity to PostgreSQL, Redis, Azure OpenAI, and Azure AI Search before the service is marked healthy; include this check in the K8s init container |

---

## 11. Data Integrity

### 11.1 Duplicate Tool Registration

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | The same tool is registered twice (network retry on timeout, or race condition between two CI pipelines) |
| **Effect** | Duplicate tools in the registry; doubled conflict detection results; inconsistent approval state |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | CI/CD gate at `/v1/webhooks/ci-check` performs pre-check before registration |
| **Recommended hardening** | Add a `UNIQUE(name, server_id, environment_id)` constraint to the `tools` table in the Alembic migration; on conflict return `200 OK` with the existing record rather than 409 to make registration idempotent |

---

### 11.2 Conflict Status Stuck in DETECTED

| Attribute | Detail |
|-----------|--------|
| **Failure mode** | A conflict is detected but its recommendation or approval is never processed (worker crash, bug) |
| **Effect** | Tool stays `BLOCKED` indefinitely; no visibility into why |
| **Severity** | 🟡 MEDIUM |
| **Current mitigation** | Approval TTL auto-expires after 7 days |
| **Recommended hardening** | Add a `stale_conflict_scan` beat task that finds conflicts with `status=DETECTED` and no linked approval after 1 hour — auto-creates the approval request and re-fires notifications |

---

## 12. Summary Risk Matrix

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Component            │ Top Failure Mode               │ Severity       │
├───────────────────────┼────────────────────────────────┼────────────────┤
│ Approval Store        │ In-process dict lost on restart│ 🔴 CRITICAL    │
│ Audit Logger          │ In-process list lost on restart│ 🔴 CRITICAL    │
│ JWT Secret            │ Key compromise / forged tokens │ 🔴 CRITICAL    │
│ PostgreSQL            │ Host unavailable               │ 🔴 CRITICAL    │
│ Embedding Model       │ Dimension mismatch on upgrade  │ 🔴 CRITICAL    │
│ Alembic Migration     │ Partial migration on deploy    │ 🔴 CRITICAL    │
│ Role Escalation       │ Unauthorised approval          │ 🔴 CRITICAL    │
│ Azure OpenAI          │ Rate limit / outage            │ 🟠 HIGH        │
│ Azure AI Search       │ Index unavailable              │ 🟠 HIGH        │
│ Celery Worker         │ Dies mid-task (zombie run)     │ 🟠 HIGH        │
│ Slack/PagerDuty       │ Webhook 4xx — silent fail      │ 🔴 CRITICAL    │
│ Stage 4 Simulation    │ LLM hallucination / bias       │ 🟠 HIGH        │
│ Stage 3 Embeddings    │ Stale vectors after tool update│ 🟠 HIGH        │
│ Sensitive Data        │ PII in LLM prompts             │ 🟠 HIGH        │
│ Redis                 │ Crash drops queued tasks       │ 🔴 CRITICAL    │
│ MCP Sync              │ Malformed server payload       │ 🟡 MEDIUM      │
│ CEF Export            │ Pipe/newline injection         │ 🟠 HIGH        │
│ Duplicate Tools       │ Race-condition re-registration │ 🟡 MEDIUM      │
│ Celery Beat           │ Scheduler process crash        │ 🟡 MEDIUM      │
│ API Key Brute Force   │ Enumerated key bypass          │ 🔴 CRITICAL    │
└───────────────────────────────────────────────────────────────────────-─┘
```

---

## 13. Priority Hardening Backlog

The following are ordered by **risk × implementation effort** — highest impact, lowest effort first:

| Priority | Item | Effort |
|----------|------|--------|
| **P0** | Persist `ApprovalRequest` to PostgreSQL (replace in-process dict) | Medium |
| **P0** | Persist `AuditEntry` to PostgreSQL append-only table | Medium |
| **P0** | Add `UNIQUE(name, server_id, environment_id)` constraint on `tools` | Low |
| **P1** | CEF output sanitisation (escape `\|`, `\n`) | Low |
| **P1** | PagerDuty dedup key = `f"mtgs-{conflict_id}"` | Low |
| **P1** | `NOTIFICATION_FAILED` audit entry on dispatch failure | Low |
| **P1** | `embedding_model` + `embedding_updated_at` on `Tool` model | Low |
| **P2** | Exponential back-off before circuit opens on Azure OpenAI | Medium |
| **P2** | Redis embedding cache (TTL 24h, keyed on fingerprint hash) | Medium |
| **P2** | Watchdog beat task for zombie `AnalysisRun` records | Low |
| **P2** | Celery `task_soft_time_limit` + `task_time_limit` | Low |
| **P3** | Azure AD / Entra ID IdP integration for RBAC | High |
| **P3** | pgvector fallback for ANN search | High |
| **P3** | Approval escalation (24h → PagerDuty HIGH, 6d → admin) | Medium |
