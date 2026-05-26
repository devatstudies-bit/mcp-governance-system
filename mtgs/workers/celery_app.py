"""Celery application configuration."""

from __future__ import annotations

from celery import Celery

from mtgs.config import settings

celery_app = Celery(
    "mtgs",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["mtgs.workers.tasks"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Routing
    task_routes={
        "mtgs.workers.tasks.run_conflict_analysis_task": {"queue": "analysis"},
        "mtgs.workers.tasks.run_impact_simulation_task": {"queue": "simulation"},
        "mtgs.workers.tasks.generate_embeddings_task": {"queue": "embeddings"},
        "mtgs.workers.tasks.sync_mcp_server_task": {"queue": "analysis"},
    },
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time (LLM calls are expensive)
    # Retry defaults
    task_max_retries=3,
    task_default_retry_delay=10,
    # Dead-letter: tasks that fail all retries go to a separate queue for inspection
    task_dead_letter_exchange="mtgs.dlx",
    # Result expiry
    result_expires=3600,
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # ── Periodic beat schedule ──────────────────────────────────────────
    beat_schedule={
        # Sync all registered MCP servers every 15 minutes
        "sync-all-mcp-servers": {
            "task": "mtgs.workers.tasks.sync_all_mcp_servers_task",
            "schedule": 900,  # seconds
            "options": {"queue": "analysis"},
        },
        # Re-run conflict analysis on all environments every hour
        "hourly-conflict-scan": {
            "task": "mtgs.workers.tasks.scheduled_conflict_scan_task",
            "schedule": 3600,
            "options": {"queue": "analysis"},
        },
    },
)
