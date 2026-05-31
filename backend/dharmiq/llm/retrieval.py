from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import BaseModel, ConfigDict
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.llm.embeddings import EmbeddingBackend, get_embedding_backend


SourceType = Literal["corpus", "upload"]


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    source_type: SourceType
    document_id: uuid.UUID
    document_title: str
    text: str
    score: float
    chunk_index: int
    page_start: int | None
    page_end: int | None


class RetrievedChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    source_type: SourceType
    document_id: uuid.UUID
    document_title: str
    text: str
    score: float
    chunk_index: int
    page_start: int | None
    page_end: int | None


class CitationRead(BaseModel):
    chunk_id: uuid.UUID
    source_type: SourceType
    document_id: uuid.UUID
    document_title: str
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None


def _query_vector(values: list[float]) -> PgVector:
    return PgVector(values)


_CORPUS_RETRIEVAL_SQL = text("""
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        sd.title AS document_title,
        dc.text,
        dc.chunk_index,
        dc.page_start,
        dc.page_end,
        dc.embedding <=> :query_embedding AS distance
    FROM document_chunks dc
    JOIN source_documents sd ON dc.document_id = sd.id
    WHERE dc.embedding IS NOT NULL
    ORDER BY distance
    LIMIT :top_k
""")


_UPLOAD_RETRIEVAL_SQL = text("""
    SELECT
        uuc.id AS chunk_id,
        uuc.upload_id AS document_id,
        uu.original_filename AS document_title,
        uuc.text,
        uuc.chunk_index,
        uuc.page_start,
        uuc.page_end,
        uuc.embedding <=> :query_embedding AS distance
    FROM user_upload_chunks uuc
    JOIN user_uploads uu ON uuc.upload_id = uu.id
    WHERE uu.user_id = :user_id
      AND uu.deleted_at IS NULL
      AND uuc.embedding IS NOT NULL
    ORDER BY distance
    LIMIT :top_k
""")


def _row_to_chunk(row: object, *, source_type: SourceType) -> RetrievedChunk:
    mapping = row._mapping  # type: ignore[attr-defined]
    distance = float(mapping["distance"])
    return RetrievedChunk(
        chunk_id=mapping["chunk_id"],
        source_type=source_type,
        document_id=mapping["document_id"],
        document_title=mapping["document_title"],
        text=mapping["text"],
        score=1.0 - distance,
        chunk_index=mapping["chunk_index"],
        page_start=mapping["page_start"],
        page_end=mapping["page_end"],
    )


async def retrieve_document_chunks(
    db: AsyncSession,
    query: str,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Return the most similar corpus document chunks for a natural-language query."""
    cfg = settings or get_settings()
    embedder = backend or get_embedding_backend()
    limit = top_k or cfg.retrieval.top_k

    query_vectors = await embedder.embed_texts([query])
    if not query_vectors:
        return []

    result = await db.execute(
        _CORPUS_RETRIEVAL_SQL,
        {
            "query_embedding": _query_vector(query_vectors[0]),
            "top_k": limit,
        },
    )

    return [_row_to_chunk(row, source_type="corpus") for row in result]


async def retrieve_user_upload_chunks(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Return the most similar user-upload chunks for a natural-language query."""
    cfg = settings or get_settings()
    embedder = backend or get_embedding_backend()
    limit = top_k or cfg.retrieval.top_k

    query_vectors = await embedder.embed_texts([query])
    if not query_vectors:
        return []

    result = await db.execute(
        _UPLOAD_RETRIEVAL_SQL,
        {
            "query_embedding": _query_vector(query_vectors[0]),
            "user_id": user_id,
            "top_k": limit,
        },
    )

    return [_row_to_chunk(row, source_type="upload") for row in result]


async def retrieve_merged_chunks(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Retrieve and merge corpus + user-upload chunks for one query."""
    per_source_k = top_k or (settings or get_settings()).retrieval.top_k
    corpus = await retrieve_document_chunks(
        db,
        query,
        top_k=per_source_k,
        backend=backend,
        settings=settings,
    )
    uploads = await retrieve_user_upload_chunks(
        db,
        query,
        user_id,
        top_k=per_source_k,
        backend=backend,
        settings=settings,
    )
    merged = _merge_chunks(corpus + uploads, top_k=per_source_k)
    return merged


def _merge_chunks(chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
    best_by_id: dict[uuid.UUID, RetrievedChunk] = {}
    for chunk in chunks:
        existing = best_by_id.get(chunk.chunk_id)
        if existing is None or chunk.score > existing.score:
            best_by_id[chunk.chunk_id] = chunk
    ranked = sorted(best_by_id.values(), key=lambda item: item.score, reverse=True)
    return ranked[:top_k]


async def retrieve_multi_query(
    db: AsyncSession,
    queries: list[str],
    user_id: uuid.UUID,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Run multi-query retrieval and deduplicate by chunk id."""
    cfg = settings or get_settings()
    limit = top_k or cfg.retrieval.multi_query_top_k
    combined: list[RetrievedChunk] = []

    for query in queries:
        results = await retrieve_merged_chunks(
            db,
            query,
            user_id,
            top_k=limit,
            backend=backend,
            settings=settings,
        )
        combined.extend(results)

    return _merge_chunks(combined, top_k=limit)


def format_retrieved_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(no relevant documents retrieved)"

    sections: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        source_label = "Statute" if chunk.source_type == "corpus" else "User upload"
        sections.append(
            "\n".join(
                [
                    f"[{index}] {source_label}: {chunk.document_title}",
                    f"document_id={chunk.document_id} chunk_id={chunk.chunk_id} "
                    f"chunk_index={chunk.chunk_index}",
                    chunk.text.strip(),
                ]
            )
        )
    return "\n\n---\n\n".join(sections)


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[CitationRead]:
    return [
        CitationRead(
            chunk_id=chunk.chunk_id,
            source_type=chunk.source_type,
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            chunk_index=chunk.chunk_index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )
        for chunk in chunks
    ]


class DharmiqPgVectorRetriever(BaseRetriever):
    """LangChain retriever backed by Dharmiq pgvector SQL search."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    db: AsyncSession
    user_id: uuid.UUID
    top_k: int = 5
    backend: EmbeddingBackend | None = None
    settings: Settings | None = None

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        chunks = await retrieve_merged_chunks(
            self.db,
            query,
            self.user_id,
            top_k=self.top_k,
            backend=self.backend,
            settings=self.settings,
        )
        return [
            Document(
                page_content=chunk.text,
                metadata={
                    "chunk_id": str(chunk.chunk_id),
                    "document_id": str(chunk.document_id),
                    "document_title": chunk.document_title,
                    "source_type": chunk.source_type,
                    "chunk_index": chunk.chunk_index,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "score": chunk.score,
                },
            )
            for chunk in chunks
        ]

    def _get_relevant_documents(self, query: str) -> list[Document]:
        raise NotImplementedError("Use async retrieval via retrieve_merged_chunks")
