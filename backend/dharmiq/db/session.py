from __future__ import annotations

from collections.abc import AsyncGenerator

from pgvector.asyncpg import register_vector
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dharmiq.config.settings import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _register_pgvector(dbapi_connection, _connection_record) -> None:
    dbapi_connection.run_async(register_vector)


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _session_factory
    cfg = settings or get_settings()
    _engine = create_async_engine(
        cfg.database.async_url,
        echo=cfg.server.debug,
        pool_pre_ping=True,
    )
    event.listen(_engine.sync_engine, "connect", _register_pgvector)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        create_engine()
    assert _session_factory is not None
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db(settings: Settings | None = None) -> None:
    """Create engine; tables are managed via Alembic migrations."""
    from pgvector.asyncpg import register_vector

    engine = create_engine(settings)
    async with engine.connect() as conn:
        raw = await conn.get_raw_connection()
        await register_vector(raw.driver_connection)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        event.remove(_engine.sync_engine, "connect", _register_pgvector)
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def check_db_connection() -> bool:
    """Return True if the database is reachable."""
    from sqlalchemy import text

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
