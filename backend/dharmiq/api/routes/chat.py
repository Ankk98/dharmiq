from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.auth.manager import current_active_user
from dharmiq.db.models.chats import ChatMessage, ChatSession, MessageRole
from dharmiq.db.models.users import User
from dharmiq.db.session import get_db_session
from dharmiq.schemas.chat import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
)

router = APIRouter(prefix="/chat", tags=["chat"])

_TITLE_MAX_LEN = 80


def _title_from_content(content: str) -> str:
    stripped = content.strip().replace("\n", " ")
    if len(stripped) <= _TITLE_MAX_LEN:
        return stripped
    return f"{stripped[: _TITLE_MAX_LEN - 3].rstrip()}..."


async def _get_user_session(
    session_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    )
    chat_session = result.scalar_one_or_none()
    if chat_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return chat_session


@router.post("/sessions", response_model=ChatSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChatSession:
    chat_session = ChatSession(user_id=user.id, title=body.title)
    db.add(chat_session)
    await db.commit()
    await db.refresh(chat_session)
    return chat_session


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatSession]:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChatSession:
    return await _get_user_session(session_id, user, db)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def append_message(
    session_id: uuid.UUID,
    body: ChatMessageCreate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChatMessage:
    chat_session = await _get_user_session(session_id, user, db)

    message = ChatMessage(
        session_id=chat_session.id,
        user_id=user.id,
        role=body.role,
        content=body.content,
        message_metadata=body.metadata,
    )
    db.add(message)

    if chat_session.title is None and body.role == MessageRole.USER:
        chat_session.title = _title_from_content(body.content)

    await db.commit()
    await db.refresh(message)
    return message


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageRead])
async def list_messages(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatMessage]:
    await _get_user_session(session_id, user, db)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    return list(result.scalars().all())
