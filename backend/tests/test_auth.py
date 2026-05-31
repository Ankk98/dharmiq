from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient) -> None:
    email = f"auth-{uuid.uuid4()}@example.com"
    password = "securepassword123"

    register = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201
    body = register.json()
    assert body["email"] == email
    assert "id" in body

    login = await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    assert "access_token" in login.json()


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    email = f"dup-{uuid.uuid4()}@example.com"
    password = "securepassword123"
    payload = {"email": email, "password": password}

    first = await client.post("/api/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/auth/register", json=payload)
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_protected_route_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/chat/sessions")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_users_me(client: AsyncClient, auth_headers: dict[str, str], unique_email: str) -> None:
    response = await client.get("/api/users/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == unique_email
