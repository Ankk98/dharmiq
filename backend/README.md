# Dharmiq Backend

Python 3.12 backend for the Dharmiq legal information assistant.

See the [repo README](../README.md) for full-stack setup. For the React chat UI, see [`../frontend/README.md`](../frontend/README.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python environment management
- Docker (recommended) for Postgres, Redis, Prometheus, and Grafana
- [Tesseract](https://github.com/tesseract-ocr/tesseract) (optional) for OCR fallback on scanned PDFs

## Quick start

```bash
# From repo root – start infrastructure
docker compose up -d

# Set up environment
cp .env.example .env
# Edit .env: set OPENROUTER_API_KEY (agent graph is enabled by default)

# Install dependencies and create venv
cd backend
uv sync --dev

# Run database migrations (001–010)
uv run alembic upgrade head

# LangGraph checkpoint tables (not managed by Alembic; idempotent)
uv run python -c "
import asyncio
from dharmiq.agents.checkpoint import get_checkpointer, close_checkpointer
async def main():
    await get_checkpointer()
    await close_checkpointer()
asyncio.run(main())
"

# Create local data directories (gitignored)
mkdir -p ../data/corpus/india_code/raw ../data/eval/datasets ../data/eval/runs

# Start API server
uv run dharmiq-api
# or: uv run uvicorn dharmiq.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (required for async chat with the agent graph)
uv run celery -A celery_app worker --loglevel=info

# Optional: daily corpus sync scheduler
uv run celery -A celery_app beat --loglevel=info
```

Local Postgres listens on **port 5433** (see `config/config.dev.yaml`).

Pytest uses a separate database (`dharmiq_test`, see `config/config.test.yaml`) so running tests does not wipe dev chat history. The test database is created and migrated automatically on first `uv run pytest`.

## Docker Compose services

| Service | Port | Purpose |
|---------|------|---------|
| `postgres` | 5433 | PostgreSQL 16 + pgvector |
| `redis` | 6379 | Celery broker + SSE pub/sub |
| `redis-commander` | 8081 | Redis browser UI |
| `flower` | 5555 | Celery worker / task monitor |
| `prometheus` | 9090 | Metrics scraper |
| `grafana` | 3000 | Dashboards (admin / admin) |

All infra including Redis Commander and Flower:

```bash
docker compose up -d
```

Observability only:

```bash
docker compose up -d prometheus grafana
```

## Configuration

Environment-specific YAML files live in `config/` at the repo root:

- `config.dev.yaml` – local development (`agent_graph.enabled: true` by default; set `DHARMIQ_AGENT_GRAPH_V2=false` for v0.1 sync chat)
- `config.beta.yaml` – beta deployment (`agent_graph.enabled: true` by default)

Select the active config with `DHARMIQ_ENV` (default: `dev`).

Secrets can live in a repo-root `.env` file (auto-loaded) or be exported in your shell:

| Variable | Description |
|----------|-------------|
| `DHARMIQ_ENV` | Config profile (`dev`, `beta`) |
| `DHARMIQ_DATABASE_PASSWORD` | Postgres password |
| `DHARMIQ_JWT_SECRET` | JWT signing secret (use a strong random value in production) |
| `OPENROUTER_API_KEY` | OpenRouter API key (required for chat and eval) |
| `DHARMIQ_ROOT` | Repo root path (auto-detected if unset) |
| `DHARMIQ_AGENT_GRAPH_V2` | Set `false` to disable the LangGraph pipeline (enabled by default) |
| `DHARMIQ_DEBUG_PROGRESS` | Enable debug-tier progress events (with superuser) |

## API endpoints

### Health & metrics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Full health check (DB + Redis) |
| GET | `/api/health/live` | Liveness probe |
| GET | `/metrics` | Prometheus metrics export |

### Auth (JWT)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register with email + password |
| POST | `/api/auth/jwt/login` | Login (form: `username`, `password`) → JWT |
| POST | `/api/auth/jwt/logout` | Logout |
| GET | `/api/users/me` | Current user profile |

### Chat (authenticated)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat/sessions` | Create a chat session |
| GET | `/api/chat/sessions` | List user's sessions |
| GET | `/api/chat/sessions/{id}` | Get a session |
| DELETE | `/api/chat/sessions/{id}` | Delete a session |
| POST | `/api/chat/sessions/{id}/messages` | Send a message (agent graph: `202` + async `chat_request_id`; v0.1: sync append) |
| PATCH | `/api/chat/sessions/{id}/messages/{message_id}` | Edit a user message and re-run the agent pipeline |
| POST | `/api/chat/sessions/{id}/messages/{message_id}/retry` | Retry a failed request |
| GET | `/api/chat/sessions/{id}/messages` | List messages in a session |
| POST | `/api/chat` | Run pipeline synchronously (v0.1 or v0.2 depending on flag) |
| GET | `/api/chat/requests/{id}` | Poll chat request status |
| GET | `/api/chat/requests/{id}/stream` | SSE stream: progress steps, answer tokens, citations |
| GET | `/api/chat/requests/{id}/events` | Poll progress events (reconnect fallback) |

### Chat attachments (authenticated, v0.2)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chat/sessions/{id}/attachments` | List uploads attached to a session |
| POST | `/api/chat/sessions/{id}/attachments` | Attach library uploads to a session |
| DELETE | `/api/chat/sessions/{id}/attachments/{upload_id}` | Detach an upload |

### Documents (authenticated)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/docs/{id}?source_type=corpus\|upload` | Document metadata for citations |
| GET | `/api/docs/{id}/file?source_type=corpus\|upload` | Download/view source PDF or image |

### Uploads (authenticated)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/uploads` | Upload PDF, DOCX, Markdown, or image (max 100 MB, 30 assets per user) |
| GET | `/api/uploads` | List active uploads |
| GET | `/api/uploads/{id}` | Get upload metadata |
| DELETE | `/api/uploads/{id}` | Soft-delete an upload |

## Chat pipeline

### v0.2 (LangGraph, `agent_graph.enabled`)

When enabled, `POST /api/chat/sessions/{id}/messages` enqueues a Celery task and returns `202 Accepted` with `chat_request_id`. The client subscribes to `/api/chat/requests/{id}/stream` for:

- **Progress events** – step start/end in concise or detailed tiers (debug gated server-side)
- **Answer stream** – validated answer replayed token-by-token (no second LLM call)
- **Citations** – inline citation payloads for the UI

Graph nodes (`dharmiq/agents/nodes/`):

1. **Input guard** – rate limits, length caps, off-topic / injection heuristics
2. **Clarifier** – up to 3 rounds of follow-up questions with structured `followup_items` (why line + quick-reply chips); END-and-return; new request per round
3. **Query rewriter** – statute-oriented search queries
4. **Retrieval** – hybrid pgvector + BM25 (RRF) with cross-encoder reranking
5. **Answerer** – comprehensive grounded draft with citations and blockquotes
6. **Citation enricher** – normalizes citation metadata for the UI
7. **Validator** – checks faithfulness and quote fuzzy-match; blocks release on failure
8. **Finalizer** – replays validated answer as SSE token stream
9. **Refusal** – structured response when retrieval is insufficient

State is checkpointed in Postgres (`langgraph` schema). Event `seq` values use Redis `INCR` for race-safe ordering.

### v0.1 (linear pipeline, flag off)

`POST /api/chat` runs a synchronous multi-agent LangChain flow:

1. **Clarifier** – asks follow-up questions if the query is underspecified
2. **Query rewriter** – generates statute-oriented search queries
3. **Retrieval** – pgvector search over corpus + user uploads
4. **Answerer** – grounded answer with citations
5. **Validator** – checks faithfulness; may regenerate up to 3 times

Prompts live in `dharmiq/llm/prompts/*.yaml`. Request tracking uses the `chat_requests` table.

## User uploads

Files are stored under `data/uploads/{user_uuid}/raw/`. Supported types: **PDF**, **DOCX**, **Markdown**, and images (JPEG, PNG, WebP, TIFF). Uploading enqueues `dharmiq.ingestion.process_user_upload`.

Uploads land in the user's library. For v0.2 retrieval, files must be **explicitly attached** to the chat session via `/api/chat/sessions/{id}/attachments`.

```yaml
uploads:
  uploads_dir: data/uploads
  max_assets_per_user: 30
  max_size_bytes: 104857600
```

## Corpus ingestion

Place IndiaCode PDFs under `data/corpus/india_code/raw/` (or configure `ingestion.corpus_dir` in `config/*.yaml`). An optional `manifest.json` can supply metadata:

```json
[
  {
    "file": "constitution.pdf",
    "source_id": "IN-CONSTITUTION-1950",
    "title": "Constitution of India",
    "doc_type": "act",
    "jurisdiction": "central"
  }
]
```

Celery tasks:

| Task | Description |
|------|-------------|
| `dharmiq.ingestion.sync_india_code_pdfs` | Scan corpus dir, register new/changed PDFs, enqueue processing |
| `dharmiq.ingestion.process_pdf` | Parse, chunk, embed, and index a single corpus document |
| `dharmiq.ingestion.process_user_upload` | Parse, chunk, embed, and index a user upload |

Trigger a manual sync:

```bash
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
```

v0.2 uses parent-child chunking with `context_text` for reranker input. Pipeline modules: `dharmiq.ingestion.scanner`, `parser`, `ocr`, `chunker`, `parsers/docx`, `parsers/markdown`.

Corpus tables (`source_documents`, `document_sections`, `document_chunks`) are created by migration `003`; v0.2 retrieval columns in `008`.

## LLM & retrieval

Configured in `config/*.yaml`:

```yaml
llm:
  roles:
    primary: openrouter/deepseek/deepseek-v4-pro    # answerer
    fast: openrouter/deepseek/deepseek-v4-flash       # aux agents
    embedding: local                                  # fixed 384-dim for v0.2
  agents:
    validator:
      model: openrouter/deepseek/deepseek-v4-pro
      reasoning: { enabled: true }
  rerank:
    backend: local
    local_model: BAAI/bge-reranker-base

embeddings:
  backend: local
  local_model_name: sentence-transformers/all-MiniLM-L6-v2
  local_dimensions: 384

retrieval:
  top_k: 5
  vector_top_k: 30
  bm25_top_k: 30
  rrf_k: 60
  rerank_top_k: 8
  min_rerank_score: 0.35
  min_relevant_chunks: 2
```

- **`dharmiq.llm.litellm_service`** – LiteLLM wrapper for chat and remote rerank
- **`dharmiq.llm.embeddings`** – local CPU (`sentence-transformers`) embeddings (384-dim, not swappable without re-embed)
- **`dharmiq.retrieval.hybrid`** – pgvector + BM25 with reciprocal rank fusion
- **`dharmiq.retrieval.reranker`** – local CrossEncoder (default) or LiteLLM remote rerank

## Evaluation

Curated eval datasets are JSONL files under `data/eval/datasets/` (committed to the repo). See `dharmiq/eval/dataset_format.md` for the schema. The sample dataset `v1_fundamental_rights.jsonl` includes citation count, blockquote, and refusal expectations for v0.2.

**Requires an indexed corpus** before running; the CLI fails fast if `document_chunks` is empty.

```bash
# 1. Ingest PDFs first (see Corpus ingestion)
# 2. Run eval
uv run dharmiq-eval --dataset v1_fundamental_rights
```

Or enqueue via Celery:

```bash
uv run celery -A celery_app call dharmiq.eval.run_dataset --args='["v1_fundamental_rights"]'
```

Results are stored in `eval_runs` / `eval_results` (migration `006`) and written to `data/eval/runs/`.

Metrics computed per question:

- **Ragas**: faithfulness, answer_correctness
- **LLM judge** (OpenRouter): semantic answer correctness, citation correctness
- **v0.2**: citation count met, blockquote met, refusal correct

See [`docs/plans/v02-eval-baseline.md`](../docs/plans/v02-eval-baseline.md) for v0.1 baseline vs v0.2 targets.

## Observability

The API exposes Prometheus metrics at `GET /metrics`:

- HTTP request counts, latency histograms, 5xx errors
- LLM token usage by model and agent
- Ingestion counters (documents processed/failed, chunks, sync stats)
- Eval run scores

### Grafana dashboard

1. Start the stack: `docker compose up -d prometheus grafana`
2. Run the API on port 8000: `uv run dharmiq-api`
3. Open http://localhost:3000 (login: **admin** / **admin**)
4. Go to **Dashboards → Dharmiq → Dharmiq Overview**

Prometheus UI: http://localhost:9090 — check **Status → Targets** to confirm `dharmiq-api` is UP (scrapes `host.docker.internal:8000/metrics`).

Generate traffic (health checks, chat, ingestion) so panels have data.

## Project layout

```
backend/
  dharmiq/
    agents/        # LangGraph graph, nodes, checkpoint, streaming, progress
    api/           # FastAPI routes (chat, stream, attachments)
    auth/          # fastapi-users integration
    config/        # Settings loader
    core/          # Logging, errors
    db/            # SQLAlchemy + models
    eval/          # Dataset loader, RAG eval runner, LLM judge
    guardrails/    # Input validator, rate limiter
    ingestion/     # PDF/DOCX/MD scan, parse, chunk, embed pipeline
    llm/           # LiteLLM service, legacy agents, prompts
    observability/ # Prometheus metrics and HTTP middleware
    retrieval/     # Hybrid search, reranker
    tasks/         # Celery tasks (agent graph, ingestion, eval)
    uploads/       # Session attachment helpers
  alembic/         # Database migrations (001–010)
  celery_app.py    # Celery CLI entry point
```

## Development

```bash
# Run tests (skips slow local model download by default)
uv run pytest -m "not slow"

# Include sentence-transformers round-trip
uv run pytest -m slow

# Lint
uv run ruff check .
```

Key v0.2 test modules: `test_agent_graph.py`, `test_chat_stream.py`, `test_hybrid_retrieval.py`, `test_session_attachments.py`, `test_v02_e2e_smoke.py`.
