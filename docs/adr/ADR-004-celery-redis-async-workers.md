# ADR-004: Celery + Redis for Async Job Processing

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team

---

## Context

The full conflict analysis pipeline (Stages 3 + 4) can take 10–60 seconds. Running this synchronously in the API request path would:
1. Block the HTTP connection for an unacceptable duration
2. Prevent tool registrations from returning quickly to CI/CD pipelines
3. Create cascading timeouts when multiple registrations arrive simultaneously

The system needs an async job queue that can:
- Accept jobs from the FastAPI application
- Execute them in isolated worker processes
- Report status back to the API for polling
- Retry on transient failures (Azure OpenAI rate limits, network errors)
- Separate simulation jobs from analysis jobs (different concurrency limits)

---

## Decision Drivers

- **Reliability:** Jobs must not be lost on worker crash; at-least-once delivery
- **Separate queues:** Simulation workers need lower concurrency (Anthropic API rate limits) than analysis workers
- **Python ecosystem:** Worker code must import and use the same Python modules as the API
- **Simplicity:** No additional message broker beyond what we already have (Redis)
- **Observability:** Job status queryable via the API (`analysis_runs.status`)

---

## Options Considered

| Option | At-Least-Once | Separate Queues | Python Native | Existing Infra | Notes |
|---|---|---|---|---|---|
| **Celery + Redis** | ✅ | ✅ | ✅ | ✅ (Redis already needed) | Industry standard |
| FastAPI BackgroundTasks | ❌ | ❌ | ✅ | ✅ | In-process, no retry, dies with app |
| Azure Service Bus | ✅ | ✅ | ⚠️ | ❌ New service | Adds complexity, overkill |
| RQ (Redis Queue) | ✅ | ✅ | ✅ | ✅ | Simpler than Celery, less ecosystem |
| Dramatiq + Redis | ✅ | ✅ | ✅ | ✅ | Good alternative but smaller ecosystem |

---

## Decision

**Celery 5.4+ with Redis broker.**

Redis is already required for embedding cache, so there is no additional infrastructure cost. Celery's retry policies, queue routing, and concurrency controls are mature and well-documented.

**Queue design:**

| Queue | Workers | Concurrency | Tasks |
|---|---|---|---|
| `analysis` | 2 replicas × 4 | 8 total | `run_conflict_analysis_task`, all Stages 1–3 |
| `simulation` | 1 replica × 2 | 2 total | `run_impact_simulation_task`, Stage 4 (LLM-bound) |
| `embeddings` | 2 replicas × 4 | 8 total | `compute_tool_embedding_task`, batch embedding |

Simulation concurrency is intentionally low (2) to respect Anthropic API rate limits. This queue can scale independently of the analysis queue.

**Retry policy:**
```python
@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,   # 60s, 120s, 240s (exponential via retry_backoff)
    retry_backoff=True,
    autoretry_for=(Exception,),
)
```

---

## Consequences

**Positive:**
- Tool registration API returns in < 500ms; full analysis continues asynchronously
- Worker crashes don't lose jobs (Redis persistence)
- Separate queues allow independent scaling of analysis vs simulation capacity
- Celery Flower (optional) provides a web UI for monitoring task queues

**Negative:**
- Workers are separate processes — they must be deployed and scaled independently
- Celery's Redis-backed result backend has a TTL (results expire after 24h by default)
- Job status polling adds one API call overhead vs. WebSocket push (WebSocket push planned for dashboard in Phase 3)
- Celery serialization (`json` mode) means all task arguments must be JSON-serializable — large payloads (tool set snapshots) are written to DB first, and only the `analysis_run_id` is passed to the task
