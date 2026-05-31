from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dharmiq.config.settings import Settings, get_settings
from dharmiq.db.session import check_db_connection

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    env: str
    checks: dict[str, str]


async def _check_redis(settings: Settings) -> bool:
    try:
        client = aioredis.from_url(settings.redis.url, socket_connect_timeout=2)
        try:
            return await client.ping()
        finally:
            await client.aclose()
    except Exception:
        return False


@router.get("/health", response_model=HealthStatus)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthStatus:
    db_ok = await check_db_connection()
    redis_ok = await _check_redis(settings)

    checks = {
        "database": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
    all_ok = all(v == "ok" for v in checks.values())

    return HealthStatus(
        status="ok" if all_ok else "degraded",
        env=settings.env,
        checks=checks,
    )


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Kubernetes-style liveness probe – process is running."""
    return {"status": "ok"}
