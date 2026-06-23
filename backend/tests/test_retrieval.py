from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.llm.retrieval import retrieve_document_chunks
from tests.corpus_helpers import with_indexed_at
from tests.vector_helpers import unit_vector


@pytest.fixture(autouse=True)
async def _clean_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


class _MappedEmbeddingBackend(EmbeddingBackend):
    def __init__(
        self,
        mapping: dict[str, list[float]],
        *,
        dimensions: int = 384,
        default: list[float] | None = None,
    ) -> None:
        self._mapping = mapping
        self._dimensions = dimensions
        self._default = default or unit_vector(0, dimensions=dimensions)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._mapping.get(text, self._default) for text in texts]


async def _seed_test_corpus(db: AsyncSession) -> tuple[DocumentChunk, DocumentChunk]:
    document = with_indexed_at(
        SourceDocument(
            source_id=f"test-constitution-{uuid.uuid4()}",
            title="Constitution of India (test)",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-1",
            file_path="/tmp/constitution.pdf",
            indexed_at=datetime.now(UTC),
        )
    )
    db.add(document)
    await db.flush()

    arrest_chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="Article 22 provides protections against arbitrary arrest and detention.",
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(0)),
    )
    consumer_chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        text="Consumer protection law covers defective products and refund rights.",
        page_start=2,
        page_end=2,
        embedding=PgVector(unit_vector(1)),
    )
    db.add_all([arrest_chunk, consumer_chunk])
    await db.commit()
    await db.refresh(arrest_chunk)
    await db.refresh(consumer_chunk)
    return arrest_chunk, consumer_chunk


@pytest.mark.asyncio
async def test_retrieve_document_chunks_ranks_by_similarity() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "What are my rights if police arrest me?"
    backend = _MappedEmbeddingBackend(
        {
            query: unit_vector(0),
        }
    )

    async with factory() as db:
        arrest_chunk, consumer_chunk = await _seed_test_corpus(db)
        results = await retrieve_document_chunks(
            db,
            query,
            top_k=2,
            backend=backend,
        )

    assert len(results) == 2
    assert results[0].chunk_id == arrest_chunk.id
    assert results[0].document_title == "Constitution of India (test)"
    assert "Article 22" in results[0].text
    assert results[0].score >= results[1].score
    assert results[1].chunk_id == consumer_chunk.id


@pytest.mark.asyncio
async def test_retrieve_document_chunks_empty_corpus() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    backend = _MappedEmbeddingBackend({})

    async with factory() as db:
        results = await retrieve_document_chunks(
            db,
            "Any question",
            backend=backend,
        )

    assert results == []
