from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from dharmiq.core.logging import get_logger
from dharmiq.observability.prometheus_metrics import (
    EVAL_ANSWER_CORRECTNESS,
    EVAL_RUNS_TOTAL,
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    INGESTION_CHUNKS_INDEXED_TOTAL,
    INGESTION_DOCUMENTS_FAILED_TOTAL,
    INGESTION_DOCUMENTS_PROCESSED_TOTAL,
    INGESTION_LAST_FAILURE_REASON,
    INGESTION_PAGES_PROCESSED_TOTAL,
    INGESTION_SYNC_CREATED,
    INGESTION_SYNC_SCANNED,
    INGESTION_SYNC_SKIPPED,
    INGESTION_SYNC_UPDATED,
    LLM_TOKENS_TOTAL,
)

logger = get_logger(__name__)
_lock = Lock()


@dataclass
class IngestionMetrics:
    documents_processed: int = 0
    documents_failed: int = 0
    chunks_indexed: int = 0
    pages_processed: int = 0
    last_failure_reason: str | None = None


_metrics = IngestionMetrics()


def record_http_request(*, method: str, path: str, status_code: int, duration_seconds: float) -> None:
    status = str(status_code)
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)
    if status_code >= 500:
        HTTP_ERRORS_TOTAL.labels(method=method, path=path).inc()


def record_llm_tokens(*, model: str, agent: str, tokens: int) -> None:
    if tokens <= 0:
        return
    LLM_TOKENS_TOTAL.labels(model=model, agent=agent).inc(tokens)


def record_ingestion_success(*, chunk_count: int, page_count: int) -> None:
    with _lock:
        _metrics.documents_processed += 1
        _metrics.chunks_indexed += chunk_count
        _metrics.pages_processed += page_count
    INGESTION_DOCUMENTS_PROCESSED_TOTAL.inc()
    INGESTION_CHUNKS_INDEXED_TOTAL.inc(chunk_count)
    INGESTION_PAGES_PROCESSED_TOTAL.inc(page_count)
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
    INGESTION_DOCUMENTS_FAILED_TOTAL.inc()
    INGESTION_LAST_FAILURE_REASON.labels(reason=reason[:120]).set(1)
    logger.warning(
        "ingestion_metrics",
        metric_event="failure",
        documents_failed=_metrics.documents_failed,
        reason=reason,
    )


def record_sync_run(*, scanned: int, skipped: int, created: int, updated: int) -> None:
    INGESTION_SYNC_SCANNED.set(scanned)
    INGESTION_SYNC_SKIPPED.set(skipped)
    INGESTION_SYNC_CREATED.set(created)
    INGESTION_SYNC_UPDATED.set(updated)
    logger.info(
        "ingestion_metrics",
        metric_event="sync",
        scanned=scanned,
        skipped=skipped,
        created=created,
        updated=updated,
    )


def record_eval_run(*, dataset: str, question_count: int, metrics: dict[str, float]) -> None:
    EVAL_RUNS_TOTAL.labels(dataset=dataset).inc()
    for key in (
        "faithfulness",
        "answer_correctness",
        "llm_answer_correctness",
        "llm_citation_correctness",
    ):
        if key in metrics:
            EVAL_ANSWER_CORRECTNESS.labels(dataset=dataset, metric=key).set(float(metrics[key]))
    logger.info(
        "eval_metrics",
        dataset=dataset,
        question_count=question_count,
        metrics=metrics,
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
