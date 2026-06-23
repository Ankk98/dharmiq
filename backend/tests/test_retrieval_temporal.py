from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.config.settings import Settings, load_settings
from dharmiq.db.models.documents import DocType, DocumentChunk, InstrumentStatus, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.llm.retrieval import retrieve_document_chunks
from dharmiq.retrieval.hybrid import bm25_search_corpus, hybrid_search_corpus, vector_search_corpus
from tests.corpus_helpers import with_indexed_at
from tests.vector_helpers import unit_vector


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


@pytest.fixture(autouse=True)
async def _clean_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


async def _seed_ipc_bns_pair(
    db: AsyncSession,
) -> tuple[DocumentChunk, DocumentChunk, SourceDocument, SourceDocument]:
    indexed_at = datetime.now(UTC)
    ipc = with_indexed_at(
        SourceDocument(
            source_id="IN-IPC-1860",
            title="Indian Penal Code, 1860",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-ipc",
            file_path="/tmp/ipc.pdf",
            status=InstrumentStatus.SUPERSEDED,
            superseded_by_source_id="IN-BNS-2023",
            version=1,
            indexed_at=indexed_at,
        )
    )
    bns = with_indexed_at(
        SourceDocument(
            source_id="IN-BNS-2023",
            title="Bharatiya Nyaya Sanhita, 2023",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-bns",
            file_path="/tmp/bns.pdf",
            status=InstrumentStatus.IN_FORCE,
            version=1,
            indexed_at=indexed_at,
        )
    )
    db.add_all([ipc, bns])
    await db.flush()

    theft_vector = unit_vector(0)
    ipc_chunk = DocumentChunk(
        document_id=ipc.id,
        chunk_index=0,
        text="Section 302 IPC — Punishment for murder.",
        page_start=302,
        page_end=302,
        embedding=PgVector(theft_vector),
    )
    bns_chunk = DocumentChunk(
        document_id=bns.id,
        chunk_index=0,
        text="Section 103 BNS — Punishment for murder.",
        page_start=103,
        page_end=103,
        embedding=PgVector(theft_vector),
    )
    db.add_all([ipc_chunk, bns_chunk])
    await db.commit()
    await db.refresh(ipc_chunk)
    await db.refresh(bns_chunk)
    await db.refresh(ipc)
    await db.refresh(bns)
    return ipc_chunk, bns_chunk, ipc, bns


async def _seed_versioned_document(
    db: AsyncSession,
) -> tuple[DocumentChunk, DocumentChunk, SourceDocument, SourceDocument]:
    indexed_at = datetime.now(UTC)
    old_doc = with_indexed_at(
        SourceDocument(
            source_id=f"IN-TEST-{uuid.uuid4()}",
            title="Sample Act (old version)",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-v1",
            file_path="/tmp/sample-v1.pdf",
            version=1,
            indexed_at=indexed_at,
        )
    )
    new_doc = with_indexed_at(
        SourceDocument(
            source_id=old_doc.source_id,
            title="Sample Act (current version)",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-v2",
            file_path="/tmp/sample-v2.pdf",
            version=2,
            indexed_at=indexed_at,
        )
    )
    db.add_all([old_doc, new_doc])
    await db.flush()

    old_chunk = DocumentChunk(
        document_id=old_doc.id,
        chunk_index=0,
        text="Old version text about registration requirements.",
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(0)),
    )
    new_chunk = DocumentChunk(
        document_id=new_doc.id,
        chunk_index=0,
        text="Current version text about registration requirements.",
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(0)),
    )
    db.add_all([old_chunk, new_chunk])
    await db.commit()
    await db.refresh(old_chunk)
    await db.refresh(new_chunk)
    return old_chunk, new_chunk, old_doc, new_doc


def _settings_with_superseded(*, include_superseded: bool) -> Settings:
    settings = load_settings()
    settings.retrieval.include_superseded = include_superseded
    return settings


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_superseded_ipc_not_retrieved_when_bns_indexed() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "theft punishment BNS murder"
    backend = _MappedEmbeddingBackend({query: unit_vector(0)})
    settings = _settings_with_superseded(include_superseded=False)

    async with factory() as db:
        ipc_chunk, bns_chunk, ipc, bns = await _seed_ipc_bns_pair(db)
        results = await hybrid_search_corpus(
            db,
            query,
            vector_top_k=5,
            bm25_top_k=5,
            rrf_k=60,
            rrf_top_k=5,
            backend=backend,
            settings=settings,
        )

    assert results
    document_ids = {chunk.document_id for chunk in results}
    assert bns.id in document_ids
    assert ipc.id not in document_ids
    assert results[0].chunk_id == bns_chunk.id


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_include_superseded_flag() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "Section 302 IPC murder"

    async with factory() as db:
        ipc_chunk, _, ipc, _ = await _seed_ipc_bns_pair(db)
        results = await bm25_search_corpus(
            db,
            query,
            top_k=5,
            settings=_settings_with_superseded(include_superseded=True),
        )

    assert any(chunk.chunk_id == ipc_chunk.id for chunk in results)
    assert any(chunk.document_id == ipc.id for chunk in results)


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_old_version_chunks_excluded() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "registration requirements"
    backend = _MappedEmbeddingBackend({query: unit_vector(0)})

    async with factory() as db:
        old_chunk, new_chunk, old_doc, new_doc = await _seed_versioned_document(db)
        results = await vector_search_corpus(db, query, top_k=5, backend=backend)

    assert len(results) == 1
    assert results[0].chunk_id == new_chunk.id
    assert results[0].document_id == new_doc.id
    assert results[0].document_id != old_doc.id
    assert results[0].chunk_id != old_chunk.id


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_revised_law_retrieval_prefers_bns_over_ipc() -> None:
    """Fixture corpus check aligned with v1_revised_law retrieval expectations."""
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "What is the punishment for murder under current criminal law?"
    backend = _MappedEmbeddingBackend({query: unit_vector(0)})

    async with factory() as db:
        _, bns_chunk, _, _ = await _seed_ipc_bns_pair(db)
        results = await retrieve_document_chunks(
            db,
            query,
            top_k=3,
            backend=backend,
            settings=_settings_with_superseded(include_superseded=False),
        )

    assert results
    assert results[0].chunk_id == bns_chunk.id
    assert "BNS" in results[0].text
