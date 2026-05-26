"""
Unit tests for Azure OpenAI and Azure AI Search clients.

All Azure SDK calls are mocked — no real API credentials needed.

Run:
    pytest tests/unit/test_azure_clients.py -v
"""

from __future__ import annotations

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ─────────────────────────────────────────────────────────────────────────────
# ToolFingerprinter — already covered in test_fingerprinter.py
# AzureOpenAIEmbeddingService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAzureOpenAIEmbeddingService:
    @pytest.fixture
    def mock_openai_client(self):
        """Mock the AsyncAzureOpenAI client."""
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 3072)]
        mock_response.usage = MagicMock(prompt_tokens=10, total_tokens=10)

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)
        return mock_client

    @pytest.mark.asyncio
    async def test_embed_returns_list_of_floats(self, mock_openai_client) -> None:
        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_openai_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService

            svc = AzureOpenAIEmbeddingService()
            result = await svc.embed("test text")

        assert isinstance(result, list)
        assert len(result) == 3072
        assert all(isinstance(v, float) for v in result)

    @pytest.mark.asyncio
    async def test_embed_caches_result(self, mock_openai_client) -> None:
        """Second call with same text should NOT call the API again."""
        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_openai_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService

            svc = AzureOpenAIEmbeddingService()
            result1 = await svc.embed("cache test")
            result2 = await svc.embed("cache test")

        # API called only once
        assert mock_openai_client.embeddings.create.call_count == 1
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_embed_different_texts_different_calls(self, mock_openai_client) -> None:
        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_openai_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService

            svc = AzureOpenAIEmbeddingService()
            await svc.embed("text one")
            await svc.embed("text two")

        assert mock_openai_client.embeddings.create.call_count == 2

    @pytest.mark.asyncio
    async def test_embed_batch_returns_multiple_embeddings(self, mock_openai_client) -> None:
        # Mock batch response with 3 embeddings
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[float(i)] * 3072) for i in range(3)
        ]
        mock_openai_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_openai_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService

            svc = AzureOpenAIEmbeddingService()
            results = await svc.embed_batch(["text a", "text b", "text c"])

        assert len(results) == 3
        for r in results:
            assert len(r) == 3072

    @pytest.mark.asyncio
    async def test_embed_batch_uses_cache_for_repeated_texts(self, mock_openai_client) -> None:
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.5] * 3072)]
        mock_openai_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_openai_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService

            svc = AzureOpenAIEmbeddingService()
            await svc.embed("shared text")  # warm cache
            results = await svc.embed_batch(["shared text", "shared text"])

        # Only the initial embed should have called the API
        assert mock_openai_client.embeddings.create.call_count == 1
        assert len(results) == 2


# ─────────────────────────────────────────────────────────────────────────────
# AzureOpenAIChatService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAzureOpenAIChatService:
    @pytest.fixture
    def mock_chat_client(self):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"result": "ok"}'))]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        return mock_client

    @pytest.mark.asyncio
    async def test_complete_returns_string(self, mock_chat_client) -> None:
        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_chat_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIChatService

            svc = AzureOpenAIChatService()
            result = await svc.complete(
                system_prompt="You are a helpful assistant.",
                user_prompt="Say hello.",
            )

        assert isinstance(result, str)
        assert '{"result": "ok"}' == result

    @pytest.mark.asyncio
    async def test_complete_json_parses_response(self, mock_chat_client) -> None:
        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_chat_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIChatService

            svc = AzureOpenAIChatService()
            result = await svc.complete_json(
                system_prompt="Return JSON.",
                user_prompt="Give me something.",
            )

        assert isinstance(result, dict)
        assert result["result"] == "ok"

    @pytest.mark.asyncio
    async def test_complete_uses_temperature_zero_by_default(
        self, mock_chat_client
    ) -> None:
        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_chat_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIChatService

            svc = AzureOpenAIChatService()
            await svc.complete(system_prompt="sys", user_prompt="usr")

        call_kwargs = mock_chat_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_complete_handles_none_content_gracefully(
        self, mock_chat_client
    ) -> None:
        # Some models return None content in edge cases
        mock_chat_client.chat.completions.create.return_value.choices[0].message.content = None

        with patch(
            "mtgs.core.embeddings.openai_client._make_client",
            return_value=mock_chat_client,
        ):
            from mtgs.core.embeddings.openai_client import AzureOpenAIChatService

            svc = AzureOpenAIChatService()
            result = await svc.complete(system_prompt="sys", user_prompt="usr")

        assert result == ""


# ─────────────────────────────────────────────────────────────────────────────
# AzureSearchClient tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAzureSearchClient:
    @pytest.fixture
    def mock_search_sdk_client(self):
        """Mock the azure.search.documents.aio.SearchClient."""
        mock = AsyncMock()
        mock.__aenter__ = AsyncMock(return_value=mock)
        mock.__aexit__ = AsyncMock(return_value=None)
        return mock

    @pytest.mark.asyncio
    async def test_upsert_tool_embedding_calls_merge_or_upload(
        self, mock_search_sdk_client
    ) -> None:
        mock_result = MagicMock(succeeded=True)
        mock_search_sdk_client.merge_or_upload_documents = AsyncMock(
            return_value=[mock_result]
        )

        with patch(
            "mtgs.core.embeddings.azure_search_client.SearchClient",
            return_value=mock_search_sdk_client,
        ):
            from mtgs.core.embeddings.azure_search_client import AzureSearchClient

            client = AzureSearchClient()
            tool_id = uuid.uuid4()
            env_id = uuid.uuid4()
            embedding = [0.1] * 3072

            await client.upsert_tool_embedding(
                tool_id=tool_id,
                tool_name="test_tool",
                environment_id=env_id,
                embedding=embedding,
            )

        mock_search_sdk_client.merge_or_upload_documents.assert_called_once()
        doc = mock_search_sdk_client.merge_or_upload_documents.call_args.kwargs["documents"][0]
        assert doc["id"] == str(tool_id)
        assert doc["tool_name"] == "test_tool"

    @pytest.mark.asyncio
    async def test_search_nearest_returns_hits(
        self, mock_search_sdk_client
    ) -> None:
        # Mock async iteration over search results
        hit = {
            "id": str(uuid.uuid4()),
            "tool_name": "existing_tool",
            "environment_id": str(uuid.uuid4()),
            "@search.score": 0.92,
        }

        async def mock_results():
            yield hit

        mock_search_sdk_client.search = AsyncMock(return_value=mock_results())

        with patch(
            "mtgs.core.embeddings.azure_search_client.SearchClient",
            return_value=mock_search_sdk_client,
        ):
            from mtgs.core.embeddings.azure_search_client import AzureSearchClient

            client = AzureSearchClient()
            results = await client.search_nearest(
                embedding=[0.1] * 3072,
                top_k=5,
            )

        assert len(results) == 1
        assert results[0]["tool_name"] == "existing_tool"
        assert results[0]["score"] == pytest.approx(0.92)

    @pytest.mark.asyncio
    async def test_delete_tool_embedding_calls_delete(
        self, mock_search_sdk_client
    ) -> None:
        mock_search_sdk_client.delete_documents = AsyncMock()

        with patch(
            "mtgs.core.embeddings.azure_search_client.SearchClient",
            return_value=mock_search_sdk_client,
        ):
            from mtgs.core.embeddings.azure_search_client import AzureSearchClient

            client = AzureSearchClient()
            tool_id = uuid.uuid4()
            await client.delete_tool_embedding(tool_id)

        mock_search_sdk_client.delete_documents.assert_called_once()
        doc = mock_search_sdk_client.delete_documents.call_args.kwargs["documents"][0]
        assert doc["id"] == str(tool_id)

    @pytest.mark.asyncio
    async def test_health_check_returns_true_on_success(
        self, mock_search_sdk_client
    ) -> None:
        mock_search_sdk_client.get_document_count = AsyncMock(return_value=42)

        with patch(
            "mtgs.core.embeddings.azure_search_client.SearchClient",
            return_value=mock_search_sdk_client,
        ):
            from mtgs.core.embeddings.azure_search_client import AzureSearchClient

            client = AzureSearchClient()
            result = await client.check_health()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_failure(
        self, mock_search_sdk_client
    ) -> None:
        mock_search_sdk_client.get_document_count = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        with patch(
            "mtgs.core.embeddings.azure_search_client.SearchClient",
            return_value=mock_search_sdk_client,
        ):
            from mtgs.core.embeddings.azure_search_client import AzureSearchClient

            client = AzureSearchClient()
            result = await client.check_health()

        assert result is False

    @pytest.mark.asyncio
    async def test_search_nearest_filters_by_environment(
        self, mock_search_sdk_client
    ) -> None:
        async def mock_results():
            return
            yield  # empty async generator

        mock_search_sdk_client.search = AsyncMock(return_value=mock_results())
        env_id = uuid.uuid4()

        with patch(
            "mtgs.core.embeddings.azure_search_client.SearchClient",
            return_value=mock_search_sdk_client,
        ):
            from mtgs.core.embeddings.azure_search_client import AzureSearchClient

            client = AzureSearchClient()
            await client.search_nearest(
                embedding=[0.1] * 3072,
                environment_id=env_id,
            )

        call_kwargs = mock_search_sdk_client.search.call_args.kwargs
        assert str(env_id) in call_kwargs.get("filter", "")
