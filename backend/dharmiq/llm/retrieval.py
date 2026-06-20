from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import BaseModel, ConfigDict
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


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    weak_retrieval: bool
    top_rerank_score: float


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
    chunk_index: int = 0
    page_start: int | None = None
    page_end: int | None = None
    marker: int | None = None
    section_label: str | None = None
    quote_text: str | None = None
    quote_start_char: int | None = None
    quote_end_char: int | None = None


def _chunk_with_score(chunk: RetrievedChunk, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        source_type=chunk.source_type,
        document_id=chunk.document_id,
        document_title=chunk.document_title,
        text=chunk.text,
        score=score,
        chunk_index=chunk.chunk_index,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
    )


def assess_retrieval_strength(
    chunks: list[RetrievedChunk],
    settings: Settings | None = None,
) -> tuple[bool, float]:
    cfg = settings or get_settings()
    if not chunks:
        return True, 0.0

    top_score = max(chunk.score for chunk in chunks)
    above_threshold = sum(
        1 for chunk in chunks if chunk.score >= cfg.retrieval.min_rerank_score
    )
    weak = (
        top_score < cfg.retrieval.min_rerank_score
        or above_threshold < cfg.retrieval.min_relevant_chunks
    )
    return weak, top_score


def _merge_chunks(chunks: list[RetrievedChunk], *, top_k: int) -> list[RetrievedChunk]:
    best_by_id: dict[uuid.UUID, RetrievedChunk] = {}
    for chunk in chunks:
        existing = best_by_id.get(chunk.chunk_id)
        if existing is None or chunk.score > existing.score:
            best_by_id[chunk.chunk_id] = chunk
    ranked = sorted(best_by_id.values(), key=lambda item: item.score, reverse=True)
    return ranked[:top_k]


async def retrieve_document_chunks(
    db: AsyncSession,
    query: str,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Return the most similar corpus document chunks for a natural-language query."""
    from dharmiq.retrieval.hybrid import hybrid_search_corpus

    cfg = settings or get_settings()
    embedder = backend or get_embedding_backend()
    limit = top_k or cfg.retrieval.rerank_top_k

    return await hybrid_search_corpus(
        db,
        query,
        vector_top_k=cfg.retrieval.vector_top_k,
        bm25_top_k=cfg.retrieval.bm25_top_k,
        rrf_k=cfg.retrieval.rrf_k,
        rrf_top_k=limit,
        backend=embedder,
    )


async def retrieve_user_upload_chunks(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID] | None = None,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Return upload chunks scoped to explicitly attached uploads only."""
    from dharmiq.retrieval.hybrid import hybrid_search_uploads

    cfg = settings or get_settings()
    embedder = backend or get_embedding_backend()
    limit = top_k or cfg.retrieval.rerank_top_k
    attached = attached_upload_ids or []

    return await hybrid_search_uploads(
        db,
        query,
        user_id,
        attached,
        vector_top_k=cfg.retrieval.vector_top_k,
        bm25_top_k=cfg.retrieval.bm25_top_k,
        rrf_k=cfg.retrieval.rrf_k,
        rrf_top_k=limit,
        backend=embedder,
    )


async def retrieve_merged_chunks(
    db: AsyncSession,
    query: str,
    user_id: uuid.UUID,
    attached_upload_ids: list[uuid.UUID] | None = None,
    *,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    """Retrieve and merge corpus + attached upload chunks for one query."""
    cfg = settings or get_settings()
    per_source_k = top_k or cfg.retrieval.rrf_top_k
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
        attached_upload_ids,
        top_k=per_source_k,
        backend=backend,
        settings=settings,
    )
    return _merge_chunks(corpus + uploads, top_k=per_source_k)


async def _rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_k: int,
    settings: Settings | None = None,
) -> list[RetrievedChunk]:
    from dharmiq.retrieval.reranker import rerank

    if not chunks:
        return []

    cfg = settings or get_settings()
    output = await rerank(query, [chunk.text for chunk in chunks], cfg, top_n=top_k)
    reranked: list[RetrievedChunk] = []
    for index, score in zip(output.indices, output.scores, strict=True):
        reranked.append(_chunk_with_score(chunks[index], score))
    return reranked


async def retrieve_multi_query(
    db: AsyncSession,
    queries: list[str],
    user_id: uuid.UUID,
    *,
    rerank_query: str | None = None,
    attached_upload_ids: list[uuid.UUID] | None = None,
    top_k: int | None = None,
    backend: EmbeddingBackend | None = None,
    settings: Settings | None = None,
) -> RetrievalResult:
    """Run hybrid multi-query retrieval, rerank, and assess retrieval strength."""
    cfg = settings or get_settings()
    rrf_limit = cfg.retrieval.rrf_top_k
    rerank_limit = top_k or cfg.retrieval.rerank_top_k
    combined: list[RetrievedChunk] = []

    for query in queries:
        results = await retrieve_merged_chunks(
            db,
            query,
            user_id,
            attached_upload_ids,
            top_k=rrf_limit,
            backend=backend,
            settings=settings,
        )
        combined.extend(results)

    merged = _merge_chunks(combined, top_k=rrf_limit)
    ranking_query = rerank_query or (queries[0] if queries else "")
    reranked = await _rerank_chunks(
        ranking_query,
        merged,
        top_k=rerank_limit,
        settings=settings,
    )
    from dharmiq.retrieval.hybrid import hydrate_parent_texts

    hydrated = await hydrate_parent_texts(db, reranked)
    weak, top_score = assess_retrieval_strength(hydrated, settings)
    return RetrievalResult(chunks=hydrated, weak_retrieval=weak, top_rerank_score=top_score)


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
    """LangChain retriever backed by Dharmiq hybrid retrieval."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    db: AsyncSession
    user_id: uuid.UUID
    attached_upload_ids: list[uuid.UUID] = []
    top_k: int = 5
    backend: EmbeddingBackend | None = None
    settings: Settings | None = None

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        result = await retrieve_multi_query(
            self.db,
            [query],
            self.user_id,
            rerank_query=query,
            attached_upload_ids=self.attached_upload_ids,
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
            for chunk in result.chunks
        ]

    def _get_relevant_documents(self, query: str) -> list[Document]:
        raise NotImplementedError("Use async retrieval via retrieve_multi_query")
