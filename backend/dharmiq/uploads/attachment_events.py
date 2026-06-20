from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import ChatMessage, ChatSession, MessageRole


async def record_attachment_event(
    db: AsyncSession,
    *,
    session: ChatSession,
    user_id: uuid.UUID,
    event: str,
    upload_id: uuid.UUID,
    filename: str,
) -> ChatMessage:
    if event == "attached":
        content = f"Attached document: {filename}"
    elif event == "detached":
        content = f"Removed document: {filename}"
    else:
        raise ValueError(f"Unsupported attachment event: {event}")

    message = ChatMessage(
        session_id=session.id,
        user_id=user_id,
        role=MessageRole.SYSTEM,
        content=content,
        message_metadata={
            "event_type": f"attachment_{event}",
            "upload_id": str(upload_id),
            "filename": filename,
        },
    )
    db.add(message)
    return message
