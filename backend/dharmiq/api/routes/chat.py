from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.auth.manager import current_active_user
from dharmiq.agents.runner import (
    create_agent_graph_request,
    edit_user_message_request,
    retry_agent_graph_request,
    run_agent_graph_for_request,
    run_agent_graph_sync,
)
from dharmiq.config.settings import get_settings
from dharmiq.core.errors import DuplicateAnswerError
from dharmiq.db.models.chats import ChatMessage, ChatRequest, ChatRequestStatus, ChatSession, MessageRole
from dharmiq.db.models.feedback import MessageFeedback
from dharmiq.db.models.users import User
from dharmiq.db.session import get_db_session
from dharmiq.schemas.chat import (
    ChatMessageRead,
    ChatPipelineRequest,
    ChatPipelineResponse,
    ChatRequestPendingResponse,
    ChatRequestRead,
    ChatSessionCreate,
    ChatSessionRead,
    SessionMessageCreate,
    SessionMessageEdit,
)
from dharmiq.schemas.feedback import MessageFeedbackCreate, MessageFeedbackRead
from dharmiq.llm.pipeline import run_chat_pipeline
from dharmiq.tasks.chat_tasks import enqueue_agent_graph

router = APIRouter(prefix="/chat", tags=["chat"])

_TITLE_MAX_LEN = 80


def _title_from_content(content: str) -> str:
    stripped = content.strip().replace("\n", " ")
    if len(stripped) <= _TITLE_MAX_LEN:
        return stripped
    return f"{stripped[: _TITLE_MAX_LEN - 3].rstrip()}..."


async def _assert_no_active_request(db: AsyncSession, session_id: uuid.UUID) -> None:
    active = await db.execute(
        select(ChatRequest).where(
            ChatRequest.session_id == session_id,
            ChatRequest.status.in_([ChatRequestStatus.PENDING, ChatRequestStatus.RUNNING]),
        )
    )
    if active.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A chat request is already in progress for this session",
        )


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


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    chat_session = await _get_user_session(session_id, user, db)
    await db.delete(chat_session)
    await db.commit()


@router.post("/sessions/{session_id}/messages")
async def post_session_message(
    session_id: uuid.UUID,
    body: SessionMessageCreate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    chat_session = await _get_user_session(session_id, user, db)
    settings = get_settings()

    if settings.agent_graph.enabled:
        await _assert_no_active_request(db, chat_session.id)

        runtime = await create_agent_graph_request(
            db,
            chat_session=chat_session,
            user=user,
            user_message=body.content,
            force_answer=body.force_answer,
            settings=settings,
        )
        enqueue_agent_graph(runtime.chat_request.id)
        payload = ChatRequestPendingResponse(
            chat_request_id=runtime.chat_request.id,
            user_message_id=runtime.user_msg.id,
            status="pending",
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=payload.model_dump(mode="json"),
        )

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
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=ChatMessageRead.model_validate(message).model_dump(mode="json"),
    )


@router.post("/sessions/{session_id}/messages/{message_id}/retry")
async def retry_session_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    chat_session = await _get_user_session(session_id, user, db)
    settings = get_settings()

    if not settings.agent_graph.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Message retry requires the agent graph pipeline",
        )

    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.session_id == chat_session.id,
            ChatMessage.user_id == user.id,
        )
    )
    user_message = result.scalar_one_or_none()
    if user_message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if user_message.role != MessageRole.USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only user messages can be retried",
        )

    await _assert_no_active_request(db, chat_session.id)

    runtime = await retry_agent_graph_request(
        db,
        chat_session=chat_session,
        user=user,
        user_message=user_message,
        settings=settings,
    )
    try:
        await run_agent_graph_for_request(db, runtime.chat_request.id, settings=settings)
    except DuplicateAnswerError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate_answer")
    payload = ChatRequestPendingResponse(
        chat_request_id=runtime.chat_request.id,
        user_message_id=runtime.user_msg.id,
        status="pending",
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=payload.model_dump(mode="json"),
    )


@router.patch("/sessions/{session_id}/messages/{message_id}")
async def edit_session_message(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: SessionMessageEdit,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    chat_session = await _get_user_session(session_id, user, db)
    settings = get_settings()

    if not settings.agent_graph.enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Message edit requires the agent graph pipeline",
        )

    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.session_id == chat_session.id,
            ChatMessage.user_id == user.id,
        )
    )
    user_message = result.scalar_one_or_none()
    if user_message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if user_message.role != MessageRole.USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only user messages can be edited",
        )

    await _assert_no_active_request(db, chat_session.id)

    runtime = await edit_user_message_request(
        db,
        chat_session=chat_session,
        user=user,
        user_message=user_message,
        new_content=body.content,
        settings=settings,
    )
    try:
        await run_agent_graph_for_request(db, runtime.chat_request.id, settings=settings)
    except DuplicateAnswerError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate_answer")
    payload = ChatRequestPendingResponse(
        chat_request_id=runtime.chat_request.id,
        user_message_id=runtime.user_msg.id,
        status="pending",
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=payload.model_dump(mode="json"),
    )


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


@router.post("/messages/{message_id}/feedback", response_model=MessageFeedbackRead)
async def submit_message_feedback(
    message_id: uuid.UUID,
    body: MessageFeedbackCreate,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> MessageFeedback:
    message_result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.user_id == user.id,
        )
    )
    message = message_result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if message.role != MessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Feedback can only be submitted for assistant messages",
        )

    feedback_result = await db.execute(
        select(MessageFeedback).where(
            MessageFeedback.user_id == user.id,
            MessageFeedback.message_id == message_id,
        )
    )
    feedback = feedback_result.scalar_one_or_none()
    if feedback is None:
        feedback = MessageFeedback(
            user_id=user.id,
            message_id=message_id,
            rating=body.rating,
            reason=body.reason,
        )
        db.add(feedback)
    else:
        feedback.rating = body.rating
        feedback.reason = body.reason

    await db.commit()
    await db.refresh(feedback)
    return feedback


@router.post("", response_model=ChatPipelineResponse)
async def chat(
    body: ChatPipelineRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChatPipelineResponse:
    chat_session = await _get_user_session(body.session_id, user, db)
    settings = get_settings()
    if settings.agent_graph.enabled:
        result = await run_agent_graph_sync(
            db,
            chat_session=chat_session,
            user=user,
            user_message=body.message,
            settings=settings,
        )
    else:
        result = await run_chat_pipeline(
            db,
            chat_session=chat_session,
            user=user,
            user_message=body.message,
        )
    return ChatPipelineResponse(
        chat_request_id=result.chat_request_id,
        status=result.status,
        needs_clarification=result.needs_clarification,
        followup_questions=result.followup_questions,
        answer=result.answer,
        citations=result.citations,
        final_warning=result.final_warning,
        taking_longer_than_expected=result.taking_longer_than_expected,
        messages=result.new_messages,
        error_message=result.error_message,
    )


@router.get("/requests/{request_id}", response_model=ChatRequestRead)
async def get_chat_request(
    request_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChatRequest:
    result = await db.execute(
        select(ChatRequest).where(
            ChatRequest.id == request_id,
            ChatRequest.user_id == user.id,
        )
    )
    chat_request = result.scalar_one_or_none()
    if chat_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat request not found")
    return chat_request
