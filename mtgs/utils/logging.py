"""
Structured JSON logging via structlog.

Usage:
    from mtgs.utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("tool_registered", tool_id=str(tool.id), name=tool.name)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from mtgs.config import Environment, settings


def configure_logging() -> None:
    """
    Configure structlog for structured JSON output in production,
    pretty console output in development.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.app_env in (Environment.PRODUCTION, Environment.STAGING):
        # JSON lines for log aggregators (Azure Monitor, Datadog, Grafana)
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-friendly coloured output for local dev
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.app_log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so third-party libs (SQLAlchemy, Celery, etc.)
    # flow through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(settings.app_log_level),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    return structlog.get_logger(name)
