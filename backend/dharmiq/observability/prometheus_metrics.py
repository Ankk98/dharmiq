from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# HTTP request metrics
HTTP_REQUESTS_TOTAL = Counter(
    "dharmiq_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "dharmiq_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

HTTP_ERRORS_TOTAL = Counter(
    "dharmiq_http_errors_total",
    "Total HTTP 5xx responses",
    ["method", "path"],
)

# LLM token usage (approximate, from OpenRouter usage fields)
LLM_TOKENS_TOTAL = Counter(
    "dharmiq_llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "agent"],
)

# Ingestion metrics
INGESTION_DOCUMENTS_PROCESSED_TOTAL = Counter(
    "dharmiq_ingestion_documents_processed_total",
    "Corpus documents successfully indexed",
)

INGESTION_DOCUMENTS_FAILED_TOTAL = Counter(
    "dharmiq_ingestion_documents_failed_total",
    "Corpus documents that failed indexing",
)

INGESTION_CHUNKS_INDEXED_TOTAL = Counter(
    "dharmiq_ingestion_chunks_indexed_total",
    "Document chunks indexed",
)

INGESTION_PAGES_PROCESSED_TOTAL = Counter(
    "dharmiq_ingestion_pages_processed_total",
    "PDF pages processed during ingestion",
)

INGESTION_SYNC_SCANNED = Gauge(
    "dharmiq_ingestion_sync_scanned",
    "Documents scanned in last corpus sync",
)

INGESTION_SYNC_CREATED = Gauge(
    "dharmiq_ingestion_sync_created",
    "Documents created in last corpus sync",
)

INGESTION_SYNC_UPDATED = Gauge(
    "dharmiq_ingestion_sync_updated",
    "Documents updated in last corpus sync",
)

INGESTION_SYNC_SKIPPED = Gauge(
    "dharmiq_ingestion_sync_skipped",
    "Documents skipped in last corpus sync",
)

INGESTION_LAST_FAILURE_REASON = Gauge(
    "dharmiq_ingestion_last_failure",
    "Set to 1 when the last ingestion failure reason is recorded",
    ["reason"],
)

# Eval metrics
EVAL_RUNS_TOTAL = Counter(
    "dharmiq_eval_runs_total",
    "Total eval runs completed",
    ["dataset"],
)

EVAL_ANSWER_CORRECTNESS = Gauge(
    "dharmiq_eval_answer_correctness",
    "Average answer correctness from the latest eval run",
    ["dataset", "metric"],
)
