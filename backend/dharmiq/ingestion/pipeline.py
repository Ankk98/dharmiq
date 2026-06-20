from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pgvector import Vector as PgVector
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import IngestionError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.documents import DocumentChunk, DocumentSection, SourceDocument
from dharmiq.ingestion.chunker import (
    CHUNK_SCHEMA_V02,
    DetectedSection,
    SectionChunkGroup,
    chunk_document,
    detect_sections,
)
from dharmiq.ingestion.parser import PdfParserBackend, get_pdf_parser
from dharmiq.ingestion.scanner import ScannedDocument, scan_corpus_directory
from dharmiq.llm.embeddings import EmbeddingBackend, get_embedding_backend
from dharmiq.observability.metrics import record_ingestion_failure, record_ingestion_success

logger = get_logger(__name__)


@dataclass(frozen=True)
class SyncResult:
    scanned: int
    skipped: int
    created: int
    updated: int
    enqueued: list[uuid.UUID]


@dataclass(frozen=True)
class ReindexResult:
    documents: int
    chunks_created: int
    chunks_removed: int


async def sync_corpus_documents(
    db: AsyncSession,
    *,
    settings: Settings | None = None,
    enqueue: bool = True,
) -> SyncResult:
    """Scan corpus directory and register new or changed PDFs."""
    cfg = settings or get_settings()
    scanned_docs = scan_corpus_directory(settings=cfg)

    skipped = 0
    created = 0
    updated = 0
    enqueued: list[uuid.UUID] = []

    for doc in scanned_docs:
        document_id, action = await _register_scanned_document(db, doc)
        if action == "skipped":
            skipped += 1
            continue
        if action == "created":
            created += 1
        elif action == "updated":
            updated += 1

        if enqueue:
            from dharmiq.tasks.celery_app import celery_app

            celery_app.send_task("dharmiq.ingestion.process_pdf", args=[str(document_id)])
            enqueued.append(document_id)

    await db.commit()
    logger.info(
        "corpus_sync_complete",
        scanned=len(scanned_docs),
        skipped=skipped,
        created=created,
        updated=updated,
        enqueued=len(enqueued),
    )
    return SyncResult(
        scanned=len(scanned_docs),
        skipped=skipped,
        created=created,
        updated=updated,
        enqueued=enqueued,
    )


async def _register_scanned_document(
    db: AsyncSession,
    scanned: ScannedDocument,
) -> tuple[uuid.UUID, str]:
    result = await db.execute(
        select(SourceDocument)
        .where(SourceDocument.source_id == scanned.source_id)
        .order_by(SourceDocument.version.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()

    if existing and existing.content_hash == scanned.content_hash:
        if existing.indexed_at is not None:
            return existing.id, "skipped"
        return existing.id, "updated"

    if existing:
        document = SourceDocument(
            source_id=scanned.source_id,
            title=scanned.title,
            doc_type=scanned.doc_type,
            jurisdiction=scanned.jurisdiction,
            version=existing.version + 1,
            content_hash=scanned.content_hash,
            file_path=str(scanned.file_path),
        )
        action = "updated"
    else:
        document = SourceDocument(
            source_id=scanned.source_id,
            title=scanned.title,
            doc_type=scanned.doc_type,
            jurisdiction=scanned.jurisdiction,
            version=1,
            content_hash=scanned.content_hash,
            file_path=str(scanned.file_path),
        )
        action = "created"

    db.add(document)
    await db.flush()
    return document.id, action


async def _parse_document_pages(
    document: SourceDocument,
    *,
    settings: Settings,
    parser: PdfParserBackend,
) -> list:
    from pathlib import Path

    file_path = Path(document.file_path)
    if not file_path.is_absolute():
        file_path = (settings.repo_root / file_path).resolve()

    try:
        return parser.extract_pages(file_path)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(
            "PDF parsing failed",
            details={"document_id": str(document.id), "error": str(exc)},
        ) from exc


async def process_document(
    db: AsyncSession,
    document_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    parser: PdfParserBackend | None = None,
    embedding_backend: EmbeddingBackend | None = None,
) -> int:
    """Parse, chunk, embed, and persist a source document."""
    cfg = settings or get_settings()
    document = await db.get(SourceDocument, document_id)
    if document is None:
        raise IngestionError("Document not found", details={"document_id": str(document_id)})

    pdf_parser = parser or get_pdf_parser(cfg)
    embedder = embedding_backend or get_embedding_backend()
    pages = await _parse_document_pages(document, settings=cfg, parser=pdf_parser)

    sections = detect_sections(pages)
    groups = chunk_document(pages, settings=cfg)

    await _clear_existing_index(db, document_id)

    section_rows = await _persist_sections(db, document_id, sections)
    chunk_count = await _persist_chunk_groups(
        db,
        document_id,
        groups,
        section_rows,
        embedder,
        batch_size=cfg.ingestion.batch_size,
    )

    document.indexed_at = datetime.now(UTC)
    await db.commit()

    record_ingestion_success(chunk_count=chunk_count, page_count=len(pages))
    logger.info(
        "document_indexed",
        document_id=str(document_id),
        source_id=document.source_id,
        sections=len(section_rows),
        chunks=chunk_count,
        pages=len(pages),
    )
    return chunk_count


async def reindex_document_v02(
    db: AsyncSession,
    document_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    parser: PdfParserBackend | None = None,
    embedding_backend: EmbeddingBackend | None = None,
) -> tuple[int, int]:
    """Non-destructive v0.2 reindex: write new parent/child chunks, then remove legacy rows."""
    cfg = settings or get_settings()
    document = await db.get(SourceDocument, document_id)
    if document is None:
        raise IngestionError("Document not found", details={"document_id": str(document_id)})

    pdf_parser = parser or get_pdf_parser(cfg)
    embedder = embedding_backend or get_embedding_backend()
    pages = await _parse_document_pages(document, settings=cfg, parser=pdf_parser)

    sections = detect_sections(pages)
    groups = chunk_document(pages, settings=cfg)
    section_rows = await _persist_sections(db, document_id, sections)
    created = await _persist_chunk_groups(
        db,
        document_id,
        groups,
        section_rows,
        embedder,
        batch_size=cfg.ingestion.batch_size,
    )

    if created == 0:
        raise IngestionError(
            "v0.2 reindex produced no chunks",
            details={"document_id": str(document_id)},
        )

    child_count = (
        await db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM document_chunks
                WHERE document_id = :document_id
                  AND metadata->>'schema_version' = :schema_version
                  AND parent_chunk_id IS NOT NULL
                """
            ),
            {"document_id": document_id, "schema_version": CHUNK_SCHEMA_V02},
        )
    ).scalar_one()
    if child_count == 0:
        raise IngestionError(
            "v0.2 reindex verification failed: no child chunks",
            details={"document_id": str(document_id)},
        )

    removed = await _remove_legacy_chunks(db, document_id)
    document.indexed_at = datetime.now(UTC)
    await db.commit()

    logger.info(
        "document_reindexed_v02",
        document_id=str(document_id),
        source_id=document.source_id,
        chunks_created=created,
        chunks_removed=removed,
    )
    return created, removed


async def reindex_corpus_v02(
    db: AsyncSession,
    *,
    settings: Settings | None = None,
    parser: PdfParserBackend | None = None,
    embedding_backend: EmbeddingBackend | None = None,
) -> ReindexResult:
    """Reindex all indexed corpus documents with parent/child v0.2 chunking."""
    cfg = settings or get_settings()
    pdf_parser = parser or get_pdf_parser(cfg)
    embedder = embedding_backend or get_embedding_backend()

    result = await db.execute(
        select(SourceDocument.id).where(SourceDocument.indexed_at.is_not(None)).order_by(SourceDocument.source_id)
    )
    document_ids = list(result.scalars().all())

    total_created = 0
    total_removed = 0
    for document_id in document_ids:
        created, removed = await reindex_document_v02(
            db,
            document_id,
            settings=cfg,
            parser=pdf_parser,
            embedding_backend=embedder,
        )
        total_created += created
        total_removed += removed

    logger.info(
        "corpus_reindexed_v02",
        documents=len(document_ids),
        chunks_created=total_created,
        chunks_removed=total_removed,
    )
    return ReindexResult(
        documents=len(document_ids),
        chunks_created=total_created,
        chunks_removed=total_removed,
    )


async def _clear_existing_index(db: AsyncSession, document_id: uuid.UUID) -> None:
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    await db.execute(delete(DocumentSection).where(DocumentSection.document_id == document_id))


async def _remove_legacy_chunks(db: AsyncSession, document_id: uuid.UUID) -> int:
    result = await db.execute(
        text(
            """
            DELETE FROM document_chunks
            WHERE document_id = :document_id
              AND COALESCE(metadata->>'schema_version', '') <> :schema_version
            """
        ),
        {"document_id": document_id, "schema_version": CHUNK_SCHEMA_V02},
    )
    return int(result.rowcount or 0)


async def _persist_sections(
    db: AsyncSession,
    document_id: uuid.UUID,
    sections: list[DetectedSection],
) -> dict[str, DocumentSection]:
    existing = (
        await db.execute(select(DocumentSection).where(DocumentSection.document_id == document_id))
    ).scalars().all()
    if existing:
        return {section.label: section for section in existing}

    rows: dict[str, DocumentSection] = {}
    for section in sections:
        row = DocumentSection(
            document_id=document_id,
            label=section.label,
            number=section.number,
            start_page=section.start_page,
            end_page=section.end_page,
        )
        db.add(row)
        rows[section.label] = row
    await db.flush()
    return rows


async def _persist_chunk_groups(
    db: AsyncSession,
    document_id: uuid.UUID,
    groups: list[SectionChunkGroup],
    section_rows: dict[str, DocumentSection],
    embedder: EmbeddingBackend,
    *,
    batch_size: int,
) -> int:
    if not groups:
        return 0

    stored = 0
    child_batches: list[tuple[DocumentChunk, str]] = []

    for group in groups:
        section_id = None
        if group.parent.section_label and group.parent.section_label in section_rows:
            section_id = section_rows[group.parent.section_label].id

        parent_row = DocumentChunk(
            document_id=document_id,
            section_id=section_id,
            chunk_index=group.parent.chunk_index,
            text=group.parent.text,
            context_text=group.parent.context_text,
            chunk_metadata=group.parent.chunk_metadata,
            page_start=group.parent.page_start,
            page_end=group.parent.page_end,
            embedding=None,
        )
        db.add(parent_row)
        await db.flush()

        for child in group.children:
            child_row = DocumentChunk(
                document_id=document_id,
                section_id=section_id,
                chunk_index=child.chunk_index,
                text=child.text,
                context_text=child.context_text,
                parent_chunk_id=parent_row.id,
                chunk_metadata=child.chunk_metadata,
                page_start=child.page_start,
                page_end=child.page_end,
            )
            db.add(child_row)
            child_batches.append((child_row, child.text))
            stored += 1

        stored += 1

    for start in range(0, len(child_batches), batch_size):
        batch = child_batches[start : start + batch_size]
        vectors = await embedder.embed_texts([text for _, text in batch])
        for (row, _), vector in zip(batch, vectors, strict=True):
            row.embedding = PgVector(vector)
        await db.flush()

    return stored


async def process_document_safe(
    db: AsyncSession,
    document_id: uuid.UUID,
    *,
    settings: Settings | None = None,
) -> int:
    try:
        return await process_document(db, document_id, settings=settings)
    except Exception as exc:
        record_ingestion_failure(reason=type(exc).__name__)
        logger.exception("document_index_failed", document_id=str(document_id), error=str(exc))
        raise


async def reindex_corpus_v02_safe(
    db: AsyncSession,
    *,
    settings: Settings | None = None,
) -> ReindexResult:
    try:
        return await reindex_corpus_v02(db, settings=settings)
    except Exception as exc:
        record_ingestion_failure(reason=type(exc).__name__)
        logger.exception("corpus_reindex_v02_failed", error=str(exc))
        raise
