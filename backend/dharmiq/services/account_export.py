from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import ChatMessage, ChatSession
from dharmiq.db.models.uploads import UserUpload
from dharmiq.db.models.users import User
from dharmiq.schemas.account import (
    AccountExportMessage,
    AccountExportPayload,
    AccountExportSession,
    AccountExportUpload,
    AccountExportUser,
)


async def build_account_export(user: User, db: AsyncSession) -> AccountExportPayload:
    sessions_result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.created_at)
    )
    sessions = list(sessions_result.scalars().all())

    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at)
    )
    messages = list(messages_result.scalars().all())

    uploads_result = await db.execute(
        select(UserUpload)
        .where(
            UserUpload.user_id == user.id,
            UserUpload.deleted_at.is_(None),
        )
        .order_by(UserUpload.created_at)
    )
    uploads = list(uploads_result.scalars().all())

    return AccountExportPayload(
        exported_at=datetime.now(UTC),
        user=AccountExportUser(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
        ),
        sessions=[
            AccountExportSession(
                id=session.id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
            )
            for session in sessions
        ],
        messages=[
            AccountExportMessage(
                id=message.id,
                session_id=message.session_id,
                role=message.role.value,
                content=message.content,
                metadata=message.message_metadata,
                created_at=message.created_at,
            )
            for message in messages
        ],
        uploads=[
            AccountExportUpload(
                id=upload.id,
                original_filename=upload.original_filename,
                mime_type=upload.mime_type,
                size_bytes=upload.size_bytes,
                content_hash=upload.content_hash,
                processing_stage=upload.processing_stage,
                chunk_count=upload.chunk_count,
                created_at=upload.created_at,
            )
            for upload in uploads
        ],
    )


def export_filename(exported_at: datetime) -> str:
    date_part = exported_at.astimezone(UTC).strftime("%Y-%m-%d")
    return f"dharmiq-export-{date_part}.json"
