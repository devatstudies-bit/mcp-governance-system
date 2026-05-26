# ADR-001: Python + FastAPI as the API Framework

**Status:** Accepted  
**Date:** 2025-05  
**Deciders:** AI Platform Team

---

## Context

MTGS needs an HTTP API that:
- Serves the governance dashboard, CLI, and CI/CD webhooks
- Performs async I/O (database queries, Redis, Azure AI calls) without blocking
- Validates complex input shapes (tool definitions, JSON Schema payloads)
- Generates self-documenting OpenAPI specs for integration consumers
- Integrates naturally with Python ML/NLP tooling (embeddings, text processing)

The core conflict detection logic is Python-native (text processing, numpy for cosine similarity). The API framework must run in the same runtime to avoid serialization overhead between services.

---

## Decision Drivers

- **Async I/O:** Analysis pipelines make many concurrent outbound calls (Azure AI Search, Azure OpenAI, Anthropic API). Blocking I/O would create unacceptable latency.
- **Type safety:** Tool definitions are complex, nested schemas. Pydantic provides compile-time and runtime validation with clear error messages.
- **Developer velocity:** FastAPI's automatic OpenAPI generation means the API reference stays in sync with the code.
- **Ecosystem:** Python owns the embeddings and NLP ecosystem. Using a Python framework means no cross-language serialization.

---

## Options Considered

| Option | Async | Type Safety | OpenAPI | Ecosystem Fit |
|---|---|---|---|---|
| **FastAPI + Python** | ✅ Native (asyncio) | ✅ Pydantic v2 | ✅ Auto-generated | ✅ Best |
| Flask + Python | ⚠️ Extension-based | ⚠️ Manual | ⚠️ Extension | ✅ Good |
| Node.js + Express | ✅ Native | ⚠️ TypeScript only | ⚠️ Extension | ❌ Poor (NLP) |
| Go (gin/chi) | ✅ Native | ✅ Strong | ⚠️ Manual | ❌ Poor (NLP) |
| Django REST Framework | ⚠️ ASGI optional | ⚠️ Serializers | ⚠️ Extension | ✅ Good |

---

## Decision

**FastAPI 0.115+ with Python 3.12**, Pydantic v2, and uvicorn.

Specific choices within this:
- `orjson` for JSON serialization (faster, handles UUID/datetime natively)
- `structlog` for structured JSON logging
- `SQLAlchemy 2.0` async mode for database access
- `asyncpg` as the PostgreSQL async driver

---

## Consequences

**Positive:**
- Single Python runtime for API + conflict detection + workers — no IPC
- Auto-generated OpenAPI docs always match implementation
- Pydantic validation errors are structured and debuggable
- Full async support enables high concurrency with minimal threads

**Negative:**
- Python has higher per-request overhead than Go/Rust for pure compute
- The GIL limits CPU-parallelism within a single process (mitigated by multiple uvicorn workers)
- FastAPI/Starlette async testing is more complex than synchronous testing (requires `pytest-asyncio`)

**Mitigation:**
- CPU-heavy analysis (embedding similarity, Stage 1/2 detection) runs in Celery workers, not in the API request path
- Multiple uvicorn workers (`--workers 4`) provide process-level parallelism for I/O-bound endpoints
