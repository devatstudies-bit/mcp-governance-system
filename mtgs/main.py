"""
MTGS FastAPI application entry point.

Startup order:
  1. Configure structured logging
  2. Create FastAPI app with lifespan
  3. Register middleware (order matters — outermost first)
  4. Register exception handlers
  5. Include routers
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import orjson
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from mtgs.api.middleware import AccessLogMiddleware, RequestIDMiddleware
from mtgs.api.v1 import analysis_runs, approvals, audit_logs, conflicts, health, tools, webhooks
from mtgs.config import settings
from mtgs.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown logic."""
    configure_logging()
    logger.info(
        "mtgs_starting",
        version=settings.app_version,
        env=settings.app_env,
        **settings.model_dump_safe(),
    )

    # Verify DB connectivity on startup
    from mtgs.database import check_db_health
    if not await check_db_health():
        logger.warning("database_unreachable_on_startup")

    yield

    logger.info("mtgs_shutting_down")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="MCP Tool Governance System",
        description=(
            "Governance layer for MCP tool registries — detects conflicts, "
            "predicts LLM routing failures, and recommends definition improvements."
        ),
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
        default_response_class=_ORJSONResponse,
    )

    # ── Middleware (registered outermost → innermost) ──────────────────────────
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ─────────────────────────────────────────────────────
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return _ORJSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail, "request_id": request.headers.get("X-Request-ID")},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return _ORJSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Validation error",
                "detail": exc.errors(),
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            path=request.url.path,
        )
        return _ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "request_id": request.headers.get("X-Request-ID"),
            },
        )

    # ── Routers ────────────────────────────────────────────────────────────────
    prefix = "/v1"
    app.include_router(health.router)                            # /health, /readiness
    app.include_router(health.router, prefix=prefix)            # /v1/environments/{id}/health
    app.include_router(tools.router, prefix=prefix)             # /v1/environments/{id}/tools
    app.include_router(conflicts.router, prefix=prefix)         # /v1/environments/{id}/conflicts
    app.include_router(webhooks.router, prefix=prefix)          # /v1/webhooks/ci-check
    app.include_router(analysis_runs.router, prefix=f"{prefix}/api")  # /v1/api/analysis-runs
    app.include_router(approvals.router, prefix=f"{prefix}/api")      # /v1/api/approvals
    app.include_router(audit_logs.router, prefix=f"{prefix}/api")    # /v1/api/audit-logs

    return app


# ── Custom JSON response using orjson (faster + handles UUID/datetime) ─────────

class _ORJSONResponse(JSONResponse):
    media_type = "application/json"

    def render(self, content) -> bytes:
        return orjson.dumps(content, option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_UUID)


# Module-level app instance
app = create_app()
