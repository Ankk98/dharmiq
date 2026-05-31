"""Celery tasks for corpus ingestion."""

from __future__ import annotations

import asyncio
import uuid

from dharmiq.config.settings import get_settings
from dharmiq.core.logging import get_logger, setup_logging
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.ingestion.pipeline import process_document_safe, sync_corpus_documents
from dharmiq.observability.metrics import record_sync_run
from dharmiq.tasks.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


async def _with_db_session(coro_factory):
    await init_db()
    factory = get_session_factory()
    try:
        async with factory() as db:
            return await coro_factory(db)
    finally:
        await close_db()


@celery_app.task(name="dharmiq.ingestion.sync_india_code_pdfs", bind=True, max_retries=2)
def sync_india_code_pdfs(self) -> dict[str, int | list[str]]:
    """Daily scan for new or updated IndiaCode PDFs in the corpus directory."""
    settings = get_settings()
    setup_logging(settings)
    logger.info("sync_india_code_pdfs_started")

    async def _run(db):
        result = await sync_corpus_documents(db, settings=settings, enqueue=True)
        record_sync_run(
            scanned=result.scanned,
            skipped=result.skipped,
            created=result.created,
            updated=result.updated,
        )
        return result

    try:
        result = _run_async(_with_db_session(_run))
    except Exception as exc:
        logger.exception("sync_india_code_pdfs_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1)) from exc

    return {
        "scanned": result.scanned,
        "skipped": result.skipped,
        "created": result.created,
        "updated": result.updated,
        "enqueued": [str(doc_id) for doc_id in result.enqueued],
    }


@celery_app.task(name="dharmiq.ingestion.process_pdf", bind=True, max_retries=3)
def process_pdf(self, document_id: str) -> dict[str, int | str]:
    """Parse, chunk, embed, and index a single source document."""
    settings = get_settings()
    setup_logging(settings)
    doc_uuid = uuid.UUID(document_id)
    logger.info("process_pdf_started", document_id=document_id)

    async def _run(db):
        chunk_count = await process_document_safe(db, doc_uuid, settings=settings)
        return chunk_count

    try:
        chunk_count = _run_async(_with_db_session(_run))
    except Exception as exc:
        logger.exception("process_pdf_failed", document_id=document_id, error=str(exc))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1)) from exc

    return {"document_id": document_id, "chunks": chunk_count}
