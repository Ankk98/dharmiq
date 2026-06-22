from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from dharmiq.db.models.chats import ChatRequest, ChatRequestStatus, ChatSession
from dharmiq.db.models.uploads import ProcessingStage, UserUpload
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.tasks import chat_tasks, ingestion_tasks


@pytest.fixture(autouse=True)
async def _clean_recovery_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM chat_request_events"))
        await db.execute(text("DELETE FROM chat_requests"))
        await db.execute(text("DELETE FROM chat_messages"))
        await db.execute(text("DELETE FROM chat_sessions"))
        await db.execute(text("DELETE FROM user_upload_chunks"))
        await db.execute(text("DELETE FROM user_uploads"))
        await db.commit()
    yield


@pytest.fixture
def run_async_in_thread() -> None:
    def _run_async(coro):
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    with (
        patch.object(chat_tasks, "_run_async", _run_async),
        patch.object(ingestion_tasks, "_run_async", _run_async),
    ):
        yield


async def _create_user(db) -> User:
    user = User(
        email=f"recovery-{uuid.uuid4()}@example.com",
        hashed_password="test",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_celery_duplicate_task_id(db, run_async_in_thread) -> None:
    user = await _create_user(db)
    session = ChatSession(user_id=user.id, title="Recovery test")
    db.add(session)
    await db.flush()

    chat_request = ChatRequest(
        session_id=session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
    )
    db.add(chat_request)
    await db.commit()
    await db.refresh(chat_request)

    apply_async = MagicMock(side_effect=[None, Exception("duplicate task id")])
    with patch("dharmiq.tasks.chat_tasks.run_agent_graph_task") as task_mock:
        task_mock.apply_async = apply_async
        assert chat_tasks.enqueue_agent_graph(chat_request.id) is True
        assert chat_tasks.enqueue_agent_graph(chat_request.id) is False

    assert apply_async.call_count == 2
    task_mock.apply_async.assert_called_with(
        args=[str(chat_request.id)],
        task_id=str(chat_request.id),
    )


@pytest.mark.asyncio
async def test_enqueue_skips_completed_request(db, run_async_in_thread) -> None:
    user = await _create_user(db)
    session = ChatSession(user_id=user.id, title="Completed")
    db.add(session)
    await db.flush()

    chat_request = ChatRequest(
        session_id=session.id,
        user_id=user.id,
        status=ChatRequestStatus.COMPLETED,
    )
    db.add(chat_request)
    await db.commit()
    await db.refresh(chat_request)

    with patch("dharmiq.tasks.chat_tasks.run_agent_graph_task") as task_mock:
        assert chat_tasks.enqueue_agent_graph(chat_request.id) is False
        task_mock.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_upload_recovery_reenqueue(db, run_async_in_thread) -> None:
    user = await _create_user(db)
    upload = UserUpload(
        user_id=user.id,
        original_filename="lease.pdf",
        file_path=f"/tmp/{uuid.uuid4()}.pdf",
        mime_type="application/pdf",
        size_bytes=128,
        content_hash="hash-" + uuid.uuid4().hex,
        processing_stage=ProcessingStage.CHUNKING.value,
    )
    db.add(upload)
    await db.commit()
    await db.refresh(upload)

    apply_async = MagicMock()
    with patch("dharmiq.tasks.ingestion_tasks.process_user_upload") as task_mock:
        task_mock.apply_async = apply_async
        recovered = ingestion_tasks.recover_stale_uploads()

    assert recovered == 1
    apply_async.assert_called_once_with(
        args=[str(upload.id)],
        task_id=str(upload.id),
    )
