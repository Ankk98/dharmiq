from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from langchain_core.runnables import RunnableConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.messages import REFUSAL_MESSAGE, VALIDATION_FAILED_MESSAGE
from dharmiq.agents.nodes.finalizer import finalizer_node
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.config.settings import get_settings
from dharmiq.corpus.footnote import SOURCES_INDEXED_MARKER, append_corpus_footnote
from dharmiq.corpus.indexed_at import get_corpus_indexed_date
from dharmiq.db.models.chats import ChatRequest, ChatRequestStatus, ChatSession, MessageRole
from dharmiq.db.models.documents import DocType, SourceDocument
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.llm.openrouter_client import get_openrouter_client
from tests.corpus_helpers import with_indexed_at

_INDEXED_DATE = date(2026, 3, 15)
_SAMPLE_ANSWER = "You have protections under Article 22 [1]."


@pytest.fixture(autouse=True)
async def _clean_corpus_documents() -> None:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text("DELETE FROM document_chunks"))
        await session.execute(text("DELETE FROM document_sections"))
        await session.execute(text("DELETE FROM source_documents"))
        await session.commit()
    yield


def _expected_footnote(indexed_date: date | None) -> str:
    label = indexed_date.isoformat() if indexed_date is not None else "unknown"
    return (
        f"\n\n---\n"
        f"Sources indexed: {label} (UTC). "
        "Citations refer to central law as indexed; confirm critical details with a qualified lawyer."
    )


@pytest.mark.timeout(30)
def test_footnote_appended_once() -> None:
    first = append_corpus_footnote(_SAMPLE_ANSWER, _INDEXED_DATE)
    assert SOURCES_INDEXED_MARKER in first
    assert first == _SAMPLE_ANSWER + _expected_footnote(_INDEXED_DATE)

    second = append_corpus_footnote(first, _INDEXED_DATE)
    assert second == first
    assert second.count(SOURCES_INDEXED_MARKER) == 1


@pytest.mark.timeout(30)
def test_footnote_skipped_on_refusal() -> None:
    unchanged = append_corpus_footnote(REFUSAL_MESSAGE, _INDEXED_DATE)
    assert unchanged == REFUSAL_MESSAGE
    assert SOURCES_INDEXED_MARKER not in unchanged


@pytest.mark.timeout(30)
def test_footnote_skipped_on_validation_failure() -> None:
    unchanged = append_corpus_footnote(VALIDATION_FAILED_MESSAGE, _INDEXED_DATE)
    assert unchanged == VALIDATION_FAILED_MESSAGE
    assert SOURCES_INDEXED_MARKER not in unchanged


@pytest.mark.timeout(30)
def test_footnote_unknown_date() -> None:
    result = append_corpus_footnote(_SAMPLE_ANSWER, None)
    assert "Sources indexed: unknown (UTC)" in result


@pytest.mark.timeout(30)
async def test_get_corpus_indexed_date_returns_latest(db: AsyncSession) -> None:
    older = with_indexed_at(
        SourceDocument(
            source_id=f"footnote-older-{uuid.uuid4()}",
            title="Older Act",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-older",
            file_path="/tmp/older.pdf",
            indexed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    newer = with_indexed_at(
        SourceDocument(
            source_id=f"footnote-newer-{uuid.uuid4()}",
            title="Newer Act",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-newer",
            file_path="/tmp/newer.pdf",
            indexed_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
        )
    )
    db.add(older)
    db.add(newer)
    await db.commit()

    indexed_date = await get_corpus_indexed_date(db)
    assert indexed_date == date(2026, 6, 1)


@pytest.mark.timeout(30)
async def test_get_corpus_indexed_date_empty_corpus(db: AsyncSession) -> None:
    assert await get_corpus_indexed_date(db) is None


@pytest.mark.timeout(30)
async def test_finalizer_appends_footnote(db: AsyncSession) -> None:
    document = with_indexed_at(
        SourceDocument(
            source_id=f"footnote-finalizer-{uuid.uuid4()}",
            title="Test Act",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-finalizer",
            file_path="/tmp/test.pdf",
            indexed_at=datetime(2026, 3, 15, tzinfo=UTC),
        )
    )
    db.add(document)

    user = User(email=f"footnote-{uuid.uuid4()}@example.com", hashed_password="x", is_active=True)
    db.add(user)
    await db.flush()

    session = ChatSession(user_id=user.id)
    db.add(session)
    await db.flush()

    chat_request = ChatRequest(
        session_id=session.id,
        user_id=user.id,
        status=ChatRequestStatus.RUNNING,
    )
    db.add(chat_request)
    await db.flush()

    from dharmiq.db.models.chats import ChatMessage

    user_msg = ChatMessage(
        session_id=session.id,
        user_id=user.id,
        role=MessageRole.USER,
        content="What are my rights?",
    )
    db.add(user_msg)
    await db.commit()

    runtime = GraphRuntime(
        db=db,
        settings=get_settings(),
        client=get_openrouter_client(),
        user=user,
        chat_session=session,
        chat_request=chat_request,
        history=[user_msg],
        user_msg=user_msg,
    )

    state = {
        "final_answer": _SAMPLE_ANSWER,
        "draft_answer": _SAMPLE_ANSWER,
        "validator_verdict": {"must_regenerate": False},
        "validation_blocked": False,
        "weak_retrieval": False,
        "citations": [],
        "total_tokens": 0,
    }
    config: RunnableConfig = {"configurable": {"runtime": runtime}}

    result = await finalizer_node(state, config)

    assert SOURCES_INDEXED_MARKER in result["final_answer"]
    assert "Sources indexed: 2026-03-15 (UTC)" in result["final_answer"]
