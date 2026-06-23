from __future__ import annotations

import uuid
from functools import lru_cache
from typing import TYPE_CHECKING

from pgvector import Vector as PgVector
from sqlalchemy import TextClause, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings

if TYPE_CHECKING:
    from dharmiq.llm.embeddings import EmbeddingBackend
    from dharmiq.llm.retrieval import RetrievedChunk


_CORPUS_SEARCHABLE_FILTER = """
    AND (
        (dc.metadata->>'schema_version' = 'v02' AND dc.parent_chunk_id IS NOT NULL)
        OR (
            COALESCE(dc.metadata->>'schema_version', '') <> 'v02'
            AND NOT EXISTS (
                SELECT 1
                FROM document_chunks v02
                WHERE v02.document_id = dc.document_id
                  AND v02.metadata->>'schema_version' = 'v02'
                  AND v02.parent_chunk_id IS NOT NULL
            )
        )
    )
"""

_UPLOAD_SEARCHABLE_FILTER = """
    AND (
        (uuc.metadata->>'schema_version' = 'v02' AND uuc.parent_chunk_id IS NOT NULL)
        OR (
            COALESCE(uuc.metadata->>'schema_version', '') <> 'v02'
            AND NOT EXISTS (
                SELECT 1
                FROM user_upload_chunks v02
                WHERE v02.upload_id = uuc.upload_id
                  AND v02.metadata->>'schema_version' = 'v02'
                  AND v02.parent_chunk_id IS NOT NULL
            )
        )
    )
"""


def _corpus_document_join_and_filter(*, include_superseded: bool) -> str:
    """Latest indexed document per source_id; optionally exclude superseded/repealed."""
    status_filter = "" if include_superseded else "AND sd.status = 'in_force'"
    return f"""
    JOIN (
        SELECT DISTINCT ON (source_id)
            id AS document_id,
            source_id,
            status,
            title
        FROM source_documents
        WHERE indexed_at IS NOT NULL
        ORDER BY source_id, version DESC
    ) sd ON dc.document_id = sd.document_id
    {status_filter}
    """


@lru_cache(maxsize=2)
def _corpus_vector_sql(include_superseded: bool) -> TextClause:
    document_filter = _corpus_document_join_and_filter(include_superseded=include_superseded)
    return text(f"""
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        sd.title AS document_title,
        dc.text,
        dc.chunk_index,
        dc.page_start,
        dc.page_end,
        dc.parent_chunk_id,
        parent.text AS parent_text,
        dc.embedding <=> :query_embedding AS distance
    FROM document_chunks dc
    {document_filter}
    LEFT JOIN document_chunks parent ON dc.parent_chunk_id = parent.id
    WHERE dc.embedding IS NOT NULL
    {_CORPUS_SEARCHABLE_FILTER}
    ORDER BY distance
    LIMIT :top_k
    """)


@lru_cache(maxsize=2)
def _corpus_bm25_sql(include_superseded: bool) -> TextClause:
    document_filter = _corpus_document_join_and_filter(include_superseded=include_superseded)
    return text(f"""
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        sd.title AS document_title,
        dc.text,
        dc.chunk_index,
        dc.page_start,
        dc.page_end,
        dc.parent_chunk_id,
        parent.text AS parent_text,
        ts_rank(dc.search_vector, plainto_tsquery('english', :query)) AS rank
    FROM document_chunks dc
    {document_filter}
    LEFT JOIN document_chunks parent ON dc.parent_chunk_id = parent.id
    WHERE dc.search_vector @@ plainto_tsquery('english', :query)
    {_CORPUS_SEARCHABLE_FILTER}
    ORDER BY rank DESC
    LIMIT :top_k
    """)


def _include_superseded(settings: Settings | None) -> bool:
    cfg = settings or get_settings()
    return cfg.retrieval.include_superseded


_UPLOAD_VECTOR_SQL = text(f"""
    SELECT
        uuc.id AS chunk_id,
        uuc.upload_id AS document_id,
        uu.original_filename AS document_title,
        uuc.text,
        uuc.chunk_index,
        uuc.page_start,
        uuc.page_end,
        uuc.parent_chunk_id,
        parent.text AS parent_text,
        uuc.embedding <=> :query_embedding AS distance
    FROM user_upload_chunks uuc
    JOIN user_uploads uu ON uuc.upload_id = uu.id
    LEFT JOIN user_upload_chunks parent ON uuc.parent_chunk_id = parent.id
    WHERE uu.user_id = :user_id
      AND uu.deleted_at IS NULL
      AND uuc.embedding IS NOT NULL
      AND uuc.upload_id = ANY(:attached_upload_ids)
    {_UPLOAD_SEARCHABLE_FILTER}
    ORDER BY distance
    LIMIT :top_k
""").bindparams(bindparam("attached_upload_ids", type_=ARRAY(PGUUID())))


_UPLOAD_BM25_SQL = text(f"""
    SELECT
        uuc.id AS chunk_id,
        uuc.upload_id AS document_id,
        uu.original_filename AS document_title,
        uuc.text,
        uuc.chunk_index,
        uuc.page_start,
        uuc.page_end,
        uuc.parent_chunk_id,
        parent.text AS parent_text,
        ts_rank(uuc.search_vector, plainto_tsquery('english', :query)) AS rank
    FROM user_upload_chunks uuc
    JOIN user_uploads uu ON uuc.upload_id = uu.id
    LEFT JOIN user_upload_chunks parent ON uuc.parent_chunk_id = parent.id
    WHERE uu.user_id = :user_id
      AND uu.deleted_at IS NULL
      AND uuc.search_vector @@ plainto_tsquery('english', :query)
      AND uuc.upload_id = ANY(:attached_upload_ids)
    {_UPLOAD_SEARCHABLE_FILTER}
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


def _answer_text(child_text: str, parent_text: str | None) -> str:
    if parent_text and parent_text.strip():
        return parent_text
    return child_text


def _row_to_corpus_chunk(row: object, *, hydrate_parent: bool = False) -> RetrievedChunk:
    from dharmiq.llm.retrieval import RetrievedChunk

    mapping = row._mapping  # type: ignore[attr-defined]
    if "distance" in mapping:
        score = 1.0 - float(mapping["distance"])
    else:
        score = float(mapping["rank"])
    child_text = mapping["text"]
    parent_text = mapping.get("parent_text")
    text = _answer_text(child_text, parent_text) if hydrate_parent else child_text
    return RetrievedChunk(
        chunk_id=mapping["chunk_id"],
        source_type="corpus",
        document_id=mapping["document_id"],
        document_title=mapping["document_title"],
        text=text,
        score=score,
        chunk_index=mapping["chunk_index"],
        page_start=mapping["page_start"],
        page_end=mapping["page_end"],
    )


def _row_to_upload_chunk(row: object, *, hydrate_parent: bool = False) -> RetrievedChunk:
    from dharmiq.llm.retrieval import RetrievedChunk

    mapping = row._mapping  # type: ignore[attr-defined]
    if "distance" in mapping:
        score = 1.0 - float(mapping["distance"])
    else:
        score = float(mapping["rank"])
    child_text = mapping["text"]
    parent_text = mapping.get("parent_text")
    text = _answer_text(child_text, parent_text) if hydrate_parent else child_text
    return RetrievedChunk(
        chunk_id=mapping["chunk_id"],
        source_type="upload",
        document_id=mapping["document_id"],
        document_title=mapping["document_title"],
        text=text,
        score=score,
        chunk_index=mapping["chunk_index"],
        page_start=mapping["page_start"],
        page_end=mapping["page_end"],
    )


async def hydrate_parent_texts(
    db: AsyncSession,
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """Swap child chunk text for parent section text when parent_chunk_id is set."""
    from dharmiq.llm.retrieval import RetrievedChunk as Chunk

    if not chunks:
        return []

    corpus_ids = [chunk.chunk_id for chunk in chunks if chunk.source_type == "corpus"]
    upload_ids = [chunk.chunk_id for chunk in chunks if chunk.source_type == "upload"]

    parent_text_by_id: dict[uuid.UUID, str] = {}

    if corpus_ids:
        result = await db.execute(
            text(
                """
                SELECT child.id AS chunk_id, parent.text AS parent_text
                FROM document_chunks child
                JOIN document_chunks parent ON child.parent_chunk_id = parent.id
                WHERE child.id = ANY(:chunk_ids)
                """
            ),
            {"chunk_ids": corpus_ids},
        )
        for row in result:
            parent_text_by_id[row.chunk_id] = row.parent_text

    if upload_ids:
        result = await db.execute(
            text(
                """
                SELECT child.id AS chunk_id, parent.text AS parent_text
                FROM user_upload_chunks child
                JOIN user_upload_chunks parent ON child.parent_chunk_id = parent.id
                WHERE child.id = ANY(:chunk_ids)
                """
            ),
            {"chunk_ids": upload_ids},
        )
        for row in result:
            parent_text_by_id[row.chunk_id] = row.parent_text

    hydrated: list[RetrievedChunk] = []
    for chunk in chunks:
        parent_text = parent_text_by_id.get(chunk.chunk_id)
        if not parent_text:
            hydrated.append(chunk)
            continue
        hydrated.append(
            Chunk(
                chunk_id=chunk.chunk_id,
                source_type=chunk.source_type,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                text=parent_text,
                score=chunk.score,
                chunk_index=chunk.chunk_index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
            )
        )
    return hydrated


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
    hydrate_parent: bool = False,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    query_vector = await _embed_query(query, backend)
    if query_vector is None:
        return []

    include_superseded = _include_superseded(settings)
    result = await db.execute(
        _corpus_vector_sql(include_superseded),
        {
            "query_embedding": PgVector(query_vector),
            "top_k": top_k,
        },
    )
    return [_row_to_corpus_chunk(row, hydrate_parent=hydrate_parent) for row in result]


async def bm25_search_corpus(
    db: AsyncSession,
    query: str,
    *,
    top_k: int,
    hydrate_parent: bool = False,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    if not query.strip():
        return []

    include_superseded = _include_superseded(settings)
    result = await db.execute(
        _corpus_bm25_sql(include_superseded),
        {"query": query, "top_k": top_k},
    )
    return [_row_to_corpus_chunk(row, hydrate_parent=hydrate_parent) for row in result]


async def vector_search_uploads(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID],
    *,
    top_k: int,
    backend: EmbeddingBackend,
    hydrate_parent: bool = False,
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
    return [_row_to_upload_chunk(row, hydrate_parent=hydrate_parent) for row in result]


async def bm25_search_uploads(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID],
    *,
    top_k: int,
    hydrate_parent: bool = False,
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
    return [_row_to_upload_chunk(row, hydrate_parent=hydrate_parent) for row in result]


async def hybrid_search_corpus(
    db: AsyncSession,
    query: str,
    *,
    vector_top_k: int,
    bm25_top_k: int,
    rrf_k: int,
    rrf_top_k: int,
    backend: EmbeddingBackend,
    hydrate_parent: bool = False,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    vector_hits = await vector_search_corpus(
        db,
        query,
        top_k=vector_top_k,
        backend=backend,
        hydrate_parent=hydrate_parent,
        settings=settings,
    )
    bm25_hits = await bm25_search_corpus(
        db,
        query,
        top_k=bm25_top_k,
        hydrate_parent=hydrate_parent,
        settings=settings,
    )
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
    hydrate_parent: bool = False,
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
        hydrate_parent=hydrate_parent,
    )
    bm25_hits = await bm25_search_uploads(
        db,
        query,
        user_id,
        attached_upload_ids,
        top_k=bm25_top_k,
        hydrate_parent=hydrate_parent,
    )
    return reciprocal_rank_fusion(vector_hits, bm25_hits, k=rrf_k, top_k=rrf_top_k)
