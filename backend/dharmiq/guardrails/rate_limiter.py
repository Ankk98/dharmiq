from __future__ import annotations

from typing import Literal

import redis.asyncio as aioredis
from pydantic import BaseModel

from dharmiq.config.settings import GuardrailsSettings
from dharmiq.core.logging import get_logger

logger = get_logger(__name__)

_MINUTE_WINDOW_SECONDS = 60
_DAY_WINDOW_SECONDS = 86_400


class RateLimitResult(BaseModel):
    allowed: bool
    reason: str | None = None
    code: str = "RATE_LIMIT_EXCEEDED"
    retry_after_seconds: int | None = None
    window: Literal["minute", "day"] | None = None


def _minute_key(user_id: str) -> str:
    return f"guard:rate:{user_id}:minute"


def _day_key(user_id: str) -> str:
    return f"guard:rate:{user_id}:day"


async def _increment_window(
    redis_client: aioredis.Redis,
    key: str,
    *,
    ttl_seconds: int,
) -> int:
    count = int(await redis_client.incr(key))
    if count == 1:
        await redis_client.expire(key, ttl_seconds)
    return count


async def check_rate_limit(
    redis_client: aioredis.Redis | None,
    *,
    user_id: str,
    settings: GuardrailsSettings,
) -> RateLimitResult:
    """Return whether the user is within per-minute and per-day chat limits."""
    if redis_client is None:
        return RateLimitResult(allowed=True)

    try:
        minute_count = await _increment_window(
            redis_client,
            _minute_key(user_id),
            ttl_seconds=_MINUTE_WINDOW_SECONDS,
        )
        if minute_count > settings.requests_per_minute:
            ttl = await redis_client.ttl(_minute_key(user_id))
            retry_after = max(int(ttl), 1) if ttl and ttl > 0 else _MINUTE_WINDOW_SECONDS
            return RateLimitResult(
                allowed=False,
                reason="Too many requests. Please wait before sending another message.",
                retry_after_seconds=retry_after,
                window="minute",
            )

        day_count = await _increment_window(
            redis_client,
            _day_key(user_id),
            ttl_seconds=_DAY_WINDOW_SECONDS,
        )
        if day_count > settings.requests_per_day:
            ttl = await redis_client.ttl(_day_key(user_id))
            retry_after = max(int(ttl), 1) if ttl and ttl > 0 else _DAY_WINDOW_SECONDS
            return RateLimitResult(
                allowed=False,
                reason="Daily request limit reached. Please try again tomorrow.",
                retry_after_seconds=retry_after,
                window="day",
            )
    except Exception:
        logger.warning("rate_limit_redis_unavailable", user_id=user_id, exc_info=True)
        return RateLimitResult(allowed=True)

    return RateLimitResult(allowed=True)
