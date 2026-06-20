from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector import Vector as PgVector
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from dharmiq.llm.embeddings import EmbeddingBackend
    from dharmiq.llm.retrieval import RetrievedChunk


_CORPUS_VECTOR_SQL = text("""
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


_CORPUS_BM25_SQL = text("""
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        sd.title AS document_title,
        dc.text,
        dc.chunk_index,
        dc.page_start,
        dc.page_end,
        ts_rank(dc.search_vector, plainto_tsquery('english', :query)) AS rank
    FROM document_chunks dc
    JOIN source_documents sd ON dc.document_id = sd.id
    WHERE dc.search_vector @@ plainto_tsquery('english', :query)
    ORDER BY rank DESC
    LIMIT :top_k
""")


_UPLOAD_VECTOR_SQL = text("""
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
      AND uuc.upload_id = ANY(:attached_upload_ids)
    ORDER BY distance
    LIMIT :top_k
""").bindparams(bindparam("attached_upload_ids", type_=ARRAY(PGUUID())))


_UPLOAD_BM25_SQL = text("""
    SELECT
        uuc.id AS chunk_id,
        uuc.upload_id AS document_id,
        uu.original_filename AS document_title,
        uuc.text,
        uuc.chunk_index,
        uuc.page_start,
        uuc.page_end,
        ts_rank(uuc.search_vector, plainto_tsquery('english', :query)) AS rank
    FROM user_upload_chunks uuc
    JOIN user_uploads uu ON uuc.upload_id = uu.id
    WHERE uu.user_id = :user_id
      AND uu.deleted_at IS NULL
      AND uuc.search_vector @@ plainto_tsquery('english', :query)
      AND uuc.upload_id = ANY(:attached_upload_ids)
    ORDER BY rank DESC
    LIMIT :top_k
""").bindparams(bindparam("attached_upload_ids", type_=ARRAY(PGUUID())))


def reciprocal_rank_fusion(
    *rankings: list[RetrievedChunk],
    k: int = 60,
    top_k: int = 20,
) -> list[RetrievedChunk]:
    """Merge ranked chunk lists with reciprocal rank fusion."""
    from dharmiq.llm.retrieval import RetrievedChunk as Chunk

    scores: dict[uuid.UUID, float] = {}
    best: dict[uuid.UUID, Chunk] = {}

    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            best[chunk.chunk_id] = chunk

    ranked_ids = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [
        Chunk(
            chunk_id=chunk_id,
            source_type=best[chunk_id].source_type,
            document_id=best[chunk_id].document_id,
            document_title=best[chunk_id].document_title,
            text=best[chunk_id].text,
            score=scores[chunk_id],
            chunk_index=best[chunk_id].chunk_index,
            page_start=best[chunk_id].page_start,
            page_end=best[chunk_id].page_end,
        )
        for chunk_id in ranked_ids[:top_k]
    ]


def _row_to_corpus_chunk(row: object) -> RetrievedChunk:
    from dharmiq.llm.retrieval import RetrievedChunk

    mapping = row._mapping  # type: ignore[attr-defined]
    if "distance" in mapping:
        score = 1.0 - float(mapping["distance"])
    else:
        score = float(mapping["rank"])
    return RetrievedChunk(
        chunk_id=mapping["chunk_id"],
        source_type="corpus",
        document_id=mapping["document_id"],
        document_title=mapping["document_title"],
        text=mapping["text"],
        score=score,
        chunk_index=mapping["chunk_index"],
        page_start=mapping["page_start"],
        page_end=mapping["page_end"],
    )


def _row_to_upload_chunk(row: object) -> RetrievedChunk:
    from dharmiq.llm.retrieval import RetrievedChunk

    mapping = row._mapping  # type: ignore[attr-defined]
    if "distance" in mapping:
        score = 1.0 - float(mapping["distance"])
    else:
        score = float(mapping["rank"])
    return RetrievedChunk(
        chunk_id=mapping["chunk_id"],
        source_type="upload",
        document_id=mapping["document_id"],
        document_title=mapping["document_title"],
        text=mapping["text"],
        score=score,
        chunk_index=mapping["chunk_index"],
        page_start=mapping["page_start"],
        page_end=mapping["page_end"],
    )


async def _embed_query(
    query: str,
    backend: EmbeddingBackend,
) -> list[float] | None:
    vectors = await backend.embed_texts([query])
    if not vectors:
        return None
    return vectors[0]


async def vector_search_corpus(
    db: AsyncSession,
    query: str,
    *,
    top_k: int,
    backend: EmbeddingBackend,
) -> list[RetrievedChunk]:
    query_vector = await _embed_query(query, backend)
    if query_vector is None:
        return []

    result = await db.execute(
        _CORPUS_VECTOR_SQL,
        {
            "query_embedding": PgVector(query_vector),
            "top_k": top_k,
        },
    )
    return [_row_to_corpus_chunk(row) for row in result]


async def bm25_search_corpus(
    db: AsyncSession,
    query: str,
    *,
    top_k: int,
) -> list[RetrievedChunk]:
    if not query.strip():
        return []

    result = await db.execute(
        _CORPUS_BM25_SQL,
        {"query": query, "top_k": top_k},
    )
    return [_row_to_corpus_chunk(row) for row in result]


async def vector_search_uploads(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID],
    *,
    top_k: int,
    backend: EmbeddingBackend,
) -> list[RetrievedChunk]:
    if not attached_upload_ids:
        return []

    query_vector = await _embed_query(query, backend)
    if query_vector is None:
        return []

    result = await db.execute(
        _UPLOAD_VECTOR_SQL,
        {
            "query_embedding": PgVector(query_vector),
            "user_id": user_id,
            "attached_upload_ids": attached_upload_ids,
            "top_k": top_k,
        },
    )
    return [_row_to_upload_chunk(row) for row in result]


async def bm25_search_uploads(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID],
    *,
    top_k: int,
) -> list[RetrievedChunk]:
    if not attached_upload_ids or not query.strip():
        return []

    result = await db.execute(
        _UPLOAD_BM25_SQL,
        {
            "query": query,
            "user_id": user_id,
            "attached_upload_ids": attached_upload_ids,
            "top_k": top_k,
        },
    )
    return [_row_to_upload_chunk(row) for row in result]


async def hybrid_search_corpus(
    db: AsyncSession,
    query: str,
    *,
    vector_top_k: int,
    bm25_top_k: int,
    rrf_k: int,
    rrf_top_k: int,
    backend: EmbeddingBackend,
) -> list[RetrievedChunk]:
    vector_hits = await vector_search_corpus(
        db,
        query,
        top_k=vector_top_k,
        backend=backend,
    )
    bm25_hits = await bm25_search_corpus(db, query, top_k=bm25_top_k)
    return reciprocal_rank_fusion(vector_hits, bm25_hits, k=rrf_k, top_k=rrf_top_k)


async def hybrid_search_uploads(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID],
    *,
    vector_top_k: int,
    bm25_top_k: int,
    rrf_k: int,
    rrf_top_k: int,
    backend: EmbeddingBackend,
) -> list[RetrievedChunk]:
    if not attached_upload_ids:
        return []

    vector_hits = await vector_search_uploads(
        db,
        query,
        user_id,
        attached_upload_ids,
        top_k=vector_top_k,
        backend=backend,
    )
    bm25_hits = await bm25_search_uploads(
        db,
        query,
        user_id,
        attached_upload_ids,
        top_k=bm25_top_k,
    )
    return reciprocal_rank_fusion(vector_hits, bm25_hits, k=rrf_k, top_k=rrf_top_k)
