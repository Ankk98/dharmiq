from __future__ import annotations

import uuid
from pathlib import Path

from pgvector import Vector as PgVector
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import IngestionError, UploadError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.uploads import UserUpload, UserUploadChunk
from dharmiq.ingestion.chunker import TextChunk, chunk_document
from dharmiq.ingestion.parser import (
    PdfParserBackend,
    extract_image_pages,
    get_pdf_parser,
)
from dharmiq.ingestion.storage import (
    resolve_upload_path,
    save_user_upload_file,
    validate_upload_file,
)
from dharmiq.llm.embeddings import EmbeddingBackend, get_embedding_backend
from dharmiq.observability.metrics import record_ingestion_failure, record_ingestion_success

logger = get_logger(__name__)

PDF_MIME = "application/pdf"
IMAGE_MIME_PREFIX = "image/"


async def count_active_uploads(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(UserUpload)
        .where(UserUpload.user_id == user_id, UserUpload.deleted_at.is_(None))
    )
    return int(result.scalar_one())


async def create_user_upload(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    filename: str,
    mime_type: str | None,
    content: bytes,
    settings: Settings | None = None,
) -> UserUpload:
    cfg = settings or get_settings()
    safe_name = validate_upload_file(
        filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        settings=cfg,
    )

    active_count = await count_active_uploads(db, user_id)
    if active_count >= cfg.uploads.max_assets_per_user:
        raise UploadError(
            "Upload limit reached",
            details={
                "max_assets_per_user": cfg.uploads.max_assets_per_user,
                "active_uploads": active_count,
            },
        )

    upload = UserUpload(
        user_id=user_id,
        original_filename=safe_name,
        file_path="",
        mime_type=mime_type or "application/octet-stream",
        size_bytes=len(content),
        content_hash=compute_file_hash_from_bytes(content),
    )
    db.add(upload)
    await db.flush()

    stored_path = save_user_upload_file(user_id, upload.id, safe_name, content, settings=cfg)
    upload.file_path = str(stored_path)
    await db.commit()
    await db.refresh(upload)
    return upload


def compute_file_hash_from_bytes(content: bytes) -> str:
    import hashlib

    return hashlib.sha256(content).hexdigest()


def _extract_upload_pages(
    upload: UserUpload,
    file_path: Path,
    *,
    settings: Settings,
    pdf_parser: PdfParserBackend,
) -> list:
    if upload.mime_type == PDF_MIME or file_path.suffix.lower() == ".pdf":
        return pdf_parser.extract_pages(file_path)
    if upload.mime_type.startswith(IMAGE_MIME_PREFIX) or file_path.suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".tif",
        ".tiff",
    }:
        return extract_image_pages(file_path, settings=settings)
    raise IngestionError(
        "Unsupported upload type for processing",
        details={"upload_id": str(upload.id), "mime_type": upload.mime_type},
    )


async def process_user_upload(
    db: AsyncSession,
    upload_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    pdf_parser: PdfParserBackend | None = None,
    embedding_backend: EmbeddingBackend | None = None,
) -> int:
    cfg = settings or get_settings()
    upload = await db.get(UserUpload, upload_id)
    if upload is None or upload.deleted_at is not None:
        raise IngestionError("Upload not found", details={"upload_id": str(upload_id)})

    file_path = resolve_upload_path(upload.file_path, cfg)
    parser = pdf_parser or get_pdf_parser(cfg)
    embedder = embedding_backend or get_embedding_backend()

    try:
        pages = _extract_upload_pages(upload, file_path, settings=cfg, pdf_parser=parser)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(
            "Upload parsing failed",
            details={"upload_id": str(upload_id), "error": str(exc)},
        ) from exc

    chunks = chunk_document(pages, settings=cfg)
    await _clear_existing_chunks(db, upload_id)
    chunk_count = await _persist_upload_chunks(
        db,
        upload_id,
        chunks,
        embedder,
        batch_size=cfg.ingestion.batch_size,
    )
    await db.commit()

    record_ingestion_success(chunk_count=chunk_count, page_count=len(pages))
    logger.info(
        "user_upload_indexed",
        upload_id=str(upload_id),
        user_id=str(upload.user_id),
        chunks=chunk_count,
        pages=len(pages),
    )
    return chunk_count


async def _clear_existing_chunks(db: AsyncSession, upload_id: uuid.UUID) -> None:
    await db.execute(delete(UserUploadChunk).where(UserUploadChunk.upload_id == upload_id))


async def _persist_upload_chunks(
    db: AsyncSession,
    upload_id: uuid.UUID,
    chunks: list[TextChunk],
    embedder: EmbeddingBackend,
    *,
    batch_size: int,
) -> int:
    if not chunks:
        return 0

    stored = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        vectors = await embedder.embed_texts([chunk.text for chunk in batch])
        for chunk, vector in zip(batch, vectors, strict=True):
            db.add(
                UserUploadChunk(
                    upload_id=upload_id,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    embedding=PgVector(vector),
                )
            )
            stored += 1
        await db.flush()
    return stored


async def process_user_upload_safe(
    db: AsyncSession,
    upload_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> int:
    try:
        return await process_user_upload(db, upload_id, settings=settings)
    except Exception as exc:
        record_ingestion_failure(reason=type(exc).__name__)
        logger.exception("user_upload_index_failed", upload_id=str(upload_id), error=str(exc))
        raise
