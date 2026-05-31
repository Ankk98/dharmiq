from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import EmbeddingError
from dharmiq.core.logging import get_logger

if TYPE_CHECKING:
    from dharmiq.llm.openrouter_client import OpenRouterClient

logger = get_logger(__name__)


class EmbeddingBackend(ABC):
    @property
    @abstractmethod
    def dimensions(self) -> int:
        raise NotImplementedError

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class LocalEmbeddingBackend(EmbeddingBackend):
    """CPU sentence-transformers model, loaded once per process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None

    @property
    def dimensions(self) -> int:
        return self._settings.embeddings.local_dimensions

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "loading_local_embedding_model",
                model=self._settings.embeddings.local_model_name,
            )
            self._model = SentenceTransformer(self._settings.embeddings.local_model_name)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        def _encode() -> list[list[float]]:
            model = self._load_model()
            vectors = model.encode(texts, convert_to_numpy=True)
            return [vector.tolist() for vector in vectors]

        try:
            return await asyncio.to_thread(_encode)
        except Exception as exc:
            raise EmbeddingError("Local embedding failed", details={"error": str(exc)}) from exc


class RemoteEmbeddingBackend(EmbeddingBackend):
    """OpenRouter-hosted embedding models."""

    def __init__(self, settings: Settings, client: OpenRouterClient | None = None) -> None:
        self._settings = settings
        if client is None:
            from dharmiq.llm.openrouter_client import get_openrouter_client

            client = get_openrouter_client()
        self._client = client

    @property
    def dimensions(self) -> int:
        return self._settings.embeddings.remote_dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            return await self._client.create_embeddings(
                texts,
                model=self._settings.embeddings.remote_model_id,
            )
        except Exception as exc:
            raise EmbeddingError("Remote embedding failed", details={"error": str(exc)}) from exc


@lru_cache
def get_embedding_backend() -> EmbeddingBackend:
    settings = get_settings()
    if settings.embeddings.backend == "remote":
        return RemoteEmbeddingBackend(settings)
    return LocalEmbeddingBackend(settings)


def reset_embedding_backend_cache() -> None:
    get_embedding_backend.cache_clear()
