from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.auth.manager import current_active_user
from dharmiq.db.models.documents import SourceDocument
from dharmiq.db.models.uploads import UserUpload
from dharmiq.db.models.users import User
from dharmiq.db.session import get_db_session
from dharmiq.llm.retrieval import SourceType
from dharmiq.documents.chunks import get_document_chunk, list_document_chunks
from dharmiq.schemas.chunks import ChunkListResponse, ChunkRead
from dharmiq.schemas.documents import DocumentRead

router = APIRouter(prefix="/docs", tags=["docs"])

_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _guess_mime(path: Path) -> str:
    return _MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document_metadata(
    document_id: uuid.UUID,
    source_type: SourceType = Query(default="corpus"),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    if source_type == "upload":
        result = await db.execute(
            select(UserUpload).where(
                UserUpload.id == document_id,
                UserUpload.user_id == user.id,
                UserUpload.deleted_at.is_(None),
            )
        )
        upload = result.scalar_one_or_none()
        if upload is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        return DocumentRead(
            id=upload.id,
            source_type="upload",
            title=upload.original_filename,
            mime_type=upload.mime_type,
            file_path=upload.file_path,
            created_at=upload.created_at,
        )

    result = await db.execute(select(SourceDocument).where(SourceDocument.id == document_id))
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = Path(document.file_path)
    return DocumentRead(
        id=document.id,
        source_type="corpus",
        title=document.title,
        doc_type=document.doc_type,
        jurisdiction=document.jurisdiction,
        enactment_date=document.enactment_date,
        enforcement_date=document.enforcement_date,
        status=document.status,
        superseded_by_source_id=document.superseded_by_source_id,
        canonical_url=document.canonical_url,
        mime_type=_guess_mime(file_path),
        file_path=document.file_path,
        created_at=document.created_at,
    )


@router.get("/{document_id}/file")
async def download_document_file(
    document_id: uuid.UUID,
    source_type: SourceType = Query(default="corpus"),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    metadata = await get_document_metadata(document_id, source_type, user, db)
    path = Path(metadata.file_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found on disk")

    filename = metadata.title if metadata.source_type == "upload" else path.name
    return FileResponse(
        path,
        media_type=metadata.mime_type,
        filename=filename,
    )


@router.get("/{document_id}/chunks", response_model=ChunkListResponse)
async def list_chunks(
    document_id: uuid.UUID,
    source_type: SourceType = Query(default="corpus"),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChunkListResponse:
    result = await list_document_chunks(
        db,
        document_id=document_id,
        source_type=source_type,
        user=user,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return result


@router.get("/{document_id}/chunks/{chunk_id}", response_model=ChunkRead)
async def get_chunk(
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    source_type: SourceType = Query(default="corpus"),
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> ChunkRead:
    result = await get_document_chunk(
        db,
        document_id=document_id,
        chunk_id=chunk_id,
        source_type=source_type,
        user=user,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chunk not found")
    return result
