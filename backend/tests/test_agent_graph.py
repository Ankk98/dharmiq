from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from pgvector import Vector as PgVector
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.checkpoint import close_checkpointer, get_checkpointer, reset_checkpointer_cache
from dharmiq.agents.graph import build_agent_graph
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.config.settings import get_settings
from dharmiq.db.models.chats import (
    ChatMessage,
    ChatRequest,
    ChatRequestStatus,
    ChatSession,
    MessageRole,
)
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.llm.openrouter_client import get_openrouter_client
from tests.litellm_helpers import mock_litellm_acompletion
from tests.rerank_helpers import mock_rerank
from tests.vector_helpers import unit_vector


class _StaticEmbeddingBackend(EmbeddingBackend):
    @property
    def dimensions(self) -> int:
        return 384

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [unit_vector(0) for _ in texts]


@pytest.fixture(autouse=True)
async def _clean_agent_graph_tables() -> None:
    await close_checkpointer()
    reset_checkpointer_cache()
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM llm_usage_events"))
        await db.execute(text("DELETE FROM chat_request_events"))
        await db.execute(text("DELETE FROM chat_requests"))
        await db.execute(text("DELETE FROM chat_messages"))
        await db.execute(text("DELETE FROM chat_sessions"))
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield
    await close_checkpointer()
    reset_checkpointer_cache()


async def _seed_corpus(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id=f"agent-graph-{uuid.uuid4()}",
        title="Constitution of India (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-agent-graph",
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
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=1,
            text="Article 22 also requires the grounds of arrest to be communicated.",
            page_start=1,
            page_end=1,
            embedding=PgVector(unit_vector(0)),
        )
    )
    await db.commit()


def _mock_full_pipeline_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": False,
        "followup_questions": [],
        "reason": "Enough detail",
    }
    rewriter = {"queries": ["Article 22 arrest rights", "police station questioning rights"]}
    answer = (
        "You have protections under Article 22 [1].\n\n"
        "> Article 22 protects against arbitrary arrest and detention.\n\n"
        "This is not legal advice."
    )
    validator = {
        "must_regenerate": False,
        "issues": [],
        "regeneration_instructions": "",
        "final_warning": "Consult a qualified lawyer for your situation.",
    }
    mock_litellm_acompletion(
        monkeypatch,
        [
            json.dumps(clarifier),
            json.dumps(rewriter),
            answer,
            json.dumps(validator),
        ],
    )


def test_graph_compiles() -> None:
    graph = build_agent_graph()
    assert graph is not None
    assert hasattr(graph, "ainvoke")


async def _setup_graph_test_data(
    db: AsyncSession,
    *,
    user_message: str,
) -> tuple[User, ChatSession, ChatRequest, ChatMessage]:
    user = User(email=f"graph-{uuid.uuid4()}@example.com", hashed_password="x", is_active=True)
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
        content=user_message,
    )
    db.add(user_msg)
    await db.commit()

    return user, session, chat_request, user_msg


@pytest.mark.asyncio
async def test_graph_clarifier_branch(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": True,
        "followup_questions": ["Are you under arrest?", "Do you have a written notice?"],
        "reason": "Need more facts",
    }
    mock_litellm_acompletion(monkeypatch, [json.dumps(clarifier)])

    user, session, chat_request, user_msg = await _setup_graph_test_data(
        db,
        user_message="Police stopped me",
    )

    runtime = GraphRuntime(
        db=db,
        settings=get_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[user_msg],
        user_msg=user_msg,
    )

    graph = build_agent_graph()
    final_state = await graph.ainvoke(
        {
            "user_message": "Police stopped me",
            "clarifier_round": 0,
            "force_answer": False,
            "total_tokens": 0,
            "max_validator_retries": get_settings().chat.max_validator_retries,
        },
        {"configurable": {"thread_id": str(chat_request.id), "runtime": runtime}},
    )

    assert final_state["needs_clarification"] is True
    assert len(final_state["followup_questions"]) == 2
    assert final_state.get("final_answer") is None


@pytest.mark.asyncio
async def test_graph_full_pipeline_mocked(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    _mock_full_pipeline_llm(monkeypatch)
    await _seed_corpus(db)

    user, session, chat_request, user_msg = await _setup_graph_test_data(
        db,
        user_message="What are my rights if police want me at the station?",
    )

    runtime = GraphRuntime(
        db=db,
        settings=get_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[user_msg],
        user_msg=user_msg,
    )

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        graph = build_agent_graph()
        final_state = await graph.ainvoke(
            {
                "user_message": user_msg.content,
                "clarifier_round": 0,
                "force_answer": False,
                "total_tokens": 0,
                "max_validator_retries": get_settings().chat.max_validator_retries,
            },
            {"configurable": {"thread_id": str(chat_request.id), "runtime": runtime}},
        )

    assert "Article 22" in final_state["final_answer"]
    assert final_state.get("needs_clarification") is not True


@pytest.mark.asyncio
async def test_graph_checkpoint_resume(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    _mock_full_pipeline_llm(monkeypatch)
    await _seed_corpus(db)

    user, session, chat_request, user_msg = await _setup_graph_test_data(
        db,
        user_message="What are my rights if police want me at the station?",
    )

    runtime = GraphRuntime(
        db=db,
        settings=get_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[user_msg],
        user_msg=user_msg,
    )

    thread_id = str(chat_request.id)
    initial_state: AgentGraphState = {
        "user_message": user_msg.content,
        "clarifier_round": 0,
        "force_answer": False,
        "total_tokens": 0,
        "max_validator_retries": get_settings().chat.max_validator_retries,
    }
    config = {"configurable": {"thread_id": thread_id, "runtime": runtime}}

    checkpointer = await get_checkpointer()
    graph = build_agent_graph(checkpointer=checkpointer)

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        paused_state = await graph.ainvoke(
            initial_state,
            config,
            interrupt_after=["query_rewriter"],
        )
        assert paused_state.get("search_queries")
        assert paused_state.get("final_answer") is None

        resumed_state = await graph.ainvoke(
            None,
            {"configurable": {"thread_id": thread_id, "runtime": runtime}},
        )

    assert "Article 22" in resumed_state["final_answer"]


@pytest.mark.asyncio
async def test_v01_fallback_when_flag_off(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DHARMIQ_AGENT_GRAPH_V2", raising=False)
    get_settings.cache_clear()
    mock_rerank(monkeypatch)

    _mock_full_pipeline_llm(monkeypatch)

    factory = get_session_factory()
    async with factory() as db:
        await _seed_corpus(db)

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        response = await client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "What are my rights if police want me at the station?",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ChatRequestStatus.COMPLETED.value
    assert "Article 22" in body["answer"]


@pytest.mark.asyncio
async def test_agent_graph_api_parity(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "true")
    get_settings.cache_clear()
    mock_rerank(monkeypatch)

    _mock_full_pipeline_llm(monkeypatch)

    factory = get_session_factory()
    async with factory() as db:
        await _seed_corpus(db)

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        response = await client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "What are my rights if police want me at the station?",
            },
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ChatRequestStatus.COMPLETED.value
    assert body["needs_clarification"] is False
    assert "Article 22" in body["answer"]
    assert len(body["citations"]) >= 1
    assert body["final_warning"] is not None
    assert any(message["role"] == MessageRole.USER.value for message in body["messages"])
    assert any(message["role"] == MessageRole.ASSISTANT.value for message in body["messages"])

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(ChatRequest))
        chat_requests = list(result.scalars().all())
        assert len(chat_requests) == 1
        assert chat_requests[0].total_tokens > 0


@pytest.mark.asyncio
async def test_langgraph_checkpoint_tables_exist() -> None:
    await get_checkpointer()
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'langgraph'
                """
            )
        )
        tables = {row[0] for row in result.fetchall()}

    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes"}.issubset(tables)


@pytest.mark.asyncio
async def test_agent_graph_clarifier_followups_api(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "true")
    get_settings.cache_clear()

    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": True,
        "followup_questions": ["Are you under arrest?", "Do you have a written notice?"],
        "reason": "Need more facts",
    }
    mock_litellm_acompletion(monkeypatch, [json.dumps(clarifier)])

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    response = await client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "Police stopped me"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["needs_clarification"] is True
    assert len(body["followup_questions"]) == 2
    assert body["answer"] is None
    assert any(message["role"] == MessageRole.CLARIFIER.value for message in body["messages"])

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(ChatRequest))
        chat_request = result.scalar_one()
        assert chat_request.clarifier_round == 1
