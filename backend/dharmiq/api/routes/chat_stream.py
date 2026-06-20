from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.auth.manager import current_active_user
from dharmiq.agents.streaming import stream_chat_request_events
from dharmiq.config.settings import get_settings
from dharmiq.db.models.chats import ChatRequest
from dharmiq.db.models.users import User
from dharmiq.db.session import get_db_session

router = APIRouter(prefix="/chat", tags=["chat-stream"])

ProgressViewParam = Literal["concise", "detailed"]


@router.get("/requests/{request_id}/stream")
async def stream_chat_request(
    request_id: uuid.UUID,
    after_seq: int = Query(default=0, ge=0),
    view: ProgressViewParam = Query(
        default="concise",
        description="Progress detail tier: concise (default) or detailed. Debug is never client-selectable.",
    ),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    result = await db.execute(
        select(ChatRequest).where(
            ChatRequest.id == request_id,
            ChatRequest.user_id == user.id,
        )
    )
    chat_request = result.scalar_one_or_none()
    if chat_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat request not found")

    settings = get_settings()

    async def event_generator():
        async for chunk in stream_chat_request_events(
            db,
            chat_request,
            user,
            after_seq=after_seq,
            view=view,
            settings=settings,
        ):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
