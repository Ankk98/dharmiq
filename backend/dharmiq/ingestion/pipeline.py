from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pgvector import Vector as PgVector
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import IngestionError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.documents import DocumentChunk, DocumentSection, SourceDocument
from dharmiq.ingestion.chunker import DetectedSection, TextChunk, chunk_document, detect_sections
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

    from pathlib import Path

    file_path = Path(document.file_path)
    if not file_path.is_absolute():
        file_path = (cfg.repo_root / file_path).resolve()

    try:
        pages = pdf_parser.extract_pages(file_path)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(
            "PDF parsing failed",
            details={"document_id": str(document_id), "error": str(exc)},
        ) from exc

    sections = detect_sections(pages)
    chunks = chunk_document(pages, settings=cfg)

    await _clear_existing_index(db, document_id)

    section_rows = await _persist_sections(db, document_id, sections)
    chunk_count = await _persist_chunks(
        db,
        document_id,
        chunks,
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


async def _clear_existing_index(db: AsyncSession, document_id: uuid.UUID) -> None:
    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
    await db.execute(delete(DocumentSection).where(DocumentSection.document_id == document_id))


async def _persist_sections(
    db: AsyncSession,
    document_id: uuid.UUID,
    sections: list[DetectedSection],
) -> dict[str, DocumentSection]:
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


async def _persist_chunks(
    db: AsyncSession,
    document_id: uuid.UUID,
    chunks: list[TextChunk],
    section_rows: dict[str, DocumentSection],
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
            section_id = None
            if chunk.section_label and chunk.section_label in section_rows:
                section_id = section_rows[chunk.section_label].id
            db.add(
                DocumentChunk(
                    document_id=document_id,
                    section_id=section_id,
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
