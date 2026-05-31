from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.db.session import get_db_session


async def get_settings_dep() -> Settings:
    return get_settings()


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session
