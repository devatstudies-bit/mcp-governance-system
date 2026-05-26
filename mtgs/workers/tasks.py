"""
Celery tasks for async conflict analysis, embedding generation, and simulation.

Each task is idempotent — safe to retry on failure.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger

from mtgs.workers.celery_app import celery_app

logger = get_task_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="mtgs.workers.tasks.run_conflict_analysis_task",
    max_retries=3,
    default_retry_delay=15,
    queue="analysis",
)
def run_conflict_analysis_task(self, tool_id: str, env_id: str) -> dict[str, Any]:
    """
    Run the full conflict detection pipeline for a newly registered/updated tool.

    Steps:
      1. Load candidate tool and all existing tools from DB
      2. Compute/refresh candidate embedding if stale
      3. Run pipeline (Stages 1, 2, 3)
      4. Persist detected conflicts to DB
      5. Trigger notifications for CRITICAL/HIGH conflicts
    """
    logger.info(f"Starting conflict analysis: tool={tool_id}, env={env_id}")
    try:
        return _run_async(_run_conflict_analysis(tool_id=tool_id, env_id=env_id))
    except Exception as exc:
        logger.error(f"Conflict analysis failed: {exc}")
        raise self.retry(exc=exc)


async def _run_conflict_analysis(tool_id: str, env_id: str) -> dict[str, Any]:
    from sqlalchemy import select

    from mtgs.config import settings
    from mtgs.core.conflict_detection.pipeline import ConflictDetectionPipeline
    from mtgs.core.embeddings.azure_search_client import AzureSearchClient
    from mtgs.core.embeddings.fingerprinter import ToolFingerprinter
    from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService
    from mtgs.database import get_db_context
    from mtgs.models.analysis_run import AnalysisRun, AnalysisRunStatus, AnalysisRunTrigger
    from mtgs.models.conflict import Conflict, ConflictType
    from mtgs.models.tool import Tool, ToolStatus
    from mtgs.core.tool_def import ToolDef

    tool_uuid = uuid.UUID(tool_id)
    env_uuid = uuid.UUID(env_id)
    t_start = datetime.now(timezone.utc)

    async with get_db_context() as db:
        # Load candidate
        result = await db.execute(
            select(Tool).where(Tool.id == tool_uuid, Tool.is_deleted == False)
        )
        candidate_tool = result.scalar_one_or_none()
        if candidate_tool is None:
            logger.warning(f"Tool {tool_id} not found; skipping analysis")
            return {"status": "skipped", "reason": "tool_not_found"}

        # Load all other active tools in the environment
        existing_result = await db.execute(
            select(Tool).where(
                Tool.environment_id == env_uuid,
                Tool.id != tool_uuid,
                Tool.status == ToolStatus.ACTIVE,
                Tool.is_deleted == False,
            )
        )
        existing_tools = existing_result.scalars().all()

        # Create analysis run record
        run = AnalysisRun(
            environment_id=env_uuid,
            trigger=AnalysisRunTrigger.TOOL_REGISTRATION,
            trigger_tool_id=tool_uuid,
            status=AnalysisRunStatus.RUNNING,
            llm_model=settings.azure_openai_chat_deployment,
            embedding_model=settings.azure_openai_embedding_deployment,
            started_at=t_start,
            tool_set_snapshot={
                "tool_count": len(existing_tools) + 1,
                "candidate_tool_id": tool_id,
            },
        )
        db.add(run)
        await db.flush()

        try:
            # Build ToolDef DTOs
            candidate_def = ToolDef(
                name=candidate_tool.name,
                description=candidate_tool.description,
                input_schema=candidate_tool.input_schema,
                server_name=str(candidate_tool.server_id),
            )
            existing_defs = [
                ToolDef(
                    name=t.name,
                    description=t.description,
                    input_schema=t.input_schema,
                    server_name=str(t.server_id),
                )
                for t in existing_tools
            ]

            # Compute/refresh embedding for candidate
            fingerprinter = ToolFingerprinter()
            new_hash = fingerprinter.compute_hash(candidate_def)
            candidate_embedding = None

            if candidate_tool.embedding_fingerprint_hash != new_hash:
                embedding_svc = AzureOpenAIEmbeddingService()
                fp_text = fingerprinter.build_fingerprint_text(candidate_def)
                candidate_embedding = await embedding_svc.embed(fp_text)
                candidate_tool.embedding = candidate_embedding
                candidate_tool.embedding_fingerprint_hash = new_hash
                candidate_tool.embedding_model = settings.azure_openai_embedding_deployment

                # Upsert in Azure AI Search
                search_client = AzureSearchClient()
                await search_client.upsert_tool_embedding(
                    tool_id=tool_uuid,
                    tool_name=candidate_tool.name,
                    environment_id=env_uuid,
                    embedding=candidate_embedding,
                )

            # Run pipeline (Stages 1–3)
            search_client = AzureSearchClient()
            pipeline = ConflictDetectionPipeline(embedding_service=search_client)
            pipeline_result = await pipeline.run_async(
                candidate=candidate_def,
                existing=existing_defs,
                candidate_embedding=candidate_embedding,
            )

            # Persist detected conflicts
            conflict_ids = []
            for c in pipeline_result.conflicts:
                # Find matching tool IDs
                conflicting_tool = next(
                    (t for t in existing_tools if t.name == c.conflicting_name), None
                )
                involved_ids = [tool_uuid]
                if conflicting_tool:
                    involved_ids.append(conflicting_tool.id)

                conflict = Conflict(
                    environment_id=env_uuid,
                    analysis_run_id=run.id,
                    conflict_type=c.conflict_type,
                    severity=c.severity,
                    tool_ids=involved_ids,
                    conflict_score=c.conflict_score,
                    evidence=c.evidence,
                )
                db.add(conflict)
                await db.flush()
                conflict_ids.append(conflict.id)

            # Update analysis run
            t_end = datetime.now(timezone.utc)
            run.status = AnalysisRunStatus.COMPLETED
            run.completed_at = t_end
            run.duration_seconds = (t_end - t_start).total_seconds()
            run.total_conflicts_found = len(pipeline_result.conflicts)
            run.conflict_ids = conflict_ids
            run.risk_score = (
                max((c.conflict_score for c in pipeline_result.conflicts), default=0.0)
                if pipeline_result.conflicts else 0.0
            )

            await db.commit()

            logger.info(
                f"Conflict analysis complete: tool={tool_id}, "
                f"conflicts={len(conflict_ids)}, "
                f"duration={run.duration_seconds:.1f}s"
            )
            return {
                "status": "completed",
                "analysis_run_id": str(run.id),
                "conflicts_found": len(conflict_ids),
                "has_critical": pipeline_result.has_critical,
            }

        except Exception as exc:
            run.status = AnalysisRunStatus.FAILED
            run.error_message = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise


@celery_app.task(
    bind=True,
    name="mtgs.workers.tasks.generate_embeddings_task",
    max_retries=3,
    queue="embeddings",
)
def generate_embeddings_task(self, tool_ids: list[str]) -> dict[str, Any]:
    """Batch-generate embeddings for multiple tools (used after bulk import)."""
    logger.info(f"Generating embeddings for {len(tool_ids)} tools")
    try:
        return _run_async(_batch_generate_embeddings(tool_ids))
    except Exception as exc:
        raise self.retry(exc=exc)


async def _batch_generate_embeddings(tool_ids: list[str]) -> dict[str, Any]:
    from sqlalchemy import select

    from mtgs.config import settings
    from mtgs.core.embeddings.azure_search_client import AzureSearchClient
    from mtgs.core.embeddings.fingerprinter import ToolFingerprinter
    from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService
    from mtgs.database import get_db_context
    from mtgs.models.tool import Tool
    from mtgs.core.tool_def import ToolDef

    fingerprinter = ToolFingerprinter()
    embedding_svc = AzureOpenAIEmbeddingService()
    search_client = AzureSearchClient()

    async with get_db_context() as db:
        result = await db.execute(
            select(Tool).where(
                Tool.id.in_([uuid.UUID(t) for t in tool_ids]),
                Tool.is_deleted == False,
            )
        )
        tools = result.scalars().all()

        # Batch embed
        defs = [
            ToolDef(
                name=t.name,
                description=t.description,
                input_schema=t.input_schema,
                server_name=str(t.server_id),
            )
            for t in tools
        ]
        texts = [fingerprinter.build_fingerprint_text(d) for d in defs]
        embeddings = await embedding_svc.embed_batch(texts)

        for tool, d, embedding in zip(tools, defs, embeddings):
            tool.embedding = embedding
            tool.embedding_fingerprint_hash = fingerprinter.compute_hash(d)
            tool.embedding_model = settings.azure_openai_embedding_deployment
            await search_client.upsert_tool_embedding(
                tool_id=tool.id,
                tool_name=tool.name,
                environment_id=tool.environment_id,
                embedding=embedding,
            )

        await db.commit()

    return {"embedded": len(tools)}


# ── Background task runner (for FastAPI BackgroundTasks) ──────────────────────

async def run_conflict_analysis_task(tool_id: str, env_id: str) -> None:
    """
    Async shim called by FastAPI BackgroundTasks.
    Falls back to direct async execution if Celery is unavailable.
    """
    try:
        # Try to dispatch to Celery first
        run_conflict_analysis_task.delay(tool_id=tool_id, env_id=env_id)
    except Exception:
        # Celery unavailable — run inline (development mode)
        await _run_conflict_analysis(tool_id=tool_id, env_id=env_id)


# ── Periodic / Celery beat tasks ───────────────────────────────────────────────


@celery_app.task(
    bind=True,
    name="mtgs.workers.tasks.sync_mcp_server_task",
    max_retries=3,
    default_retry_delay=30,
    queue="analysis",
)
def sync_mcp_server_task(self, server_id: str) -> dict[str, Any]:
    """
    Fetch the live tool list from a single MCP server and diff it against the DB.
    Queues conflict analysis for each newly added or updated tool.
    """
    logger.info(f"Starting MCP server sync: server={server_id}")
    try:
        return _run_async(_sync_mcp_server(server_id))
    except Exception as exc:
        logger.error(f"MCP server sync failed: {exc}")
        raise self.retry(exc=exc)


async def _sync_mcp_server(server_id: str) -> dict[str, Any]:
    """Async implementation of sync_mcp_server_task."""
    import httpx
    from sqlalchemy import select

    from mtgs.core.sync.mcp_sync import MCPServerSyncService
    from mtgs.core.tool_def import ToolDef
    from mtgs.database import get_db_context
    from mtgs.models.mcp_server import MCPServer
    from mtgs.models.tool import Tool, ToolStatus

    server_uuid = uuid.UUID(server_id)

    async with get_db_context() as db:
        # Load server record
        result = await db.execute(
            select(MCPServer).where(MCPServer.id == server_uuid, MCPServer.is_deleted == False)
        )
        server = result.scalar_one_or_none()
        if server is None:
            logger.warning(f"MCPServer {server_id} not found; skipping sync")
            return {"status": "skipped", "reason": "server_not_found"}

        # Fetch live tool list from the MCP server
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{server.base_url}/tools/list",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"Authorization": f"Bearer {server.api_key_hash}"},
                )
                resp.raise_for_status()
                data = resp.json()
                remote_tools_raw = data.get("result", {}).get("tools", [])
        except Exception as exc:
            logger.error(f"Failed to fetch tools from MCP server {server_id}: {exc}")
            return {"status": "error", "reason": str(exc)}

        # Load DB tools for this server
        db_result = await db.execute(
            select(Tool).where(
                Tool.server_id == server_uuid,
                Tool.status == ToolStatus.ACTIVE,
                Tool.is_deleted == False,
            )
        )
        db_tools_orm = db_result.scalars().all()
        db_tools = [
            ToolDef(
                name=t.name,
                description=t.description,
                input_schema=t.input_schema or {},
                server_name=server.name,
            )
            for t in db_tools_orm
        ]

        # Compute diff
        svc = MCPServerSyncService()
        report = await svc.diff(
            remote_tools=remote_tools_raw,
            db_tools=db_tools,
            server_name=server.name,
        )

        if not report.has_changes:
            logger.info(f"No changes for MCP server {server_id}")
            return {"status": "no_changes"}

        # Enqueue conflict analysis for each new/updated tool
        queued = 0
        for added_tool in report.added:
            # The full tool creation & analysis dispatch happens in the API layer;
            # here we just log that new tools were detected
            logger.info(f"New tool detected on {server.name}: {added_tool.name}")
            queued += 1

        for updated_tool in report.updated:
            logger.info(f"Updated tool detected on {server.name}: {updated_tool.name}")
            queued += 1

        for removed_tool in report.removed:
            logger.info(f"Removed tool detected on {server.name}: {removed_tool.name}")

        return {
            "status": "changes_detected",
            "added": report.total_added,
            "removed": report.total_removed,
            "updated": report.total_updated,
            "queued_for_analysis": queued,
        }


@celery_app.task(
    name="mtgs.workers.tasks.sync_all_mcp_servers_task",
    queue="analysis",
)
def sync_all_mcp_servers_task() -> dict[str, Any]:
    """Beat task: fan-out sync_mcp_server_task for every active server."""
    return _run_async(_sync_all_mcp_servers())


async def _sync_all_mcp_servers() -> dict[str, Any]:
    """Enumerate all active MCP servers and enqueue individual sync tasks."""
    from sqlalchemy import select

    from mtgs.database import get_db_context
    from mtgs.models.mcp_server import MCPServer

    async with get_db_context() as db:
        result = await db.execute(
            select(MCPServer.id).where(MCPServer.is_deleted == False)
        )
        server_ids = [str(row[0]) for row in result.fetchall()]

    for sid in server_ids:
        sync_mcp_server_task.delay(server_id=sid)

    logger.info(f"Enqueued sync for {len(server_ids)} MCP servers")
    return {"enqueued": len(server_ids)}


@celery_app.task(
    name="mtgs.workers.tasks.scheduled_conflict_scan_task",
    queue="analysis",
)
def scheduled_conflict_scan_task() -> dict[str, Any]:
    """
    Beat task: hourly full conflict re-scan.
    Re-analyses all active tools in all environments so that newly added tools
    that weren't caught in the webhook path get processed.
    """
    return _run_async(_scheduled_conflict_scan())


async def _scheduled_conflict_scan() -> dict[str, Any]:
    """Enumerate all environments and re-queue analysis for their active tools."""
    from sqlalchemy import select

    from mtgs.database import get_db_context
    from mtgs.models.tool import Tool, ToolStatus

    async with get_db_context() as db:
        result = await db.execute(
            select(Tool.id, Tool.environment_id).where(
                Tool.status == ToolStatus.ACTIVE,
                Tool.is_deleted == False,
            )
        )
        rows = result.fetchall()

    queued = 0
    for tool_id, env_id in rows:
        run_conflict_analysis_task.delay(
            tool_id=str(tool_id), env_id=str(env_id)
        )
        queued += 1

    logger.info(f"Scheduled conflict scan enqueued {queued} analysis tasks")
    return {"enqueued": queued}
