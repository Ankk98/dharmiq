from __future__ import annotations

import pytest

from dharmiq.llm.embeddings import LocalEmbeddingBackend, RemoteEmbeddingBackend
from dharmiq.config.settings import load_settings


class _FakeOpenRouterClient:
    async def create_embeddings(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
        return [[float(len(text)), 0.0, 1.0] for text in texts]


@pytest.mark.asyncio
async def test_remote_embedding_backend() -> None:
    settings = load_settings("dev")
    backend = RemoteEmbeddingBackend(settings, client=_FakeOpenRouterClient())  # type: ignore[arg-type]

    vectors = await backend.embed_texts(["hello", "world"])

    assert backend.dimensions == settings.embeddings.remote_dimensions
    assert vectors[0][0] == 5.0
    assert vectors[1][0] == 5.0


@pytest.mark.asyncio
@pytest.mark.slow
async def test_local_embedding_backend_roundtrip() -> None:
    settings = load_settings("dev")
    backend = LocalEmbeddingBackend(settings)

    vectors = await backend.embed_texts(["fundamental rights", "consumer refunds"])

    assert len(vectors) == 2
    assert len(vectors[0]) == settings.embeddings.local_dimensions
    assert len(vectors[1]) == settings.embeddings.local_dimensions
