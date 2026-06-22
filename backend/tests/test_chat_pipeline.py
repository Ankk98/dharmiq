from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from pgvector import Vector as PgVector
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import ChatRequest, ChatRequestStatus, MessageRole
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from tests.litellm_helpers import mock_litellm_acompletion
from tests.vector_helpers import unit_vector


class _StaticEmbeddingBackend(EmbeddingBackend):
    @property
    def dimensions(self) -> int:
        return 384

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [unit_vector(0) for _ in texts]


@pytest.fixture(autouse=True)
async def _clean_pipeline_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM chat_requests"))
        await db.execute(text("DELETE FROM chat_messages"))
        await db.execute(text("DELETE FROM chat_sessions"))
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


async def _seed_corpus(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id=f"pipeline-test-{uuid.uuid4()}",
        title="Constitution of India (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-pipeline",
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
    await db.commit()


def _mock_llm_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": False,
        "followup_questions": [],
        "reason": "Enough detail",
    }
    rewriter = {"queries": ["Article 22 arrest rights", "police station questioning rights"]}
    answer = "You have protections under Article 22 [doc:abc|chunk:def]. This is not legal advice."
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


@pytest.mark.asyncio
async def test_chat_pipeline_returns_answer(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_llm_responses(monkeypatch)

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
        assert chat_requests[0].status == ChatRequestStatus.COMPLETED
        assert chat_requests[0].total_tokens > 0


@pytest.mark.asyncio
async def test_chat_pipeline_returns_clarifier_followups(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clarifier = {
        "topic": "police_arrest",
        "needs_more_info": True,
        "followup_items": [
            {"question": "Are you under arrest?", "options": [], "why": None},
            {"question": "Do you have a written notice?", "options": [], "why": None},
        ],
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
