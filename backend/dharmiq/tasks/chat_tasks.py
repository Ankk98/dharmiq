from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.runner import run_agent_graph_for_request
from dharmiq.config.settings import get_settings
from dharmiq.core.logging import get_logger, setup_logging
from dharmiq.agents.checkpoint import close_checkpointer
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.tasks.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


async def _with_db_session(coro_factory):
    await init_db()
    factory = get_session_factory()
    try:
        async with factory() as db:
            return await coro_factory(db)
    finally:
        await close_checkpointer()
        await close_db()


async def execute_agent_graph(chat_request_id: uuid.UUID) -> None:
    async def _run(db: AsyncSession) -> None:
        try:
            await run_agent_graph_for_request(
                db,
                chat_request_id,
                settings=get_settings(),
            )
        except Exception:
            from sqlalchemy import select

            from dharmiq.db.models.chats import ChatRequest, ChatRequestStatus
            from dharmiq.llm.pipeline import _mark_request_failed

            result = await db.execute(
                select(ChatRequest).where(ChatRequest.id == chat_request_id)
            )
            chat_request = result.scalar_one_or_none()
            if chat_request is not None and chat_request.status in {
                ChatRequestStatus.PENDING,
                ChatRequestStatus.RUNNING,
            }:
                await _mark_request_failed(
                    db,
                    chat_request,
                    error_message="Internal error",
                )
            raise

    await _with_db_session(_run)


def recover_pending_agent_graph_requests() -> int:
    """Re-enqueue chat requests left pending after Redis/worker restarts."""

    async def _recover(db: AsyncSession) -> int:
        from sqlalchemy import select

        from dharmiq.db.models.chats import ChatRequest, ChatRequestStatus

        result = await db.execute(
            select(ChatRequest.id).where(
                ChatRequest.status.in_(
                    [ChatRequestStatus.PENDING, ChatRequestStatus.RUNNING]
                )
            )
        )
        request_ids = list(result.scalars().all())
        for request_id in request_ids:
            enqueue_agent_graph(request_id)
        return len(request_ids)

    return _run_async(_with_db_session(_recover))


def enqueue_agent_graph(chat_request_id: uuid.UUID) -> None:
    run_agent_graph_task.delay(str(chat_request_id))


@celery_app.task(name="dharmiq.chat.run_agent_graph", bind=True, max_retries=0)
def run_agent_graph_task(self, chat_request_id: str) -> dict[str, str]:
    settings = get_settings()
    setup_logging(settings)
    request_id = uuid.UUID(chat_request_id)
    logger.info("run_agent_graph_started", chat_request_id=chat_request_id)

    try:
        _run_async(execute_agent_graph(request_id))
    except Exception as exc:
        logger.exception("run_agent_graph_failed", chat_request_id=chat_request_id, error=str(exc))
        raise

    logger.info("run_agent_graph_completed", chat_request_id=chat_request_id)
    return {"chat_request_id": chat_request_id, "status": "completed"}
