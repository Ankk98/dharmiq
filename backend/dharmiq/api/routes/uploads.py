from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.auth.manager import current_active_user
from dharmiq.api.dependencies import get_settings_dep
from dharmiq.config.settings import Settings
from dharmiq.core.errors import UploadError
from dharmiq.db.models.uploads import ProcessingStage, UserUpload
from dharmiq.db.models.users import User
from dharmiq.db.session import get_db_session
from dharmiq.ingestion.upload_pipeline import create_user_upload
from dharmiq.schemas.uploads import UserUploadCreateResponse, UserUploadRead
from dharmiq.tasks.celery_app import celery_app

router = APIRouter(prefix="/uploads", tags=["uploads"])


async def _get_user_upload(
    upload_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> UserUpload:
    result = await db.execute(
        select(UserUpload).where(
            UserUpload.id == upload_id,
            UserUpload.user_id == user.id,
            UserUpload.deleted_at.is_(None),
        )
    )
    upload = result.scalar_one_or_none()
    if upload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    return upload


def _upload_is_indexed(upload: UserUpload) -> bool:
    return upload.processing_stage == ProcessingStage.READY.value


def _to_read(upload: UserUpload) -> UserUploadRead:
    indexed = _upload_is_indexed(upload)
    return UserUploadRead(
        id=upload.id,
        user_id=upload.user_id,
        original_filename=upload.original_filename,
        mime_type=upload.mime_type,
        size_bytes=upload.size_bytes,
        content_hash=upload.content_hash,
        created_at=upload.created_at,
        deleted_at=upload.deleted_at,
        processing_stage=upload.processing_stage,
        chunk_count=upload.chunk_count,
        processing_error=upload.processing_error,
        indexed=indexed,
    )


@router.post("", response_model=UserUploadCreateResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings_dep),
) -> UserUploadCreateResponse:
    content = await file.read()
    if len(content) > settings.uploads.max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds {settings.uploads.max_size_bytes} byte limit",
        )

    try:
        upload = await create_user_upload(
            db,
            user_id=user.id,
            filename=file.filename or "upload",
            mime_type=file.content_type,
            content=content,
            settings=settings,
        )
    except UploadError as exc:
        status_code = status.HTTP_413_CONTENT_TOO_LARGE
        if "limit reached" in exc.message.lower():
            status_code = status.HTTP_409_CONFLICT
        elif "unsupported" in exc.message.lower() or "empty" in exc.message.lower():
            status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

    celery_app.send_task("dharmiq.ingestion.process_user_upload", args=[str(upload.id)])

    return UserUploadCreateResponse(
        **_to_read(upload).model_dump(),
        processing_enqueued=True,
    )


@router.get("", response_model=list[UserUploadRead])
async def list_uploads(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[UserUploadRead]:
    result = await db.execute(
        select(UserUpload)
        .where(UserUpload.user_id == user.id, UserUpload.deleted_at.is_(None))
        .order_by(UserUpload.created_at.desc())
    )
    uploads = list(result.scalars().all())
    return [_to_read(upload) for upload in uploads]


@router.get("/{upload_id}", response_model=UserUploadRead)
async def get_upload(
    upload_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserUploadRead:
    upload = await _get_user_upload(upload_id, user, db)
    return _to_read(upload)


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_upload(
    upload_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    upload = await _get_user_upload(upload_id, user, db)
    upload.deleted_at = datetime.now(UTC)
    await db.commit()
