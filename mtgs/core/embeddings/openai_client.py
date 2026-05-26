"""
Azure OpenAI embedding + chat completion client.

Two classes:
  AzureOpenAIEmbeddingService  — generates text embeddings (text-embedding-3-large)
  AzureOpenAIChatService       — chat completions for simulation & recommendations

Both use the openai Python SDK with azure_endpoint configured (same SDK, Azure endpoint).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from openai import AsyncAzureOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from mtgs.config import settings
from mtgs.utils.logging import get_logger

logger = get_logger(__name__)


def _make_client() -> AsyncAzureOpenAI:
    return AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )


class AzureOpenAIEmbeddingService:
    """
    Generates text embeddings via Azure OpenAI text-embedding-3-large.

    Includes an in-process cache (keyed on SHA256 of input text) to avoid
    re-embedding unchanged tool definitions.
    """

    def __init__(self) -> None:
        self._client = _make_client()
        self._cache: dict[str, list[float]] = {}

    def _cache_key(self, text: str) -> str:
        return hashlib.sha256(
            f"{settings.azure_openai_embedding_deployment}:{text}".encode()
        ).hexdigest()

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def embed(self, text: str) -> list[float]:
        """
        Return the embedding vector for `text`.
        Uses in-process cache; respects Azure OpenAI rate limits via retry.
        """
        key = self._cache_key(text)
        if key in self._cache:
            logger.debug("embedding_cache_hit", key=key[:16])
            return self._cache[key]

        response = await self._client.embeddings.create(
            input=text,
            model=settings.azure_openai_embedding_deployment,
            dimensions=settings.azure_openai_embedding_dimensions,
        )
        embedding = response.data[0].embedding
        self._cache[key] = embedding
        logger.debug(
            "embedding_generated",
            model=settings.azure_openai_embedding_deployment,
            dimensions=len(embedding),
        )
        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single API call (more efficient)."""
        # Identify which texts are not cached
        keys = [self._cache_key(t) for t in texts]
        uncached_indices = [i for i, k in enumerate(keys) if k not in self._cache]

        if uncached_indices:
            uncached_texts = [texts[i] for i in uncached_indices]
            response = await self._client.embeddings.create(
                input=uncached_texts,
                model=settings.azure_openai_embedding_deployment,
                dimensions=settings.azure_openai_embedding_dimensions,
            )
            for batch_idx, original_idx in enumerate(uncached_indices):
                embedding = response.data[batch_idx].embedding
                self._cache[keys[original_idx]] = embedding

        return [self._cache[k] for k in keys]


class AzureOpenAIChatService:
    """
    Chat completions via Azure OpenAI gpt-4o.

    Used for:
      - Routing simulation (Stage 4)
      - Recommendation generation
      - Probe query auto-generation
    """

    def __init__(self) -> None:
        self._client = _make_client()
        self._deployment = settings.azure_openai_chat_deployment

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        response_format: dict[str, str] | None = None,
    ) -> str:
        """
        Send a chat completion request and return the response text.

        Args:
            system_prompt:   System message content.
            user_prompt:     User message content.
            temperature:     0.0 for deterministic (simulation); higher for generation.
            max_tokens:      Max response length.
            response_format: {"type": "json_object"} to enforce JSON output.

        Returns:
            Raw text content of the assistant response.
        """
        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        logger.debug(
            "chat_completion",
            model=self._deployment,
            prompt_tokens=response.usage.prompt_tokens if response.usage else None,
            completion_tokens=response.usage.completion_tokens if response.usage else None,
        )
        return content

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
    ) -> Any:
        """
        Complete and parse the response as JSON.
        Raises json.JSONDecodeError if the response is not valid JSON.
        """
        raw = await self.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(raw)
