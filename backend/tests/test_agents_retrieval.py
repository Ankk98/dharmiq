from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.agents.graph import build_agent_graph
from dharmiq.agents.progress import ProgressEmitter
from dharmiq.agents.runtime import GraphRuntime
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
from dharmiq.llm.agents.clarifier import run_clarifier
from dharmiq.llm.agents.query_rewriter import run_query_rewriter
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.llm.openrouter_client import OpenRouterClient, get_openrouter_client
from dharmiq.llm.prompts.loader import load_prompt
from dharmiq.llm.retrieval import (
    DharmiqPgVectorRetriever,
    retrieve_merged_chunks,
    retrieve_multi_query,
)
from tests.litellm_helpers import chat_response_dict, mock_litellm_acompletion
from tests.rerank_helpers import mock_rerank, weak_rerank
from tests.vector_helpers import blend_vectors, unit_vector


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
async def _clean_retrieval_tables() -> None:
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


async def _seed_corpus(db: AsyncSession) -> DocumentChunk:
    document = SourceDocument(
        source_id=f"test-act-{uuid.uuid4()}",
        title="Consumer Protection Act (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-corpus",
        file_path="/tmp/consumer.pdf",
    )
    db.add(document)
    await db.flush()

    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="Section 12 covers deficiency in service and refund rights.",
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(0)),
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(chunk)
    return chunk


async def _create_user(db: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"retrieval-{uuid.uuid4()}@example.com",
        hashed_password="hashed",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _seed_upload(db: AsyncSession, user_id: uuid.UUID) -> tuple[UserUpload, UserUploadChunk]:
    upload = UserUpload(
        user_id=user_id,
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
        embedding=PgVector(unit_vector(1)),
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(upload)
    await db.refresh(chunk)
    return upload, chunk


@pytest.mark.asyncio
async def test_retrieve_merged_chunks_includes_corpus_and_uploads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "Can I get a refund for a defective product?"
    backend = _MappedEmbeddingBackend({query: blend_vectors(unit_vector(0), unit_vector(1))})
    user_id = uuid.uuid4()

    async with factory() as db:
        user_id = await _create_user(db)
        corpus_chunk = await _seed_corpus(db)
        upload, upload_chunk = await _seed_upload(db, user_id)
        session = ChatSession(user_id=user_id)
        db.add(session)
        await db.flush()
        db.add(ChatSessionUpload(session_id=session.id, upload_id=upload.id))
        await db.commit()
        results = await retrieve_merged_chunks(
            db,
            query,
            user_id,
            attached_upload_ids=[upload.id],
            top_k=2,
            backend=backend,
        )

    assert len(results) == 2
    source_types = {item.source_type for item in results}
    assert source_types == {"corpus", "upload"}
    chunk_ids = {item.chunk_id for item in results}
    assert corpus_chunk.id in chunk_ids
    assert upload_chunk.id in chunk_ids


@pytest.mark.asyncio
async def test_retrieve_multi_query_deduplicates_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query_a = "refund rights"
    query_b = "defective product refund"
    backend = _MappedEmbeddingBackend(
        {
            query_a: unit_vector(0),
            query_b: unit_vector(0),
        }
    )
    user_id = uuid.uuid4()

    async with factory() as db:
        user_id = await _create_user(db)
        await _seed_corpus(db)
        results = (
            await retrieve_multi_query(
                db,
                [query_a, query_b],
                user_id,
                top_k=3,
                backend=backend,
            )
        ).chunks

    assert len(results) == 1


@pytest.mark.asyncio
async def test_langchain_retriever_wraps_pgvector_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    query = "employment termination notice"
    backend = _MappedEmbeddingBackend({query: unit_vector(1)})
    user_id = uuid.uuid4()

    async with factory() as db:
        user_id = await _create_user(db)
        upload, _upload_chunk = await _seed_upload(db, user_id)
        retriever = DharmiqPgVectorRetriever(
            db=db,
            user_id=user_id,
            attached_upload_ids=[upload.id],
            top_k=1,
            backend=backend,
        )
        documents = await retriever.ainvoke(query)

    assert len(documents) == 1
    assert documents[0].metadata["source_type"] == "upload"
    assert "terminated" in documents[0].page_content


def test_load_prompt_templates() -> None:
    clarifier = load_prompt("clarifier")
    rendered = clarifier.render_user(
        history="user: hello",
        user_question="What are my rights?",
    )
    assert "What are my rights?" in rendered
    assert "user: hello" in rendered


@pytest.mark.asyncio
async def test_run_clarifier_parses_json_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "topic": "police_arrest",
        "needs_more_info": True,
        "followup_questions": ["Are you under arrest?"],
        "reason": "Need arrest status",
    }
    mock_litellm_acompletion(
        monkeypatch,
        [chat_response_dict(json.dumps(payload), total_tokens=42)],
    )

    client = OpenRouterClient()
    result = await run_clarifier(
        client,
        user_question="Police stopped me",
        history=[],
    )

    assert result.needs_more_info is True
    assert result.followup_questions == ["Are you under arrest?"]
    assert result.tokens_used == 42


@pytest.mark.asyncio
async def test_run_query_rewriter_returns_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"queries": ["Section 12 refund rights", "consumer protection defective goods"]}
    mock_litellm_acompletion(
        monkeypatch,
        [chat_response_dict(json.dumps(payload), total_tokens=30)],
    )

    client = OpenRouterClient()
    result = await run_query_rewriter(
        client,
        user_question="My product arrived damaged",
        topic="consumer_refund",
        facts="Ordered online last week",
    )

    assert len(result.queries) == 2
    assert result.tokens_used == 30


@pytest.mark.asyncio
async def test_refusal_node_no_answerer_call(
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

    document = SourceDocument(
        source_id=f"refusal-{uuid.uuid4()}",
        title="Constitution of India (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-refusal",
        file_path="/tmp/constitution.pdf",
    )
    db.add(document)
    await db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            text="Article 22 protects against arbitrary arrest and detention.",
            page_start=1,
            page_end=1,
            embedding=PgVector(unit_vector(0)),
        )
    )

    user = User(email=f"refusal-{uuid.uuid4()}@example.com", hashed_password="hashed")
    db.add(user)
    await db.flush()
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

    captured_steps: list[str] = []

    async def _capture_publish(event) -> None:
        if event.payload.get("step_id"):
            captured_steps.append(str(event.payload["step_id"]))

    emitter = ProgressEmitter(
        db,
        chat_request.id,
        publish=_capture_publish,
    )
    runtime = GraphRuntime(
        db=db,
        settings=load_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[user_msg],
        user_msg=user_msg,
        emitter=emitter,
    )

    with patch(
        "dharmiq.llm.retrieval.get_embedding_backend",
        return_value=_MappedEmbeddingBackend({"Article 22 arrest rights": unit_vector(0)}),
    ):
        graph = build_agent_graph()
        final_state = await graph.ainvoke(
            {
                "user_message": user_msg.content,
                "clarifier_round": 0,
                "force_answer": False,
                "total_tokens": 0,
                "max_validator_retries": load_settings().chat.max_validator_retries,
            },
            {"configurable": {"thread_id": str(chat_request.id), "runtime": runtime}},
        )

    await emitter.close()
    assert final_state.get("weak_retrieval") is True
    assert "answerer" not in captured_steps


@pytest.mark.asyncio
async def test_clarifier_three_round_cap(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch, handler=weak_rerank)
    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": True,
        "followup_questions": ["Are you currently detained?"],
        "reason": "Need more facts",
    }
    rewriter = {"queries": ["Article 22 arrest rights"]}
    mock_litellm_acompletion(
        monkeypatch,
        [json.dumps(clarifier), json.dumps(rewriter)],
    )

    document = SourceDocument(
        source_id=f"clarifier-cap-{uuid.uuid4()}",
        title="Constitution of India (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-clarifier-cap",
        file_path="/tmp/constitution.pdf",
    )
    db.add(document)
    await db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            text="Article 22 protects against arbitrary arrest and detention.",
            page_start=1,
            page_end=1,
            embedding=PgVector(unit_vector(0)),
        )
    )

    user = User(email=f"clarifier-cap-{uuid.uuid4()}@example.com", hashed_password="hashed")
    db.add(user)
    await db.flush()
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
        content="Police stopped me",
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

    with patch(
        "dharmiq.llm.retrieval.get_embedding_backend",
        return_value=_MappedEmbeddingBackend({"Article 22 arrest rights": unit_vector(0)}),
    ):
        graph = build_agent_graph()
        final_state = await graph.ainvoke(
            {
                "user_message": user_msg.content,
                "clarifier_round": 3,
                "force_answer": False,
                "total_tokens": 0,
                "max_validator_retries": load_settings().chat.max_validator_retries,
            },
            {"configurable": {"thread_id": str(chat_request.id), "runtime": runtime}},
        )

    assert final_state.get("needs_clarification") is True
    assert final_state.get("search_queries")
    assert final_state.get("weak_retrieval") is True
