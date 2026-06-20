from __future__ import annotations

import redis.asyncio as aioredis

from dharmiq.config.settings import Settings, get_settings

_redis_client: aioredis.Redis | None = None


async def get_redis(settings: Settings | None = None) -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        cfg = settings or get_settings()
        _redis_client = aioredis.from_url(cfg.redis.url, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


def reset_redis_cache() -> None:
    global _redis_client
    _redis_client = None
