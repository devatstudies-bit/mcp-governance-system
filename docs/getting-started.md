# Getting Started

This guide gets you from zero to a running MTGS instance with your first tool registered and conflict-checked.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | `python --version` |
| Docker | 24+ | For local DB + Redis |
| Azure OpenAI | — | `text-embedding-3-large` deployment required |
| Azure AI Search | — | Standard tier or higher (for vector search) |

> **Tip:** You can run Stages 1 and 2 (lexical + schema conflict detection) without Azure credentials. Only Stage 3 (semantic) and Stage 4 (simulation) require external services.

---

## 1. Install

```bash
git clone https://github.com/your-org/mtgs.git
cd mtgs

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Verify CLI is available
mtgs --help
```

---

## 2. Configure

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```bash
# Required — generate a random secret
APP_SECRET_KEY=<random-32-char-string>
JWT_SECRET_KEY=<random-64-char-string>

# Database (local Docker — already set correctly)
DATABASE_URL=postgresql+asyncpg://mtgs_user:mtgs_password@localhost:5432/mtgs_dev

# Redis (local Docker — already set correctly)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Azure OpenAI (required for Stage 3 semantic analysis)
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# Azure AI Search (required for Stage 3 ANN search)
AZURE_SEARCH_ENDPOINT=https://your-search.search.windows.net
AZURE_SEARCH_API_KEY=<your-admin-key>
AZURE_SEARCH_INDEX_NAME=mtgs-tool-embeddings
```

See [Configuration Reference](configuration.md) for all options.

---

## 3. Start Infrastructure

```bash
# Start PostgreSQL and Redis
docker compose -f docker/docker-compose.yml up -d db redis

# Verify they're healthy
docker compose -f docker/docker-compose.yml ps
```

Expected output:
```
NAME              STATUS
mtgs-db-1         Up (healthy)
mtgs-redis-1      Up (healthy)
```

---

## 4. Run Database Migrations

```bash
alembic upgrade head
```

This creates all tables, indexes, and the `pgvector` extension. You should see:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
```

---

## 5. Start the API

```bash
uvicorn mtgs.main:app --reload --port 8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
# → {"status": "ok", "version": "1.0.0"}
```

Interactive API docs (development only):
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 6. Start Celery Workers

Open two additional terminal windows:

**Analysis + Embeddings worker:**
```bash
celery -A mtgs.workers.celery_app worker \
  --loglevel=info \
  -Q analysis,embeddings \
  --concurrency=4
```

**Simulation worker:**
```bash
celery -A mtgs.workers.celery_app worker \
  --loglevel=info \
  -Q simulation \
  --concurrency=2
```

---

## 7. Create Your First API Key

```bash
# Create an admin API key
curl -X POST http://localhost:8000/v1/auth/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "dev-key", "role": "ADMIN"}'
```

Response:
```json
{
  "key_id": "key_abc123",
  "raw_key": "mtgs_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "role": "ADMIN",
  "note": "Store this key — it will not be shown again."
}
```

Export it for CLI use:
```bash
export MTGS_API_KEY=mtgs_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
export MTGS_API_URL=http://localhost:8000
```

---

## 8. Create an Environment

Environments are scoped registries (`dev`, `staging`, `prod`).

```bash
curl -X POST http://localhost:8000/v1/environments \
  -H "X-API-Key: $MTGS_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "dev",
    "policy": {
      "max_severity_to_block": "HIGH",
      "auto_approve_below": "LOW"
    }
  }'
```

Note the `env_id` from the response — you'll use it in subsequent calls.

---

## 9. Register Your First Tool

Create a tool definition file:

```bash
cat > my-tool.json << 'EOF'
{
  "name": "create_jira_issue",
  "description": "Creates a new issue in Jira for the specified project. Use this tool when the user wants to create a bug report, feature request, or task in the Jira project management system.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project_key": {
        "type": "string",
        "description": "The Jira project key (e.g., PROJ)"
      },
      "summary": {
        "type": "string",
        "description": "One-line summary of the issue"
      },
      "issue_type": {
        "type": "string",
        "enum": ["Bug", "Task", "Story", "Epic"],
        "description": "Type of Jira issue to create"
      }
    },
    "required": ["project_key", "summary"]
  }
}
EOF
```

**Dry-run check first:**
```bash
mtgs tools check --file my-tool.json --env dev
```

Output (no conflicts):
```
✓ PASSED  No conflicts detected for create_jira_issue

  Stage 1 (Lexical)   0ms    0 conflicts
  Stage 2 (Schema)    8ms    0 conflicts
  Stage 3 (Semantic)  1.2s   0 conflicts

Risk Score: 0 / 100
```

**Register it:**
```bash
mtgs tools register --file my-tool.json --server jira-mcp --env dev
```

```
✓ Registered  create_jira_issue  (tool_id: abc-123)
  Full analysis running in background (run_id: run-xyz)
  Dashboard: http://localhost:3000/runs/run-xyz
```

---

## 10. Simulate a Conflict

Now register a second tool that intentionally overlaps:

```bash
cat > conflicting-tool.json << 'EOF'
{
  "name": "create_ticket",
  "description": "Creates a new ticket or task in the project management system for tracking bugs, features, and work items.",
  "input_schema": {
    "type": "object",
    "properties": {
      "project": { "type": "string" },
      "title": { "type": "string" },
      "type": { "type": "string" }
    },
    "required": ["project", "title"]
  }
}
EOF

mtgs tools check --file conflicting-tool.json --env dev
```

Output:
```
✗ FAILED  2 conflicts detected for create_ticket

  Stage 1 (Lexical)    0ms   0 conflicts
  Stage 2 (Schema)     9ms   0 conflicts
  Stage 3 (Semantic)   1.4s  1 conflict

  ┌─────────────────────────────────────────────────────────────────┐
  │ HIGH  SEMANTIC_OVERLAP                                          │
  │ create_ticket ↔ create_jira_issue                               │
  │ Cosine similarity: 0.87                                         │
  │                                                                 │
  │ Recommendation: Narrow scope in description to specify the      │
  │ exact system. Example: "Creates a new ticket in [System Name]..." │
  └─────────────────────────────────────────────────────────────────┘

Risk Score: 20 / 100
```

---

## Full Docker Development Stack

To run the full stack (API + workers + DB + Redis) in one command:

```bash
docker compose -f docker/docker-compose.yml up -d
```

This starts:
- `db` — PostgreSQL 16 on port 5432
- `redis` — Redis 7 on port 6379
- `api` — FastAPI on port 8000 (with hot reload)
- `worker-analysis` — Celery worker for analysis queue
- `worker-simulation` — Celery worker for simulation queue

---

## Running Tests

```bash
# Unit tests only (no external services needed)
pytest tests/unit -v

# Unit tests with coverage
pytest tests/unit --cov=mtgs/core --cov-report=html
open htmlcov/index.html

# Integration tests (requires running DB + Redis)
pytest tests/integration -v

# All tests
pytest -v
```

---

## Next Steps

- [API Reference](api-reference.md) — full endpoint documentation
- [Conflict Detection](conflict-detection.md) — understand how conflicts are scored
- [CLI Reference](cli.md) — all `mtgs` commands
- [Dashboard](dashboard.md) — the React governance dashboard
- [Deployment](deployment.md) — production deployment on Azure
