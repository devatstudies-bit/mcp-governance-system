"""
Azure AI Search client for vector (embedding) operations.

Responsibilities:
  1. Upsert tool embeddings into the Azure AI Search index
  2. ANN (approximate nearest-neighbour) search given an embedding vector
  3. Delete a tool's embedding from the index

Architecture notes:
  - Uses azure-search-documents SDK (REST under the hood)
  - Retry with exponential backoff via `tenacity`
  - All methods are async to avoid blocking the FastAPI event loop
  - The index schema is managed separately (see infrastructure/search_index.json)

Index field mapping (created once at deploy time):
  id          : Edm.String (key)            ← tool UUID
  tool_name   : Edm.String (searchable)
  environment : Edm.String (filterable)
  embedding   : Collection(Edm.Single)      ← 3072-dim vector, HNSW
"""

from __future__ import annotations

import uuid
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from mtgs.config import settings
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)

_INDEX_NAME = settings.azure_search_index_name
_VECTOR_FIELD = settings.azure_search_vector_field
_TOP_K = settings.azure_search_top_k


class AzureSearchClient:
    """
    Thin async wrapper around azure-search-documents for MTGS vector operations.

    Usage:
        client = AzureSearchClient()
        await client.upsert_tool_embedding(tool_id, tool_name, env_id, embedding)
        hits = await client.search_nearest(embedding, top_k=20)
    """

    def __init__(self) -> None:
        self._credential = AzureKeyCredential(settings.azure_search_api_key)
        self._endpoint = settings.azure_search_endpoint
        self._index_name = _INDEX_NAME

    def _get_client(self) -> SearchClient:
        """Create a new SearchClient (clients are not thread-safe; create per call)."""
        return SearchClient(
            endpoint=self._endpoint,
            index_name=self._index_name,
            credential=self._credential,
        )

    @retry(
        retry=retry_if_exception_type(AzureError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def upsert_tool_embedding(
        self,
        tool_id: uuid.UUID,
        tool_name: str,
        environment_id: uuid.UUID,
        embedding: list[float],
    ) -> None:
        """
        Insert or update a tool's embedding in Azure AI Search.
        Uses merge-or-upload action — safe to call on create and update.
        """
        document = {
            "id": str(tool_id),
            "tool_name": tool_name,
            "environment_id": str(environment_id),
            _VECTOR_FIELD: embedding,
        }
        async with self._get_client() as client:
            result = await client.merge_or_upload_documents(documents=[document])
            logger.info(
                "embedding_upserted",
                tool_id=str(tool_id),
                tool_name=tool_name,
                succeeded=result[0].succeeded,
            )

    @retry(
        retry=retry_if_exception_type(AzureError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def search_nearest(
        self,
        embedding: list[float],
        top_k: int = _TOP_K,
        environment_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find the top-K most similar tool embeddings using HNSW ANN search.

        Args:
            embedding:        Query vector (must match index dimensions).
            top_k:            Number of nearest neighbours to return.
            environment_id:   If set, filter results to this environment only.

        Returns:
            List of dicts: [{tool_id, tool_name, environment_id, score}, ...]
            Score is the cosine similarity (0–1, higher = more similar).
        """
        vector_query = VectorizedQuery(
            vector=embedding,
            k_nearest_neighbors=top_k,
            fields=_VECTOR_FIELD,
            exhaustive=False,  # use HNSW approximation for speed
        )

        filter_expr: str | None = None
        if environment_id:
            filter_expr = f"environment_id eq '{environment_id}'"

        async with self._get_client() as client:
            results = await client.search(
                search_text=None,
                vector_queries=[vector_query],
                filter=filter_expr,
                top=top_k,
                select=["id", "tool_name", "environment_id"],
            )
            hits = []
            async for result in results:
                hits.append(
                    {
                        "tool_id": result["id"],
                        "tool_name": result["tool_name"],
                        "environment_id": result.get("environment_id"),
                        "score": result["@search.score"],
                    }
                )
        return hits

    @retry(
        retry=retry_if_exception_type(AzureError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def delete_tool_embedding(self, tool_id: uuid.UUID) -> None:
        """Remove a tool's embedding from the index (called on tool deprecation/deletion)."""
        async with self._get_client() as client:
            await client.delete_documents(documents=[{"id": str(tool_id)}])
            logger.info("embedding_deleted", tool_id=str(tool_id))

    async def embed(self, text: str) -> list[float]:
        """
        Convenience method: generate an embedding for arbitrary text.
        Delegates to AzureOpenAIEmbeddingService.
        Kept here so callers only need to know about AzureSearchClient.
        """
        from mtgs.core.embeddings.openai_client import AzureOpenAIEmbeddingService

        svc = AzureOpenAIEmbeddingService()
        return await svc.embed(text)

    async def check_health(self) -> bool:
        """Return True if Azure AI Search is reachable."""
        try:
            async with self._get_client() as client:
                await client.get_document_count()
            return True
        except Exception as exc:
            logger.error("azure_search_health_check_failed", error=str(exc))
            return False
