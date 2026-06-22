from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


async def _create_message(
    client: AsyncClient,
    auth_headers: dict[str, str],
    role: str,
    content: str,
) -> str:
    create_session = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    assert create_session.status_code == 201
    session_id = create_session.json()["id"]

    create_message = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"role": role, "content": content},
        headers=auth_headers,
    )
    assert create_message.status_code == 201
    return create_message.json()["id"]


@pytest.mark.asyncio
async def test_feedback_upsert(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    message_id = await _create_message(client, auth_headers, "assistant", "Initial answer")

    first = await client.post(
        f"/api/chat/messages/{message_id}/feedback",
        json={"rating": "down", "reason": "Too generic"},
        headers=auth_headers,
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["rating"] == "down"
    assert first_payload["reason"] == "Too generic"

    second = await client.post(
        f"/api/chat/messages/{message_id}/feedback",
        json={"rating": "up", "reason": "Clear and precise"},
        headers=auth_headers,
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["rating"] == "up"
    assert second_payload["reason"] == "Clear and precise"


@pytest.mark.asyncio
async def test_feedback_assistant_only(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    user_message_id = await _create_message(client, auth_headers, "user", "My message")
    response = await client.post(
        f"/api/chat/messages/{user_message_id}/feedback",
        json={"rating": "up"},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_feedback_other_user_404(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    message_id = await _create_message(client, auth_headers, "assistant", "Owner answer")

    other_email = f"other-{uuid.uuid4()}@example.com"
    password = "securepassword123"
    await client.post("/api/auth/register", json={"email": other_email, "password": password})
    other_login = await client.post(
        "/api/auth/jwt/login",
        data={"username": other_email, "password": password},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.post(
        f"/api/chat/messages/{message_id}/feedback",
        json={"rating": "down", "reason": "Should not be allowed"},
        headers=other_headers,
    )
    assert response.status_code == 404
