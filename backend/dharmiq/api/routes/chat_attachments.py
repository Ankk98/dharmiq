from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.auth.manager import current_active_user
from dharmiq.core.errors import UploadError
from dharmiq.db.models.users import User
from dharmiq.db.session import get_db_session
from dharmiq.api.routes.chat import _get_user_session
from dharmiq.schemas.chat import ChatSessionUploadAttachRequest, ChatSessionUploadRead
from dharmiq.uploads.session_attachments import (
    attach_uploads_to_session,
    detach_upload_from_session,
    list_attached_uploads,
)

router = APIRouter(prefix="/chat/sessions", tags=["chat-attachments"])


@router.get("/{session_id}/attachments", response_model=list[ChatSessionUploadRead])
async def list_session_attachments(
    session_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatSessionUploadRead]:
    await _get_user_session(session_id, user, db)
    attached = await list_attached_uploads(db, session_id)
    return [
        ChatSessionUploadRead(
            session_id=session_id,
            upload_id=info.upload_id,
            attached_at=info.attached_at,
        )
        for info in attached
    ]


@router.post("/{session_id}/attachments", response_model=list[ChatSessionUploadRead])
async def attach_uploads(
    session_id: uuid.UUID,
    body: ChatSessionUploadAttachRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatSessionUploadRead]:
    chat_session = await _get_user_session(session_id, user, db)
    try:
        attached = await attach_uploads_to_session(
            db,
            session=chat_session,
            user_id=user.id,
            upload_ids=body.upload_ids,
        )
    except UploadError as exc:
        status_code = status.HTTP_404_NOT_FOUND
        if "another user's upload" in exc.message.lower():
            status_code = status.HTTP_403_FORBIDDEN
        elif "not indexed" in exc.message.lower():
            status_code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

    return [
        ChatSessionUploadRead(
            session_id=session_id,
            upload_id=info.upload_id,
            attached_at=info.attached_at,
        )
        for info in attached
    ]


@router.delete("/{session_id}/attachments/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_upload(
    session_id: uuid.UUID,
    upload_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    await _get_user_session(session_id, user, db)
    await detach_upload_from_session(db, session_id=session_id, upload_id=upload_id)
