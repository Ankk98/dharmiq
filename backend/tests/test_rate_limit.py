from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from dharmiq.config.settings import get_settings
from dharmiq.guardrails.rate_limiter import _day_key, _minute_key, check_rate_limit
from dharmiq.redis_client import close_redis, get_redis, reset_redis_cache


@pytest.fixture(autouse=True)
async def _clean_rate_limit_keys() -> None:
    await close_redis()
    reset_redis_cache()
    yield
    await close_redis()
    reset_redis_cache()


@pytest.fixture
def low_rate_limit_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "false")
    get_settings.cache_clear()
    settings = get_settings()
    settings.guardrails.requests_per_minute = 10
    settings.guardrails.requests_per_day = 200
    return settings


async def _clear_user_rate_keys(user_id: str) -> None:
    redis_client = await get_redis()
    await redis_client.delete(_minute_key(user_id), _day_key(user_id))


@pytest.mark.asyncio
async def test_rate_limit_429(
    client: AsyncClient,
    auth_headers: dict[str, str],
    low_rate_limit_settings,
) -> None:
    create = await client.post("/api/chat/sessions", json={}, headers=auth_headers)
    session_id = create.json()["id"]

    for _ in range(11):
        response = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "What are my rights under Article 22?"},
            headers=auth_headers,
        )
        if response.status_code == 429:
            body = response.json()
            assert body["code"] == "RATE_LIMIT_EXCEEDED"
            assert "Retry-After" in response.headers
            assert response.headers["Retry-After"].isdigit()
            return
    pytest.fail("Expected 11th request to return 429")


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limits(low_rate_limit_settings) -> None:
    user_id = str(uuid.uuid4())
    await _clear_user_rate_keys(user_id)
    redis_client = await get_redis()

    for _ in range(10):
        result = await check_rate_limit(
            redis_client,
            user_id=user_id,
            settings=low_rate_limit_settings.guardrails,
        )
        assert result.allowed is True

    blocked = await check_rate_limit(
        redis_client,
        user_id=user_id,
        settings=low_rate_limit_settings.guardrails,
    )
    assert blocked.allowed is False
    assert blocked.window == "minute"


@pytest.mark.asyncio
async def test_rate_limiter_skips_when_redis_unavailable(low_rate_limit_settings) -> None:
    result = await check_rate_limit(
        None,
        user_id=str(uuid.uuid4()),
        settings=low_rate_limit_settings.guardrails,
    )
    assert result.allowed is True
