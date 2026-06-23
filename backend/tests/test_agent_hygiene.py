from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from pgvector import Vector as PgVector
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.checkpoint import close_checkpointer, reset_checkpointer_cache
from dharmiq.agents.graph import build_agent_graph
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.runner import (
    CLARIFIER_FAILURE_MESSAGE,
    run_agent_graph_for_request,
)
from dharmiq.agents.text_utils import normalize_for_comparison
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


def _clarifier_payload(*questions: str, **kwargs) -> dict:
    items = [
        {
            "question": question,
            "options": kwargs.get("options", []),
            "why": kwargs.get("why"),
        }
        for question in questions
    ]
    return {
        "topic": kwargs.get("topic", "police_arrest"),
        "needs_more_info": kwargs.get("needs_more_info", True),
        "followup_items": items,
        "reason": kwargs.get("reason", "Need more facts"),
    }


def _mock_full_pipeline_llm(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    clarifier = _clarifier_payload(needs_more_info=False)
    clarifier["needs_more_info"] = False
    clarifier["followup_items"] = []
    rewriter = {"queries": ["Article 22 arrest rights"]}
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


@pytest.fixture(autouse=True)
async def _clean_agent_hygiene_tables() -> None:
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


@pytest.fixture
def agent_graph_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "true")
    get_settings.cache_clear()


async def _seed_corpus(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id=f"agent-hygiene-{uuid.uuid4()}",
        title="Constitution of India (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-agent-hygiene",
        file_path="/tmp/constitution.pdf",
        indexed_at=datetime.now(UTC),
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
    await db.commit()


async def _setup_request(
    db: AsyncSession,
    *,
    user_message: str,
    history: list[ChatMessage] | None = None,
) -> tuple[User, ChatSession, ChatRequest, ChatMessage]:
    user = User(email=f"hygiene-{uuid.uuid4()}@example.com", hashed_password="x", is_active=True)
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
    await db.flush()
    user_msg = ChatMessage(
        session_id=session.id,
        user_id=user.id,
        role=MessageRole.USER,
        content=user_message,
        message_metadata={"chat_request_id": str(chat_request.id)},
    )
    db.add(user_msg)

    if history:
        for message in history:
            message.session_id = session.id
            message.user_id = user.id
            db.add(message)

    await db.commit()
    await db.refresh(chat_request)
    await db.refresh(user_msg)
    return user, session, chat_request, user_msg


def test_normalize_for_comparison() -> None:
    assert normalize_for_comparison("  Hello\tWorld  ") == "hello world"
    assert normalize_for_comparison("café") == normalize_for_comparison("café")


@pytest.mark.asyncio
async def test_clarifier_empty_followup_fails(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clarifier_bad = {
        "topic": "police_arrest",
        "needs_more_info": True,
        "reason": "Need more facts",
    }
    mock_litellm_acompletion(
        monkeypatch,
        [json.dumps(clarifier_bad), json.dumps(clarifier_bad)],
    )

    _, _, chat_request, _ = await _setup_request(db, user_message="Police stopped me")

    result = await run_agent_graph_for_request(db, chat_request.id)

    assert result.status == ChatRequestStatus.FAILED
    assert result.error_message == CLARIFIER_FAILURE_MESSAGE

    refreshed = await db.get(ChatRequest, chat_request.id)
    assert refreshed is not None
    assert refreshed.status == ChatRequestStatus.FAILED


@pytest.mark.asyncio
async def test_duplicate_clarifier_question_force_answer(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    answer = "You have protections under Article 22 [1].\n\nThis is not legal advice."
    clarifier = _clarifier_payload("Are you under arrest?")
    rewriter = {"queries": ["Article 22 arrest rights"]}
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
    await _seed_corpus(db)

    prior_clarifier = ChatMessage(
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        role=MessageRole.CLARIFIER,
        content="- Are you under arrest?",
        message_metadata={
            "followup_items": [
                {"question": "Are you under arrest?", "options": [], "why": None},
            ],
        },
    )
    user, session, chat_request, user_msg = await _setup_request(
        db,
        user_message="Police stopped me",
        history=[prior_clarifier],
    )

    runtime = GraphRuntime(
        db=db,
        settings=get_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[prior_clarifier, user_msg],
        user_msg=user_msg,
    )

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        graph = build_agent_graph()
        final_state = await graph.ainvoke(
            {
                "user_message": user_msg.content,
                "clarifier_round": 1,
                "force_answer": False,
                "total_tokens": 0,
                "max_validator_retries": get_settings().chat.max_validator_retries,
                "node_execution_count": 0,
            },
            {"configurable": {"thread_id": str(chat_request.id), "runtime": runtime}},
        )

    assert final_state.get("needs_clarification") is not True
    assert final_state.get("search_queries")


@pytest.mark.asyncio
async def test_retry_duplicate_answer_409(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_rerank(monkeypatch)
    answer = "You have protections under Article 22 [1].\n\nThis is not legal advice."
    _mock_full_pipeline_llm(monkeypatch, answer)

    factory = get_session_factory()
    async with factory() as db:
        await _seed_corpus(db)

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        first = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "What are my rights if police want me at the station?"},
            headers=auth_headers,
        )
    assert first.status_code == 202
    req_id = uuid.UUID(first.json()["chat_request_id"])

    async with factory() as db:
        await run_agent_graph_for_request(db, req_id)

    async with factory() as db:
        user_result = await db.execute(
            select(ChatMessage).where(
                ChatMessage.message_metadata["chat_request_id"].astext == str(req_id),
                ChatMessage.role == MessageRole.USER,
            )
        )
        user_message = user_result.scalar_one()

    _mock_full_pipeline_llm(monkeypatch, answer)
    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        retry = await client.post(
            f"/api/chat/sessions/{session_id}/messages/{user_message.id}/retry",
            headers=auth_headers,
        )

    assert retry.status_code == 409
    assert retry.json()["detail"] == "duplicate_answer"


@pytest.mark.asyncio
async def test_step_limit_fails_request(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clarifier = _clarifier_payload(needs_more_info=False)
    clarifier["needs_more_info"] = False
    clarifier["followup_items"] = []
    mock_litellm_acompletion(monkeypatch, [json.dumps(clarifier)])

    _, _, chat_request, _ = await _setup_request(db, user_message="Police stopped me")

    with patch("dharmiq.agents.graph.MAX_NODE_EXECUTIONS", 1):
        result = await run_agent_graph_for_request(db, chat_request.id)

    assert result.status == ChatRequestStatus.FAILED
    assert result.error_message is not None
    assert "too many steps" in result.error_message.lower()

    refreshed = await db.get(ChatRequest, chat_request.id)
    assert refreshed is not None
    assert refreshed.status == ChatRequestStatus.FAILED
