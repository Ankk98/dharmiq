from __future__ import annotations

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import get_settings
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.llm.embeddings import reset_embedding_backend_cache
from dharmiq.llm.litellm_service import reset_litellm_service
from dharmiq.llm.openrouter_client import close_openrouter_client
from dharmiq.main import create_app


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DHARMIQ_DATABASE_PASSWORD",
        os.environ.get("DHARMIQ_DATABASE_PASSWORD", "dharmiq"),
    )
    monkeypatch.setenv(
        "DHARMIQ_JWT_SECRET",
        os.environ.get("DHARMIQ_JWT_SECRET", "test-jwt-secret-with-32-byte-min"),
    )


@pytest.fixture(autouse=True)
async def _db_engine_lifecycle() -> None:
    await close_db()
    await close_openrouter_client()
    reset_litellm_service()
    reset_embedding_backend_cache()
    get_settings.cache_clear()
    await init_db()
    yield
    await close_db()
    await close_openrouter_client()
    reset_litellm_service()
    reset_embedding_backend_cache()
    get_settings.cache_clear()


@pytest.fixture
async def db() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4()}@example.com"


@pytest.fixture
async def auth_headers(client: AsyncClient, unique_email: str) -> dict[str, str]:
    password = "securepassword123"
    register_response = await client.post(
        "/api/auth/register",
        json={"email": unique_email, "password": password},
    )
    assert register_response.status_code == 201, register_response.text

    login_response = await client.post(
        "/api/auth/jwt/login",
        data={"username": unique_email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
