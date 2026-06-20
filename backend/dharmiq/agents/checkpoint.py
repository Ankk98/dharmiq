from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from sqlalchemy import text

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.logging import get_logger
from dharmiq.db.session import get_session_factory

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = get_logger(__name__)

LANGGRAPH_SCHEMA = "langgraph"
_checkpointer: AsyncPostgresSaver | None = None
_connection: AsyncConnection | None = None
_checkpointer_setup_done = False


def postgres_conn_string(settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    db = cfg.database
    password = db.password.get_secret_value()
    search_path_option = quote(f"-c search_path={LANGGRAPH_SCHEMA}", safe="")
    return (
        f"postgresql://{db.user}:{password}@{db.host}:{db.port}/{db.name}"
        f"?options={search_path_option}"
    )


async def ensure_langgraph_schema(settings: Settings | None = None) -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text(f"CREATE SCHEMA IF NOT EXISTS {LANGGRAPH_SCHEMA}"))
        await session.commit()


async def get_checkpointer(settings: Settings | None = None) -> AsyncPostgresSaver:
    global _checkpointer, _connection, _checkpointer_setup_done

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    if _checkpointer is None:
        await ensure_langgraph_schema(settings)
        _connection = await AsyncConnection.connect(
            postgres_conn_string(settings),
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        _checkpointer = AsyncPostgresSaver(conn=_connection)

    if not _checkpointer_setup_done:
        await _checkpointer.setup()
        _checkpointer_setup_done = True
        logger.info("langgraph_checkpoint_setup_complete", schema=LANGGRAPH_SCHEMA)

    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _connection, _checkpointer_setup_done
    if _connection is not None:
        await _connection.close()
    _checkpointer = None
    _connection = None
    _checkpointer_setup_done = False


def reset_checkpointer_cache() -> None:
    global _checkpointer, _connection, _checkpointer_setup_done
    _checkpointer = None
    _connection = None
    _checkpointer_setup_done = False
