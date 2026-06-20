from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from pgvector import Vector as PgVector
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.checkpoint import close_checkpointer, reset_checkpointer_cache
from dharmiq.agents.runner import run_agent_graph_for_request
from dharmiq.agents.streaming import ProgressEmitter, pubsub_channel, seq_key
from dharmiq.config.settings import get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.db.models.chats import (
    ChatRequest,
    ChatRequestEvent,
    ChatRequestStatus,
    ChatSession,
)
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.redis_client import close_redis, reset_redis_cache
from tests.litellm_helpers import mock_litellm_acompletion
from tests.vector_helpers import unit_vector


class _StaticEmbeddingBackend(EmbeddingBackend):
    @property
    def dimensions(self) -> int:
        return 384

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [unit_vector(0) for _ in texts]


@pytest.fixture(autouse=True)
async def _clean_stream_tables() -> None:
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


def _mock_full_pipeline_llm(monkeypatch: pytest.MonkeyPatch) -> None:
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


async def _seed_corpus(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id=f"chat-stream-{uuid.uuid4()}",
        title="Constitution of India (test)",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-chat-stream",
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


def _parse_sse_block(block: str) -> tuple[str | None, dict | None]:
    event_type = None
    data = None
    for line in block.strip().splitlines():
        if line.startswith("event: "):
            event_type = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data = json.loads(line.removeprefix("data: "))
    return event_type, data


async def _read_sse_events(client: AsyncClient, url: str, headers: dict[str, str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream("GET", url, headers=headers) as response:
        assert response.status_code == 200
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                part, buffer = buffer.split("\n\n", 1)
                if not part.strip():
                    continue
                event_type, data = _parse_sse_block(part)
                if event_type and data:
                    events.append((event_type, data))
    return events


async def _run_graph_inline(chat_request_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as db:
        with patch("dharmiq.llm.retrieval.get_embedding_backend", return_value=_StaticEmbeddingBackend()):
            await run_agent_graph_for_request(db, chat_request_id)


def _patch_inline_enqueue(monkeypatch: pytest.MonkeyPatch) -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = []

    def enqueue(chat_request_id: uuid.UUID) -> None:
        tasks.append(asyncio.create_task(_run_graph_inline(chat_request_id)))

    monkeypatch.setattr("dharmiq.api.routes.chat.enqueue_agent_graph", enqueue)
    return tasks


@pytest.mark.asyncio
async def test_post_message_returns_request_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_inline_enqueue(monkeypatch)

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    response = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "What is Article 22?"},
        headers=auth_headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["chat_request_id"]


@pytest.mark.asyncio
async def test_sse_receives_progress_events(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_full_pipeline_llm(monkeypatch)
    tasks = _patch_inline_enqueue(monkeypatch)

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
    req_id = post.json()["chat_request_id"]

    sse_task = asyncio.create_task(
        _read_sse_events(
            client,
            f"/api/chat/requests/{req_id}/stream",
            auth_headers,
        )
    )
    await asyncio.gather(*tasks)
    events = await sse_task

    progress_events = [data for event_type, data in events if event_type == "progress"]
    done_events = [data for event_type, data in events if event_type == "done"]
    assert len(progress_events) >= 2
    assert len(done_events) == 1
    assert done_events[0]["status"] == ChatRequestStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_events_persisted_in_db(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    req_id = uuid.UUID(post.json()["chat_request_id"])

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

    after_seq = 0
    sse_events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream?after_seq={after_seq}",
        auth_headers,
    )

    sse_seqs = sorted({data["seq"] for _, data in sse_events})
    db_seqs = [event.seq for event in db_events]
    assert sse_seqs == db_seqs


@pytest.mark.asyncio
async def test_seq_no_collision_under_parallel_emit() -> None:
    import redis.asyncio as aioredis

    chat_request_id = uuid.uuid4()
    settings = get_settings()
    redis_client = aioredis.from_url(
        settings.redis.url,
        decode_responses=True,
        single_connection_client=True,
    )

    async def incr_once() -> int:
        return int(await redis_client.incr(seq_key(chat_request_id)))

    try:
        seqs = await asyncio.gather(*[incr_once() for _ in range(20)])
        assert len(seqs) == len(set(seqs))
        assert sorted(seqs) == list(range(1, 21))
    finally:
        await redis_client.aclose()


async def _create_chat_request_row(db: AsyncSession) -> uuid.UUID:
    user = User(email=f"stream-{uuid.uuid4()}@example.com", hashed_password="x", is_active=True)
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
    await db.commit()
    return chat_request.id


@pytest.mark.asyncio
async def test_progress_emitter_publishes_to_redis(db: AsyncSession) -> None:
    import redis.asyncio as aioredis

    chat_request_id = await _create_chat_request_row(db)
    settings = get_settings()
    publish_client = aioredis.from_url(
        settings.redis.url,
        decode_responses=True,
        single_connection_client=True,
    )
    subscribe_client = aioredis.from_url(
        settings.redis.url,
        decode_responses=True,
        single_connection_client=True,
    )

    emitter = ProgressEmitter(db, chat_request_id, redis_client=publish_client)
    pubsub = subscribe_client.pubsub()
    await pubsub.subscribe(pubsub_channel(chat_request_id))

    listen_task = asyncio.create_task(_collect_one_pubsub_message(pubsub))
    await emitter.emit_step_start("retrieve")
    message = await asyncio.wait_for(listen_task, timeout=5.0)

    payload = json.loads(message["data"])
    assert payload["sse_event"] == "progress"
    assert payload["payload"]["step_id"] == "retrieve"
    await pubsub.unsubscribe(pubsub_channel(chat_request_id))
    await pubsub.aclose()
    await publish_client.aclose()
    await subscribe_client.aclose()


@pytest.mark.asyncio
async def test_reconnect_replays_then_dedupes(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    req_id = uuid.UUID(post.json()["chat_request_id"])

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

    assert len(db_events) >= 3
    after_seq = db_events[len(db_events) // 2].seq

    reconnect_events = await _read_sse_events(
        client,
        f"/api/chat/requests/{req_id}/stream?after_seq={after_seq}",
        auth_headers,
    )
    reconnect_seqs = [data["seq"] for _, data in reconnect_events]
    expected_seqs = [event.seq for event in db_events if event.seq > after_seq]

    assert reconnect_seqs == expected_seqs
    assert len(reconnect_seqs) == len(set(reconnect_seqs))


@pytest.mark.asyncio
async def test_failed_graph_emits_error_event(
    client: AsyncClient,
    auth_headers: dict[str, str],
    agent_graph_v2: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_litellm_acompletion(monkeypatch, [OpenRouterError("mock LLM failure")])
    tasks = _patch_inline_enqueue(monkeypatch)

    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]
    post = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"content": "What is Article 22?"},
        headers=auth_headers,
    )
    req_id = post.json()["chat_request_id"]

    sse_task = asyncio.create_task(
        _read_sse_events(client, f"/api/chat/requests/{req_id}/stream", auth_headers)
    )
    await asyncio.gather(*tasks)
    events = await sse_task

    error_events = [data for event_type, data in events if event_type == "error"]
    assert len(error_events) == 1
    assert error_events[0]["code"] == "LLM_ERROR"

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(ChatRequest).where(ChatRequest.id == uuid.UUID(req_id)))
        chat_request = result.scalar_one()
        assert chat_request.status == ChatRequestStatus.FAILED


async def _collect_one_pubsub_message(pubsub) -> dict:
    async for message in pubsub.listen():
        if message.get("type") == "message":
            return message
    raise RuntimeError("No pub/sub message received")
