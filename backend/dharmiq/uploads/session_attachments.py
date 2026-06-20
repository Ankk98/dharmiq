from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.core.errors import UploadError
from dharmiq.db.models.chats import ChatSession, ChatSessionUpload
from dharmiq.db.models.uploads import UserUpload, UserUploadChunk
from dharmiq.uploads.attachment_events import record_attachment_event


@dataclass(frozen=True)
class AttachedUploadInfo:
    upload_id: uuid.UUID
    original_filename: str
    mime_type: str
    indexed: bool
    attached_at: datetime


async def _upload_is_indexed(db: AsyncSession, upload_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(UserUploadChunk.id).where(UserUploadChunk.upload_id == upload_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def list_attached_uploads(
    db: AsyncSession,
    session_id: uuid.UUID,
    *,
    as_of: datetime | None = None,
) -> list[AttachedUploadInfo]:
    query = (
        select(ChatSessionUpload, UserUpload)
        .join(UserUpload, UserUpload.id == ChatSessionUpload.upload_id)
        .where(
            ChatSessionUpload.session_id == session_id,
            UserUpload.deleted_at.is_(None),
        )
    )
    if as_of is not None:
        query = query.where(ChatSessionUpload.attached_at <= as_of)
    query = query.order_by(ChatSessionUpload.attached_at.asc())
    result = await db.execute(query)
    rows = result.all()
    attached: list[AttachedUploadInfo] = []
    for link, upload in rows:
        indexed = await _upload_is_indexed(db, upload.id)
        attached.append(
            AttachedUploadInfo(
                upload_id=upload.id,
                original_filename=upload.original_filename,
                mime_type=upload.mime_type,
                indexed=indexed,
                attached_at=link.attached_at,
            )
        )
    return attached


async def attach_uploads_to_session(
    db: AsyncSession,
    *,
    session: ChatSession,
    user_id: uuid.UUID,
    upload_ids: list[uuid.UUID],
) -> list[AttachedUploadInfo]:
    if not upload_ids:
        return await list_attached_uploads(db, session.id)

    unique_ids = list(dict.fromkeys(upload_ids))
    result = await db.execute(
        select(UserUpload).where(
            UserUpload.id.in_(unique_ids),
            UserUpload.deleted_at.is_(None),
        )
    )
    uploads = {upload.id: upload for upload in result.scalars().all()}

    for upload_id in unique_ids:
        upload = uploads.get(upload_id)
        if upload is None:
            raise UploadError("Upload not found", details={"upload_id": str(upload_id)})
        if upload.user_id != user_id:
            raise UploadError(
                "Cannot attach another user's upload",
                details={"upload_id": str(upload_id)},
            )
        if not await _upload_is_indexed(db, upload_id):
            raise UploadError(
                "Upload is not indexed yet",
                details={"upload_id": str(upload_id)},
            )

    existing = await db.execute(
        select(ChatSessionUpload.upload_id).where(
            ChatSessionUpload.session_id == session.id,
            ChatSessionUpload.upload_id.in_(unique_ids),
        )
    )
    already_attached = set(existing.scalars().all())
    now = datetime.now(UTC)

    for upload_id in unique_ids:
        if upload_id in already_attached:
            continue
        db.add(
            ChatSessionUpload(
                session_id=session.id,
                upload_id=upload_id,
                attached_at=now,
            )
        )
        await record_attachment_event(
            db,
            session=session,
            user_id=user_id,
            event="attached",
            upload_id=upload_id,
            filename=uploads[upload_id].original_filename,
        )

    await db.commit()
    return await list_attached_uploads(db, session.id)


async def detach_upload_from_session(
    db: AsyncSession,
    *,
    session: ChatSession,
    user_id: uuid.UUID,
    upload_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(UserUpload).where(
            UserUpload.id == upload_id,
            UserUpload.deleted_at.is_(None),
        )
    )
    upload = result.scalar_one_or_none()
    if upload is not None:
        await record_attachment_event(
            db,
            session=session,
            user_id=user_id,
            event="detached",
            upload_id=upload_id,
            filename=upload.original_filename,
        )

    await db.execute(
        delete(ChatSessionUpload).where(
            ChatSessionUpload.session_id == session.id,
            ChatSessionUpload.upload_id == upload_id,
        )
    )
    await db.commit()
