"""
Pytest configuration and shared fixtures.

Fixture scopes:
  session  — DB engine, created once per test run
  function — fresh DB transaction, rolled back after each test (fast)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Force TEST environment before any imports ─────────────────────────────────
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-32-chars-minimum!")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-must-be-long-enough-32c")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
os.environ.setdefault("AZURE_SEARCH_ENDPOINT", "https://test.search.windows.net")
os.environ.setdefault("AZURE_SEARCH_API_KEY", "test-search-key")


# ── SQLite in-memory engine for unit/integration tests ────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_mtgs.db"


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
async def test_engine():
    """Create tables once per test session using SQLite."""
    from mtgs.database import Base
    import mtgs.models  # noqa: F401 — register all models

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a fresh AsyncSession per test, wrapped in a savepoint.
    The savepoint is rolled back after each test — no data leaks between tests.
    """
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    HTTPX async test client wired to the FastAPI app.
    Overrides the `get_db` dependency to use the test session.
    """
    from mtgs.database import get_db
    from mtgs.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ── Auth fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def admin_token() -> str:
    """A valid JWT for an admin user."""
    from mtgs.auth.security import create_access_token

    return create_access_token(
        subject=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        role="admin",
    )


@pytest.fixture
def developer_token() -> str:
    from mtgs.auth.security import create_access_token

    return create_access_token(
        subject=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        role="developer",
    )


# ── Mock Azure services ───────────────────────────────────────────────────────

@pytest.fixture
def mock_embedding_service():
    """Mock AzureOpenAIEmbeddingService — returns deterministic fake embeddings."""
    mock = AsyncMock()
    mock.embed.return_value = [0.1] * 3072
    mock.embed_batch.return_value = [[0.1] * 3072]
    return mock


@pytest.fixture
def mock_search_client():
    """Mock AzureSearchClient — returns empty search results."""
    mock = AsyncMock()
    mock.search_nearest.return_value = []
    mock.upsert_tool_embedding.return_value = None
    mock.delete_tool_embedding.return_value = None
    mock.embed.return_value = [0.1] * 3072
    return mock


@pytest.fixture
def mock_chat_service():
    """Mock AzureOpenAIChatService."""
    mock = AsyncMock()
    mock.complete.return_value = "query_database"
    mock.complete_json.return_value = {"recommendations": []}
    return mock


# ── Seed data factories ───────────────────────────────────────────────────────

@pytest.fixture
def make_tool_def():
    """Factory for ToolDef instances."""
    from mtgs.core.tool_def import ToolDef

    def _make(
        name: str = "test_tool",
        description: str = "A test tool for unit testing purposes.",
        server_name: str = "test-server",
        input_schema: dict | None = None,
    ) -> ToolDef:
        return ToolDef(
            name=name,
            description=description,
            server_name=server_name,
            input_schema=input_schema or {"type": "object", "properties": {}},
        )

    return _make
