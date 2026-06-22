from __future__ import annotations

import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from dharmiq.db.models.documents import DocumentChunk, SourceDocument
from dharmiq.db.models.uploads import UserUpload, UserUploadChunk
from dharmiq.db.models.users import User
from dharmiq.llm.retrieval import SourceType
from dharmiq.schemas.chunks import ChunkListItem, ChunkListResponse, ChunkRead

_PREVIEW_LEN = 200


def _preview(text: str) -> str:
    if len(text) <= _PREVIEW_LEN:
        return text
    return f"{text[:_PREVIEW_LEN]}…"


def _section_label_from_corpus_chunk(chunk: DocumentChunk) -> str | None:
    if chunk.section is not None:
        return chunk.section.label
    label = chunk.chunk_metadata.get("section_label")
    return str(label) if label else None


def _section_label_from_upload_chunk(chunk: UserUploadChunk) -> str | None:
    label = chunk.chunk_metadata.get("section_label")
    return str(label) if label else None


def _leaf_chunk_filter(model: type[DocumentChunk] | type[UserUploadChunk]):
    child = aliased(model)
    return or_(
        model.parent_chunk_id.isnot(None),
        ~exists().where(child.parent_chunk_id == model.id),
    )


async def _require_owned_upload(
    db: AsyncSession,
    document_id: uuid.UUID,
    user: User,
) -> UserUpload | None:
    result = await db.execute(
        select(UserUpload).where(
            UserUpload.id == document_id,
            UserUpload.user_id == user.id,
            UserUpload.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _require_corpus_document(db: AsyncSession, document_id: uuid.UUID) -> SourceDocument | None:
    result = await db.execute(select(SourceDocument).where(SourceDocument.id == document_id))
    return result.scalar_one_or_none()


async def list_document_chunks(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    source_type: SourceType,
    user: User,
) -> ChunkListResponse | None:
    if source_type == "upload":
        upload = await _require_owned_upload(db, document_id, user)
        if upload is None:
            return None

        result = await db.execute(
            select(UserUploadChunk)
            .where(
                UserUploadChunk.upload_id == document_id,
                _leaf_chunk_filter(UserUploadChunk),
            )
            .order_by(UserUploadChunk.chunk_index.asc())
        )
        chunks = result.scalars().all()
        items = [
            ChunkListItem(
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                preview=_preview(chunk.text),
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_label=_section_label_from_upload_chunk(chunk),
            )
            for chunk in chunks
        ]
        return ChunkListResponse(document_id=document_id, source_type="upload", chunks=items)

    document = await _require_corpus_document(db, document_id)
    if document is None:
        return None

    result = await db.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            _leaf_chunk_filter(DocumentChunk),
        )
        .order_by(DocumentChunk.chunk_index.asc())
    )
    chunks = result.scalars().all()
    # Eager section labels without N+1 when section_id is set.
    for chunk in chunks:
        if chunk.section_id is not None:
            await db.refresh(chunk, attribute_names=["section"])

    items = [
        ChunkListItem(
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            preview=_preview(chunk.text),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_label=_section_label_from_corpus_chunk(chunk),
        )
        for chunk in chunks
    ]
    return ChunkListResponse(document_id=document_id, source_type="corpus", chunks=items)


async def get_document_chunk(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    source_type: SourceType,
    user: User,
) -> ChunkRead | None:
    if source_type == "upload":
        upload = await _require_owned_upload(db, document_id, user)
        if upload is None:
            return None

        result = await db.execute(
            select(UserUploadChunk).where(
                UserUploadChunk.id == chunk_id,
                UserUploadChunk.upload_id == document_id,
            )
        )
        chunk = result.scalar_one_or_none()
        if chunk is None:
            return None

        return ChunkRead(
            chunk_id=chunk.id,
            document_id=document_id,
            source_type="upload",
            text=chunk.text,
            context_text=chunk.context_text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_label=_section_label_from_upload_chunk(chunk),
        )

    document = await _require_corpus_document(db, document_id)
    if document is None:
        return None

    result = await db.execute(
        select(DocumentChunk).where(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id,
        )
    )
    chunk = result.scalar_one_or_none()
    if chunk is None:
        return None

    if chunk.section_id is not None:
        await db.refresh(chunk, attribute_names=["section"])

    return ChunkRead(
        chunk_id=chunk.id,
        document_id=document_id,
        source_type="corpus",
        text=chunk.text,
        context_text=chunk.context_text,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        section_label=_section_label_from_corpus_chunk(chunk),
    )
