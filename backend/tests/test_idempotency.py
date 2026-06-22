from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from dharmiq.config.settings import get_settings
from dharmiq.db.models.chats import ChatRequest
from dharmiq.db.session import get_session_factory


@pytest.fixture(autouse=True)
def agent_graph_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "true")
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _clean_idempotency_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM idempotency_keys"))
        await db.execute(text("DELETE FROM chat_request_events"))
        await db.execute(text("DELETE FROM chat_requests"))
        await db.execute(text("DELETE FROM chat_messages"))
        await db.execute(text("DELETE FROM chat_sessions"))
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_idempotency_replay_same_key(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]
    idempotency_key = str(uuid.uuid4())
    headers = {**auth_headers, "Idempotency-Key": idempotency_key}
    body = {"content": "What are my rights if police arrest me?"}

    with patch("dharmiq.api.routes.chat.enqueue_agent_graph") as enqueue_mock:
        first = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json=body,
            headers=headers,
        )
        second = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json=body,
            headers=headers,
        )

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["chat_request_id"] == second.json()["chat_request_id"]
    assert first.json()["user_message_id"] == second.json()["user_message_id"]
    enqueue_mock.assert_called_once()

    factory = get_session_factory()
    async with factory() as db:
        result = await db.execute(select(ChatRequest))
        assert len(list(result.scalars().all())) == 1


@pytest.mark.asyncio
async def test_idempotency_conflict(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]
    idempotency_key = str(uuid.uuid4())
    headers = {**auth_headers, "Idempotency-Key": idempotency_key}

    with patch("dharmiq.api.routes.chat.enqueue_agent_graph"):
        first = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "What are my arrest rights?"},
            headers=headers,
        )
        second = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "What are my consumer rights?"},
            headers=headers,
        )

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["detail"] == "idempotency_key_conflict"
