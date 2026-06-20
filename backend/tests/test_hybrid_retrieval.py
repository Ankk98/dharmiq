from __future__ import annotations

import json
import uuid

import pytest
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.agents.graph import build_agent_graph
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.config.settings import load_settings
from dharmiq.db.models.chats import (
    ChatMessage,
    ChatRequest,
    ChatRequestStatus,
    ChatSession,
    ChatSessionUpload,
    MessageRole,
)
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.models.uploads import UserUpload, UserUploadChunk
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.llm.openrouter_client import get_openrouter_client
from dharmiq.llm.retrieval import retrieve_user_upload_chunks
from dharmiq.retrieval.hybrid import (
    bm25_search_corpus,
    hybrid_search_corpus,
    reciprocal_rank_fusion,
    vector_search_corpus,
)
from tests.litellm_helpers import mock_litellm_acompletion
from tests.rerank_helpers import mock_rerank, weak_rerank
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
async def _clean_hybrid_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM chat_session_uploads"))
        await db.execute(text("DELETE FROM chat_sessions"))
        await db.execute(text("DELETE FROM user_upload_chunks"))
        await db.execute(text("DELETE FROM user_uploads"))
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


async def _seed_crpc_chunks(db: AsyncSession) -> tuple[DocumentChunk, DocumentChunk]:
    document = SourceDocument(
        source_id=f"crpc-{uuid.uuid4()}",
        title="Code of Criminal Procedure, 1973",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-crpc",
        file_path="/tmp/crpc.pdf",
    )
    db.add(document)
    await db.flush()

    section_41 = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="Section 41 CrPC — When police may arrest without warrant.",
        page_start=41,
        page_end=41,
        embedding=PgVector(unit_vector(1)),
    )
    unrelated = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        text="Section 100 covers search of place used for depositing stolen property.",
        page_start=100,
        page_end=100,
        embedding=PgVector(unit_vector(0)),
    )
    db.add_all([section_41, unrelated])
    await db.commit()
    await db.refresh(section_41)
    await db.refresh(unrelated)
    return section_41, unrelated


async def _create_user(db: AsyncSession) -> User:
    user = User(email=f"hybrid-{uuid.uuid4()}@example.com", hashed_password="hashed")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_bm25_finds_exact_section_number() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "Section 41 CrPC"

    async with factory() as db:
        section_41, _ = await _seed_crpc_chunks(db)
        results = await bm25_search_corpus(db, query, top_k=3)

    assert results
    top_ids = [chunk.chunk_id for chunk in results[:3]]
    assert section_41.id in top_ids


@pytest.mark.asyncio
async def test_rrf_beats_vector_only() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "Section 41 CrPC arrest without warrant"
    backend = _MappedEmbeddingBackend({query: unit_vector(0)})

    async with factory() as db:
        section_41, unrelated = await _seed_crpc_chunks(db)
        vector_hits = await vector_search_corpus(db, query, top_k=5, backend=backend)
        bm25_hits = await bm25_search_corpus(db, query, top_k=5)
        merged = reciprocal_rank_fusion(vector_hits, bm25_hits, k=60, top_k=5)

    assert vector_hits[0].chunk_id == unrelated.id
    assert merged[0].chunk_id == section_41.id


@pytest.mark.asyncio
async def test_hybrid_search_corpus_combines_legs() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "Section 41 CrPC"
    backend = _MappedEmbeddingBackend({query: unit_vector(1)})
    settings = load_settings()

    async with factory() as db:
        section_41, _ = await _seed_crpc_chunks(db)
        results = await hybrid_search_corpus(
            db,
            query,
            vector_top_k=settings.retrieval.vector_top_k,
            bm25_top_k=settings.retrieval.bm25_top_k,
            rrf_k=settings.retrieval.rrf_k,
            rrf_top_k=settings.retrieval.rrf_top_k,
            backend=backend,
        )

    assert results[0].chunk_id == section_41.id


@pytest.mark.asyncio
async def test_upload_retrieval_requires_attach(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_rerank(monkeypatch)
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "termination notice period"

    async with factory() as db:
        user = await _create_user(db)
        upload = UserUpload(
            user_id=user.id,
            original_filename="contract.pdf",
            file_path="/tmp/contract.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            content_hash="hash-upload",
        )
        db.add(upload)
        await db.flush()

        chunk = UserUploadChunk(
            upload_id=upload.id,
            chunk_index=0,
            text="The employee may be terminated with 30 days notice.",
            page_start=1,
            page_end=1,
            embedding=PgVector(unit_vector(0)),
        )
        db.add(chunk)
        await db.commit()
        await db.refresh(chunk)

        unattached = await retrieve_user_upload_chunks(
            db,
            query,
            user.id,
            attached_upload_ids=[],
            backend=_MappedEmbeddingBackend({query: unit_vector(0)}),
        )
        assert unattached == []

        session = ChatSession(user_id=user.id)
        db.add(session)
        await db.flush()
        db.add(ChatSessionUpload(session_id=session.id, upload_id=upload.id))
        await db.commit()

        attached = await retrieve_user_upload_chunks(
            db,
            query,
            user.id,
            attached_upload_ids=[upload.id],
            backend=_MappedEmbeddingBackend({query: unit_vector(0)}),
        )
        assert len(attached) == 1
        assert attached[0].chunk_id == chunk.id


@pytest.mark.asyncio
async def test_weak_retrieval_refusal(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch, handler=weak_rerank)
    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": False,
        "followup_questions": [],
        "reason": "Enough detail",
    }
    rewriter = {"queries": ["Article 22 arrest rights"]}
    mock_litellm_acompletion(
        monkeypatch,
        [json.dumps(clarifier), json.dumps(rewriter)],
    )

    await _seed_crpc_chunks(db)
    user = await _create_user(db)
    session = ChatSession(user_id=user.id)
    db.add(session)
    await db.flush()
    chat_request = ChatRequest(
        session_id=session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
    )
    db.add(chat_request)
    user_msg = ChatMessage(
        session_id=session.id,
        user_id=user.id,
        role=MessageRole.USER,
        content="What are my arrest rights?",
    )
    db.add(user_msg)
    await db.commit()

    runtime = GraphRuntime(
        db=db,
        settings=load_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[user_msg],
        user_msg=user_msg,
    )

    monkeypatch.setattr(
        "dharmiq.llm.retrieval.get_embedding_backend",
        lambda: _MappedEmbeddingBackend({"Article 22 arrest rights": unit_vector(0)}),
    )
    graph = build_agent_graph()
    final_state: AgentGraphState = await graph.ainvoke(
        {
            "user_message": user_msg.content,
            "clarifier_round": 0,
            "force_answer": False,
            "total_tokens": 0,
            "max_validator_retries": load_settings().chat.max_validator_retries,
        },
        {"configurable": {"thread_id": str(chat_request.id), "runtime": runtime}},
    )

    assert final_state.get("weak_retrieval") is True
    assert "could not find sufficient sources" in (final_state.get("final_answer") or "").lower()
    assert final_state.get("draft_answer") == final_state.get("final_answer")
