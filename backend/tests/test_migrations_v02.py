from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import (
    ChatRequest,
    ChatRequestEvent,
    ChatRequestEventType,
    ChatRequestStatus,
    ChatSession,
    ChatSessionUpload,
)
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.models.uploads import UserUpload
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory


async def _table_columns(db: AsyncSession, table: str) -> set[str]:
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :table",
        ),
        {"table": table},
    )
    return {row[0] for row in result.all()}


async def _table_exists(db: AsyncSession, table: str) -> bool:
    result = await db.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables "
            "  WHERE table_schema = 'public' AND table_name = :table"
            ")",
        ),
        {"table": table},
    )
    return bool(result.scalar_one())


async def _create_user(db: AsyncSession) -> User:
    helper = PasswordHelper()
    hashed = helper.hash("securepassword123")
    user = User(
        id=uuid.uuid4(),
        email=f"migration-test-{uuid.uuid4()}@example.com",
        hashed_password=hashed,
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_session(db: AsyncSession, user: User) -> ChatSession:
    session = ChatSession(id=uuid.uuid4(), user_id=user.id, title="migration test")
    db.add(session)
    await db.flush()
    return session


async def _create_upload(db: AsyncSession, user: User) -> UserUpload:
    upload = UserUpload(
        id=uuid.uuid4(),
        user_id=user.id,
        original_filename="contract.pdf",
        file_path="/tmp/contract.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        content_hash="abc123",
    )
    db.add(upload)
    await db.flush()
    return upload


async def test_v02_columns_exist(db: AsyncSession) -> None:
    chat_message_cols = await _table_columns(db, "chat_messages")
    assert {"content_compressed", "compression_version"}.issubset(chat_message_cols)

    chat_request_cols = await _table_columns(db, "chat_requests")
    assert {
        "clarifier_round",
        "force_answer",
        "stated_assumptions",
        "progress_view",
    }.issubset(chat_request_cols)

    assert await _table_exists(db, "chat_session_uploads")
    assert await _table_exists(db, "chat_request_events")
    assert await _table_exists(db, "context_summaries")

    document_chunk_cols = await _table_columns(db, "document_chunks")
    assert {
        "context_text",
        "parent_chunk_id",
        "metadata",
        "search_vector",
    }.issubset(document_chunk_cols)

    upload_chunk_cols = await _table_columns(db, "user_upload_chunks")
    assert {
        "context_text",
        "parent_chunk_id",
        "metadata",
        "search_vector",
    }.issubset(upload_chunk_cols)

    gin_result = await db.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'document_chunks' AND indexdef LIKE '%gin%'",
        ),
    )
    gin_indexes = {row[0] for row in gin_result.all()}
    assert any("search_vector" in name for name in gin_indexes)


async def test_chunk_metadata_attr_maps_to_metadata_col(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id=f"meta-test-{uuid.uuid4()}",
        title="Test Act",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-meta",
        file_path="/tmp/test.pdf",
    )
    db.add(document)
    await db.flush()

    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="Section 41 permits arrest without warrant in certain cases.",
        chunk_metadata={"act_short_name": "CrPC", "section_number": "41"},
    )
    db.add(chunk)
    await db.commit()

    row = await db.execute(
        text("SELECT metadata FROM document_chunks WHERE id = :id"),
        {"id": chunk.id},
    )
    metadata = row.scalar_one()
    assert metadata["act_short_name"] == "CrPC"
    assert metadata["section_number"] == "41"

    await db.refresh(chunk)
    assert chunk.chunk_metadata["act_short_name"] == "CrPC"


async def test_search_vector_is_generated(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id=f"tsv-test-{uuid.uuid4()}",
        title="Test Act",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-tsv",
        file_path="/tmp/test.pdf",
    )
    db.add(document)
    await db.flush()

    chunk = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="Article 22 protects against arbitrary detention.",
    )
    db.add(chunk)
    await db.commit()

    row = await db.execute(
        text(
            "SELECT search_vector IS NOT NULL AS has_vector "
            "FROM document_chunks WHERE id = :id",
        ),
        {"id": chunk.id},
    )
    assert row.scalar_one() is True

    rank_row = await db.execute(
        text(
            "SELECT ts_rank(search_vector, plainto_tsquery('english', :q)) AS rank "
            "FROM document_chunks WHERE id = :id",
        ),
        {"id": chunk.id, "q": "arbitrary detention"},
    )
    assert rank_row.scalar_one() > 0


async def test_chat_session_uploads_fk(db: AsyncSession) -> None:
    user = await _create_user(db)
    session = await _create_session(db, user)
    upload = await _create_upload(db, user)

    link = ChatSessionUpload(session_id=session.id, upload_id=upload.id)
    db.add(link)
    await db.commit()

    factory = get_session_factory()
    async with factory() as verify_db:
        row = await verify_db.execute(
            text(
                "SELECT session_id, upload_id FROM chat_session_uploads "
                "WHERE session_id = :sid AND upload_id = :uid",
            ),
            {"sid": session.id, "uid": upload.id},
        )
        assert row.one() == (session.id, upload.id)


async def test_chat_request_event_seq_unique(db: AsyncSession) -> None:
    user = await _create_user(db)
    session = await _create_session(db, user)
    chat_request = ChatRequest(
        id=uuid.uuid4(),
        session_id=session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
    )
    db.add(chat_request)
    await db.flush()

    db.add(
        ChatRequestEvent(
            chat_request_id=chat_request.id,
            seq=1,
            visibility="concise",
            event_type=ChatRequestEventType.STEP_START,
            payload={"label": "Understanding your question"},
        )
    )
    await db.flush()

    db.add(
        ChatRequestEvent(
            chat_request_id=chat_request.id,
            seq=1,
            visibility="concise",
            event_type=ChatRequestEventType.STEP_END,
            payload={"label": "Done"},
        )
    )

    with pytest.raises(IntegrityError):
        await db.flush()

    await db.rollback()
