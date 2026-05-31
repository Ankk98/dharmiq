"""Tests for milestone 1 infrastructure."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from dharmiq.config.settings import REPO_ROOT, load_settings
from dharmiq.main import create_app


def test_repo_root_exists() -> None:
    assert (REPO_ROOT / "config" / "config.dev.yaml").exists()


def test_load_dev_settings() -> None:
    settings = load_settings("dev")
    assert settings.env == "dev"
    assert settings.server.port == 8000
    assert "postgresql+asyncpg://" in settings.database.async_url


def test_load_beta_settings() -> None:
    settings = load_settings("beta")
    assert settings.env == "beta"
    assert settings.server.debug is False


@pytest.mark.asyncio
async def test_liveness_endpoint() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
