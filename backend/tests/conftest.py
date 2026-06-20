from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import get_settings
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.llm.embeddings import reset_embedding_backend_cache
from dharmiq.llm.litellm_service import reset_litellm_service
from dharmiq.retrieval.reranker import reset_reranker_cache
from dharmiq.llm.openrouter_client import close_openrouter_client
from dharmiq.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_DB_BOOTSTRAPPED = False


def _ensure_test_database() -> None:
    global _TEST_DB_BOOTSTRAPPED
    if _TEST_DB_BOOTSTRAPPED:
        return

    password = os.environ.get("DHARMIQ_DATABASE_PASSWORD", "dharmiq")
    create_db = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "dharmiq",
            "-d",
            "postgres",
            "-tc",
            "SELECT 1 FROM pg_database WHERE datname = 'dharmiq_test'",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if create_db.returncode != 0:
        pytest.skip(
            "Postgres is unavailable; start it with `docker compose up -d postgres` "
            "before running tests."
        )
    if create_db.stdout.strip() != "1":
        created = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "dharmiq",
                "-d",
                "postgres",
                "-c",
                "CREATE DATABASE dharmiq_test OWNER dharmiq;",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            raise RuntimeError(f"Failed to create dharmiq_test database: {created.stderr}")

    migrated = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT / "backend",
        env={
            **os.environ,
            "DHARMIQ_ENV": "test",
            "DHARMIQ_DATABASE_PASSWORD": password,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if migrated.returncode != 0:
        raise RuntimeError(f"Failed to migrate dharmiq_test database: {migrated.stderr}")

    _TEST_DB_BOOTSTRAPPED = True


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    os.environ["DHARMIQ_ENV"] = "test"
    get_settings.cache_clear()
    _ensure_test_database()


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_ENV", "test")
    monkeypatch.setenv(
        "DHARMIQ_DATABASE_PASSWORD",
        os.environ.get("DHARMIQ_DATABASE_PASSWORD", "dharmiq"),
    )
    monkeypatch.setenv(
        "DHARMIQ_JWT_SECRET",
        os.environ.get("DHARMIQ_JWT_SECRET", "test-jwt-secret-with-32-byte-min"),
    )
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
async def _db_engine_lifecycle() -> None:
    await close_db()
    await close_openrouter_client()
    reset_litellm_service()
    reset_reranker_cache()
    reset_embedding_backend_cache()
    get_settings.cache_clear()
    await init_db()
    yield
    await close_db()
    await close_openrouter_client()
    reset_litellm_service()
    reset_reranker_cache()
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
