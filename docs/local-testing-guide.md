# Local Testing Guide

> **tl;dr** — Don't use SQLite. Use Docker for Postgres + Redis, run unit tests immediately (no deps at all), and optionally add Azure credentials for full pipeline testing.

---

## Why not SQLite?

The `Environment` ORM model uses a PostgreSQL-specific `JSONB` column. SQLite will immediately throw:

```
CompileError: can't render element of type JSONB
```

All local testing uses **PostgreSQL via Docker** (single command, no install needed). The `docker-compose.yml` already has everything configured.

---

## Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.12+ | `python3 --version` |
| Docker Desktop | 24+ | `docker --version` |
| Make | any | `make --version` |

No Azure account needed for Tier 1 or Tier 2 testing.

---

## Tier 1 — Unit Tests (zero external dependencies)

Runs completely offline. All Azure OpenAI, Azure AI Search, Postgres, and Redis calls are `AsyncMock`ed.

```bash
# One-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run all 196 unit tests (~5s)
make test-unit

# With coverage report (gate: ≥80% on mtgs/core)
make test-cov
# Opens htmlcov/index.html for the HTML report
```

**What this covers:**
- Conflict detection pipeline (all 4 stages, mocked)
- Probe generator, impact simulator, recommendation engine
- Approval workflow state machine
- Audit log immutability
- Circuit breaker state transitions
- Notification router (Slack/Email/PagerDuty — all mocked)
- MCP server sync diff logic
- All REST API endpoint logic (DB mocked with AsyncMock)

---

## Tier 2 — API Smoke Test (Docker only, no Azure)

Stages 1+2 (lexical + schema conflict detection) work fully. Stages 3+4 (semantic + behavioral) will trip their circuit breakers and degrade gracefully — the API still responds correctly with partial results.

### Step 1 — Start Postgres + Redis

```bash
make dev-up
# Waits until Postgres passes the health-check, then exits
```

### Step 2 — Configure environment

```bash
cp .env.example .env
```

Edit `.env` — the minimum required values for Tier 2:

```bash
# .env (Tier 2 minimum — Azure keys left as placeholders)
APP_ENV=development
APP_SECRET_KEY=local-dev-secret-key-32chars-min
JWT_SECRET_KEY=local-dev-jwt-secret-64chars-minimum-length-here
DATABASE_URL=postgresql+asyncpg://mtgs_user:mtgs_password@localhost:5432/mtgs_dev
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Leave Azure values as placeholder — circuit breakers will handle gracefully
AZURE_OPENAI_API_KEY=placeholder
AZURE_OPENAI_ENDPOINT=https://placeholder.openai.azure.com
AZURE_SEARCH_ENDPOINT=https://placeholder.search.windows.net
AZURE_SEARCH_API_KEY=placeholder
```

### Step 3 — Run migrations

```bash
make migrate
# Applies alembic/versions/0001_initial_schema.py
# Creates all tables in the local Postgres
```

### Step 4 — Start the API

```bash
make api
# Uvicorn starts with --reload at http://localhost:8000
```

### Step 5 — Smoke test it

```bash
make smoke
# Hits /health, /readiness, /openapi.json — prints JSON responses
```

Or open **http://localhost:8000/docs** in a browser for the interactive Swagger UI.

### Step 6 — Try the CLI

```bash
# Check a tool definition for conflicts (dry-run, stages 1+2 only)
mtgs tools check --file my-tool.json --env <env-id>

# List conflicts
mtgs conflicts list --env <env-id>

# Health check
mtgs health
```

### What works vs what degrades in Tier 2

| Feature | Tier 2 Status | Reason |
|---------|---------------|--------|
| Tool registration (Stage 1+2) | ✅ Full | Pure Python, no Azure |
| Lexical conflict detection | ✅ Full | Pure Python |
| Schema conflict detection | ✅ Full | Pure Python |
| Approval workflow | ✅ Full | In-process, no Azure |
| Audit log + SIEM export | ✅ Full | In-process, no Azure |
| CI/CD webhook gate | ✅ Full | Stages 1+2 |
| Semantic conflict (Stage 3) | ⚡ Graceful | Azure circuit breaker OPEN after 5 retries |
| Behavioral simulation (Stage 4) | ⚡ Graceful | Azure circuit breaker OPEN |
| Recommendation engine | ⚡ Graceful | Returns `[]`, run continues |
| Notifications (Slack/PD) | ⚡ Graceful | No webhook URLs configured |
| MCP server sync | ⚡ Graceful | No live servers configured |

"⚡ Graceful" means the API returns a valid response — just with empty/partial data for the Azure-dependent fields.

---

## Tier 3 — Full Pipeline Test (Azure credentials required)

All 4 conflict detection stages, recommendation engine, and embedding search work end-to-end.

### Azure resources needed

| Resource | Tier | Estimated cost (dev) |
|----------|------|---------------------|
| Azure OpenAI | Standard | ~$1–5/month at dev scale |
| Azure AI Search | Basic | ~$25/month (lowest paid tier) |

Both are available in the Azure portal. Azure OpenAI requires a brief access request approval.

### Additional `.env` values to fill in

```bash
# Azure OpenAI
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o

# Azure AI Search
AZURE_SEARCH_ENDPOINT=https://<your-search>.search.windows.net
AZURE_SEARCH_API_KEY=<your-admin-key>
AZURE_SEARCH_INDEX_NAME=mtgs-tool-embeddings
```

### Azure AI Search index setup

The index needs to exist before the first embedding is stored. Either:

**Option A — Auto-create on first use** (if `AzureSearchClient` has `ensure_index()` logic)

**Option B — Create manually via Azure portal:**
```
Index name:   mtgs-tool-embeddings
Fields:
  - id          (Edm.String, key)
  - tool_id     (Edm.String, filterable)
  - vector      (Collection(Edm.Single), searchable, dimensions=3072, algorithm=hnsw)
  - content     (Edm.String, searchable)
```

### Run integration tests

```bash
# Requires: make dev-up + make migrate + Azure creds in .env
make test-integration
```

---

## Running Celery Workers Locally

Open three separate terminal windows:

```bash
# Terminal 1 — Analysis + embedding tasks
make worker-analysis

# Terminal 2 — Simulation tasks (LLM routing)
make worker-simulation

# Terminal 3 — Periodic beat scheduler (MCP sync every 15 min, conflict scan hourly)
make beat
```

Monitor tasks visually:

```bash
# Flower task dashboard at http://localhost:5555
make flower
```

---

## Load Testing

```bash
# API must be running first: make api
# Headless: 50 concurrent users, 60s run
make bench

# Interactive web UI at http://localhost:8089
make bench-ui
```

---

## Common Issues

### `asyncpg.exceptions.InvalidCatalogNameError: database "mtgs_dev" does not exist`

The DB container started but the database wasn't created. Run:

```bash
make dev-down && make dev-up && make migrate
```

### `Connection refused` on port 5432

Docker isn't running or the container hasn't started yet:

```bash
docker ps               # check container status
make dev-down dev-up    # restart
```

### `ModuleNotFoundError: No module named 'mtgs'`

The venv isn't activated or the package isn't installed:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### Circuit breaker OPEN immediately

Expected in Tier 2 (no Azure creds). The circuit opens after 5 failed Azure calls, then fail-fasts for 30s. Stages 1+2 still work. Check `/readiness` to see breaker states:

```bash
curl http://localhost:8000/readiness | python3 -m json.tool
```

### `alembic.util.exc.CommandError: Can't locate revision identified by 'head'`

Alembic can't find the versions folder. Run from the project root (where `alembic.ini` is):

```bash
cd /path/to/mtgs
make migrate
```

---

## Quick Reference

```bash
make install          # One-time: create venv + install deps
make dev-up           # Start Postgres + Redis
make migrate          # Apply DB migrations
make api              # Start FastAPI at :8000
make test-unit        # 196 tests, no deps, ~5s
make test-cov         # Tests + coverage gate (≥80%)
make smoke            # Quick curl health check
make lint             # ruff linter
make typecheck        # mypy
make bench            # Locust load test
make clean            # Remove cache + build artefacts
make reset            # Full wipe (containers + volumes + caches)
```
