from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_sessions(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await client.post("/api/chat/sessions", json={"title": "Police rights"}, headers=auth_headers)
    assert create.status_code == 201
    session = create.json()
    assert session["title"] == "Police rights"
    assert "id" in session

    listing = await client.get("/api/chat/sessions", headers=auth_headers)
    assert listing.status_code == 200
    sessions = listing.json()
    assert any(item["id"] == session["id"] for item in sessions)


@pytest.mark.asyncio
async def test_append_and_list_messages(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    assert create.status_code == 201
    session_id = create.json()["id"]

    append = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"role": "user", "content": "What are my rights if police stop me?"},
        headers=auth_headers,
    )
    assert append.status_code == 201
    message = append.json()
    assert message["role"] == "user"
    assert message["content"].startswith("What are my rights")

    listing = await client.get(
        f"/api/chat/sessions/{session_id}/messages",
        headers=auth_headers,
    )
    assert listing.status_code == 200
    messages = listing.json()
    assert len(messages) == 1
    assert messages[0]["id"] == message["id"]


@pytest.mark.asyncio
async def test_auto_title_from_first_user_message(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"role": "user", "content": "Can my employer fire me without notice?"},
        headers=auth_headers,
    )

    session = await client.get(f"/api/chat/sessions/{session_id}", headers=auth_headers)
    assert session.status_code == 200
    assert session.json()["title"] == "Can my employer fire me without notice?"


@pytest.mark.asyncio
async def test_session_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    missing_id = uuid.uuid4()
    response = await client.get(f"/api/chat/sessions/{missing_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_other_user_cannot_access_session(
    client: AsyncClient,
    auth_headers: dict[str, str],
    unique_email: str,
) -> None:
    create = await client.post("/api/chat/sessions", json={"title": "Private"}, headers=auth_headers)
    session_id = create.json()["id"]

    other_email = f"other-{uuid.uuid4()}@example.com"
    password = "securepassword123"
    await client.post("/api/auth/register", json={"email": other_email, "password": password})
    other_login = await client.post(
        "/api/auth/jwt/login",
        data={"username": other_email, "password": password},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    response = await client.get(f"/api/chat/sessions/{session_id}", headers=other_headers)
    assert response.status_code == 404
