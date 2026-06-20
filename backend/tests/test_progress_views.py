from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from dharmiq.agents.checkpoint import close_checkpointer, reset_checkpointer_cache
from dharmiq.agents.streaming import event_to_stream, filter_event_for_user
from dharmiq.config.settings import get_settings
from dharmiq.db.models.chats import ChatRequestEvent, EventVisibility
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.redis_client import close_redis, reset_redis_cache
from tests.test_chat_stream import (
    _mock_full_pipeline_llm,
    _read_sse_events,
    _run_graph_inline,
    _seed_corpus,
)
from tests.vector_helpers import unit_vector


class _StaticEmbeddingBackend(EmbeddingBackend):
    @property
    def dimensions(self) -> int:
        return 384

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [unit_vector(0) for _ in texts]


@pytest.fixture(autouse=True)
async def _clean_progress_tables() -> None:
    await close_checkpointer()
    reset_checkpointer_cache()
    await close_redis()
    reset_redis_cache()
    factory = get_session_factory()
    async with factory() as db:
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
    await close_redis()
    reset_redis_cache()


@pytest.fixture
def agent_graph_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "true")
    get_settings.cache_clear()


@pytest.fixture
def debug_progress_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_DEBUG_PROGRESS", "true")
    get_settings.cache_clear()


async def _promote_user_to_superuser(email: str) -> None:
    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.is_superuser = True
        await db.commit()


async def _run_pipeline_and_get_request_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> uuid.UUID:
    _mock_full_pipeline_llm(monkeypatch)

    factory = get_session_factory()
    async with factory() as db:
        await _seed_corpus(db)

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]
    post = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "What are my rights if police want me at the station?"},
        headers=auth_headers,
    )
    return uuid.UUID(post.json()["chat_request_id"])


def _visible_db_seqs(
    db_events: list[ChatRequestEvent],
    user: User,
    *,
    view: str = "concise",
) -> list[int]:
    settings = get_settings()
    visible: list[int] = []
    for event in db_events:
        filtered = filter_event_for_user(event_to_stream(event), user, settings, view=view)  # type: ignore[arg-type]
        if filtered is not None:
            visible.append(event.seq)
    return visible


@pytest.mark.asyncio
async def test_concise_hides_rerank_scores(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
    debug_progress_enabled: None,
) -> None:
    req_id = await _run_pipeline_and_get_request_id(client, auth_headers, monkeypatch)

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        await _run_graph_inline(req_id)

    events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream",
        auth_headers,
    )
    progress_payloads = [data for event_type, data in events if event_type == "progress"]

    assert progress_payloads
    for payload in progress_payloads:
        assert "rerank_scores" not in payload
        assert "queries" not in payload


@pytest.mark.asyncio
async def test_detailed_includes_chunk_previews(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    req_id = await _run_pipeline_and_get_request_id(client, auth_headers, monkeypatch)

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        await _run_graph_inline(req_id)

    events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream?view=detailed",
        auth_headers,
    )
    progress_payloads = [data for event_type, data in events if event_type == "progress"]

    retrieve_events = [
        payload
        for payload in progress_payloads
        if payload.get("step_id") == "retrieve"
        and payload.get("status") == "completed"
        and payload.get("visibility") == EventVisibility.DETAILED.value
    ]
    assert retrieve_events
    assert isinstance(retrieve_events[0].get("preview"), list)
    assert retrieve_events[0]["preview"]


@pytest.mark.asyncio
async def test_debug_requires_admin(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
    debug_progress_enabled: None,
) -> None:
    req_id = await _run_pipeline_and_get_request_id(client, auth_headers, monkeypatch)

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        await _run_graph_inline(req_id)

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(ChatRequestEvent)
            .where(ChatRequestEvent.chat_request_id == req_id)
            .order_by(ChatRequestEvent.seq.asc())
        )
        db_events = list(result.scalars().all())

    assert any(event.visibility == EventVisibility.DEBUG.value for event in db_events)

    events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream?view=detailed",
        auth_headers,
    )
    all_payloads = [data for _, data in events]

    for payload in all_payloads:
        assert payload.get("visibility") != EventVisibility.DEBUG.value
        assert "rerank_scores" not in payload
        assert "queries" not in payload


@pytest.mark.asyncio
async def test_admin_sees_debug_events(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
    debug_progress_enabled: None,
) -> None:
    me = await client.get("/api/users/me", headers=auth_headers)
    await _promote_user_to_superuser(me.json()["email"])

    req_id = await _run_pipeline_and_get_request_id(client, auth_headers, monkeypatch)

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        await _run_graph_inline(req_id)

    events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream?view=detailed",
        auth_headers,
    )
    progress_payloads = [data for event_type, data in events if event_type == "progress"]

    debug_events = [
        payload for payload in progress_payloads if payload.get("visibility") == EventVisibility.DEBUG.value
    ]
    assert debug_events

    retrieve_debug = next(
        payload
        for payload in debug_events
        if payload.get("step_id") == "retrieve" and payload.get("status") == "completed"
    )
    assert isinstance(retrieve_debug.get("rerank_scores"), list)
    assert isinstance(retrieve_debug.get("queries"), list)
    assert retrieve_debug["queries"]


@pytest.mark.asyncio
async def test_replay_applies_same_visibility_filter(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
    debug_progress_enabled: None,
) -> None:
    req_id = await _run_pipeline_and_get_request_id(client, auth_headers, monkeypatch)

    with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
        await _run_graph_inline(req_id)

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(
            select(ChatRequestEvent)
            .where(ChatRequestEvent.chat_request_id == req_id)
            .order_by(ChatRequestEvent.seq.asc())
        )
        db_events = list(result.scalars().all())

    midpoint = db_events[len(db_events) // 2].seq
    replay_events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream?after_seq={midpoint}&view=detailed",
        auth_headers,
    )
    replay_payloads = [data for _, data in replay_events]

    for payload in replay_payloads:
        assert payload.get("visibility") != EventVisibility.DEBUG.value
        assert "rerank_scores" not in payload
