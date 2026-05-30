# ─────────────────────────────────────────────────────────────────────────────
# MTGS — Developer Makefile
# Usage: make <target>
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help install dev-up dev-down migrate api worker-analysis worker-simulation \
        test test-unit test-integration test-cov lint typecheck format \
        bench clean reset logs

# Default Python / venv
PYTHON   := python3
VENV     := .venv
PIP      := $(VENV)/bin/pip
PYTEST   := $(VENV)/bin/pytest
UVICORN  := $(VENV)/bin/uvicorn
CELERY   := $(VENV)/bin/celery
ALEMBIC  := $(VENV)/bin/alembic
RUFF     := $(VENV)/bin/ruff
MYPY     := $(VENV)/bin/mypy
LOCUST   := $(VENV)/bin/locust

COMPOSE  := docker compose -f docker/docker-compose.yml

# ─────────────────────────────────────────────────────────────────────────────
# Help
# ─────────────────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

install: ## Create venv and install all dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	@echo "\n✅  Dependencies installed. Run 'make dev-up' to start the stack."

# ─────────────────────────────────────────────────────────────────────────────
# Docker (Postgres + Redis only — no Azure needed for Tier 1/2 testing)
# ─────────────────────────────────────────────────────────────────────────────

dev-up: ## Start Postgres + Redis via Docker Compose
	$(COMPOSE) up -d db redis
	@echo "⏳  Waiting for Postgres to be ready..."
	@until $(COMPOSE) exec db pg_isready -U mtgs_user -d mtgs_dev > /dev/null 2>&1; do sleep 1; done
	@echo "✅  Postgres + Redis are up."

dev-down: ## Stop and remove Docker containers
	$(COMPOSE) down

dev-up-full: ## Start full stack (API + workers) via Docker Compose
	$(COMPOSE) up -d
	@echo "✅  Full stack started. API → http://localhost:8000"

logs: ## Tail Docker logs
	$(COMPOSE) logs -f

# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

migrate: ## Run Alembic migrations (requires Postgres to be up)
	$(ALEMBIC) upgrade head
	@echo "✅  Migrations applied."

migrate-down: ## Rollback one migration step
	$(ALEMBIC) downgrade -1

migrate-status: ## Show current migration state
	$(ALEMBIC) current

# ─────────────────────────────────────────────────────────────────────────────
# Run locally (outside Docker — Tier 2 mode)
# ─────────────────────────────────────────────────────────────────────────────

api: ## Run FastAPI dev server (reload on change)
	$(UVICORN) mtgs.main:app --reload --host 0.0.0.0 --port 8000

worker-analysis: ## Run Celery analysis + embeddings worker
	$(CELERY) -A mtgs.workers.celery_app worker \
		-Q analysis,embeddings --loglevel=info --concurrency=4

worker-simulation: ## Run Celery simulation worker
	$(CELERY) -A mtgs.workers.celery_app worker \
		-Q simulation --loglevel=info --concurrency=2

beat: ## Run Celery beat scheduler (periodic tasks)
	$(CELERY) -A mtgs.workers.celery_app beat --loglevel=info

flower: ## Run Celery Flower task monitor at http://localhost:5555
	$(CELERY) -A mtgs.workers.celery_app flower --port=5555

# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

test: test-unit ## Alias for test-unit (no external deps)

test-unit: ## Run all unit tests (196 tests, fully mocked, no Docker needed)
	$(PYTEST) tests/unit/ -v --tb=short

test-cov: ## Run unit tests with coverage report (gate: ≥80% on mtgs/core)
	$(PYTEST) tests/unit/ \
		--cov=mtgs/core \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-fail-under=80 \
		-q
	@echo "✅  Coverage report → htmlcov/index.html"

test-integration: ## Run integration tests (requires: make dev-up migrate)
	$(PYTEST) tests/integration/ -v --tb=short

test-all: ## Run unit + integration tests
	$(PYTEST) tests/unit/ tests/integration/ -v --tb=short

# ─────────────────────────────────────────────────────────────────────────────
# Code quality
# ─────────────────────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	$(RUFF) check mtgs/ cli/ tests/

format: ## Auto-format with ruff
	$(RUFF) format mtgs/ cli/ tests/

typecheck: ## Run mypy type checker
	$(MYPY) mtgs/

check: lint typecheck ## Run lint + typecheck together

# ─────────────────────────────────────────────────────────────────────────────
# Benchmarks
# ─────────────────────────────────────────────────────────────────────────────

bench: ## Run Locust headless benchmark (50 users, 60s) — API must be running
	$(LOCUST) -f benchmarks/locustfile.py \
		--headless -u 50 -r 10 -t 60s \
		--host http://localhost:8000 \
		--html benchmarks/report.html
	@echo "✅  Report → benchmarks/report.html"

bench-ui: ## Launch Locust web UI at http://localhost:8089
	$(LOCUST) -f benchmarks/locustfile.py --host http://localhost:8000

# ─────────────────────────────────────────────────────────────────────────────
# Quick smoke test (curl-based, no pytest)
# ─────────────────────────────────────────────────────────────────────────────

smoke: ## Smoke test the running API with curl
	@echo "\n── Health ──────────────────────────────"
	@curl -s http://localhost:8000/health | python3 -m json.tool
	@echo "\n── Readiness ───────────────────────────"
	@curl -s http://localhost:8000/readiness | python3 -m json.tool
	@echo "\n── OpenAPI docs ────────────────────────"
	@curl -s -o /dev/null -w "OpenAPI JSON: HTTP %{http_code}\n" http://localhost:8000/openapi.json
	@echo "\n✅  Smoke test complete."

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

clean: ## Remove build artefacts, caches, coverage files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache  -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml dist/ build/
	@echo "✅  Clean."

reset: dev-down clean ## Stop containers + clean everything
	$(COMPOSE) down -v   # also removes named volumes (wipes DB data)
	@echo "✅  Full reset complete."

dashboard-install: ## Install dashboard npm dependencies
	cd dashboard && npm install

dashboard-dev: ## Start dashboard dev server at http://localhost:5173
	cd dashboard && npm run dev

dashboard-build: ## Build dashboard for production
	cd dashboard && npm run build
