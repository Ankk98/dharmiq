from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from dharmiq.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionMetrics:
    documents_processed: int = 0
    documents_failed: int = 0
    chunks_indexed: int = 0
    pages_processed: int = 0
    last_failure_reason: str | None = None


_metrics = IngestionMetrics()
_lock = Lock()


def record_ingestion_success(*, chunk_count: int, page_count: int) -> None:
    with _lock:
        _metrics.documents_processed += 1
        _metrics.chunks_indexed += chunk_count
        _metrics.pages_processed += page_count
    logger.info(
        "ingestion_metrics",
        metric_event="success",
        documents_processed=_metrics.documents_processed,
        chunks_indexed=_metrics.chunks_indexed,
        pages_processed=_metrics.pages_processed,
    )


def record_ingestion_failure(*, reason: str) -> None:
    with _lock:
        _metrics.documents_failed += 1
        _metrics.last_failure_reason = reason
    logger.warning(
        "ingestion_metrics",
        metric_event="failure",
        documents_failed=_metrics.documents_failed,
        reason=reason,
    )


def record_sync_run(*, scanned: int, skipped: int, created: int, updated: int) -> None:
    logger.info(
        "ingestion_metrics",
        metric_event="sync",
        scanned=scanned,
        skipped=skipped,
        created=created,
        updated=updated,
    )


def get_ingestion_metrics() -> dict[str, int | str | None]:
    with _lock:
        return {
            "documents_processed": _metrics.documents_processed,
            "documents_failed": _metrics.documents_failed,
            "chunks_indexed": _metrics.chunks_indexed,
            "pages_processed": _metrics.pages_processed,
            "last_failure_reason": _metrics.last_failure_reason,
        }


def reset_ingestion_metrics() -> None:
    global _metrics
    with _lock:
        _metrics = IngestionMetrics()
