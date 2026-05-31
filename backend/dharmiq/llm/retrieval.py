from __future__ import annotations

import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.llm.embeddings import EmbeddingBackend, get_embedding_backend


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
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
    document_id: uuid.UUID
    document_title: str
    text: str
    score: float
    chunk_index: int
    page_start: int | None
    page_end: int | None


def _query_vector(values: list[float]) -> PgVector:
    return PgVector(values)


_RETRIEVAL_SQL = text("""
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


async def retrieve_document_chunks(
    db: AsyncSession,
    query: str,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Return the most similar document chunks for a natural-language query."""
    cfg = settings or get_settings()
    embedder = backend or get_embedding_backend()
    limit = top_k or cfg.retrieval.top_k

    query_vectors = await embedder.embed_texts([query])
    if not query_vectors:
        return []

    result = await db.execute(
        _RETRIEVAL_SQL,
        {
            "query_embedding": _query_vector(query_vectors[0]),
            "top_k": limit,
        },
    )

    retrieved: list[RetrievedChunk] = []
    for row in result.mappings():
        distance = float(row["distance"])
        retrieved.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                document_title=row["document_title"],
                text=row["text"],
                score=1.0 - distance,
                chunk_index=row["chunk_index"],
                page_start=row["page_start"],
                page_end=row["page_end"],
            )
        )
    return retrieved
