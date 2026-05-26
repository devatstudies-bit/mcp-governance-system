"""
Async SQLAlchemy engine and session factory.

Design decisions:
- AsyncEngine with asyncpg driver for non-blocking I/O
- Scoped session via AsyncSession with expire_on_commit=False
  (avoids lazy-load errors after commit in async context)
- `get_db()` is the FastAPI dependency; use as `Depends(get_db)`
- `get_db_context()` is the context-manager form for Celery workers
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from mtgs.config import settings
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# ── Engine ────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout,
    pool_pre_ping=True,   # reconnect on stale connections
    echo=settings.database_echo,
    json_serializer=lambda obj: __import__("orjson").dumps(obj).decode(),
    json_deserializer=lambda s: __import__("orjson").loads(s),
)

# ── Session factory ───────────────────────────────────────────────────────────

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an AsyncSession per request.
    The session is committed on success and rolled back on exception.

    Usage:
        @router.post("/tools")
        async def create_tool(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Context-manager form (for workers / scripts) ──────────────────────────────

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context-manager for use outside FastAPI (Celery workers, CLI, tests).

    Usage:
        async with get_db_context() as db:
            result = await db.execute(select(Tool))
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Health check helper ───────────────────────────────────────────────────────

async def check_db_health() -> bool:
    """Return True if DB is reachable, False otherwise."""
    try:
        from sqlalchemy import text

        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("db_health_check_failed", error=str(exc))
        return False
