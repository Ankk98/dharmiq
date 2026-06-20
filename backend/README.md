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
# Edit .env: set OPENROUTER_API_KEY for chat/eval

# Install dependencies and create venv
cd backend
uv sync --dev

# Run database migrations (001–006)
uv run alembic upgrade head

# Create local data directories (gitignored)
mkdir -p ../data/corpus/india_code/raw ../data/eval/datasets ../data/eval/runs

# Start API server
uv run dharmiq-api
# or: uv run uvicorn dharmiq.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (separate terminal, from backend/)
uv run celery -A celery_app worker --loglevel=info

# Optional: daily corpus sync scheduler
uv run celery -A celery_app beat --loglevel=info
```

Local Postgres listens on **port 5433** (see `config/config.dev.yaml`).

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

- `config.dev.yaml` – local development
- `config.beta.yaml` – beta deployment

Select the active config with `DHARMIQ_ENV` (default: `dev`).

Secrets can live in a repo-root `.env` file (auto-loaded) or be exported in your shell:

| Variable | Description |
|----------|-------------|
| `DHARMIQ_ENV` | Config profile (`dev`, `beta`) |
| `DHARMIQ_DATABASE_PASSWORD` | Postgres password |
| `DHARMIQ_JWT_SECRET` | JWT signing secret (use a strong random value in production) |
| `OPENROUTER_API_KEY` | OpenRouter API key (required for chat and eval) |
| `DHARMIQ_ROOT` | Repo root path (auto-detected if unset) |

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
| POST | `/api/chat/sessions/{id}/messages` | Append a message (without LLM) |
| GET | `/api/chat/sessions/{id}/messages` | List messages in a session |
| POST | `/api/chat` | Run full RAG pipeline (clarify → retrieve → answer → validate) |
| GET | `/api/chat/requests/{id}` | Poll chat request status |

### Documents (authenticated)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/docs/{id}?source_type=corpus\|upload` | Document metadata for citations |
| GET | `/api/docs/{id}/file?source_type=corpus\|upload` | Download/view source PDF or image |

### Uploads (authenticated)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/uploads` | Upload a PDF or image (max 100 MB, 30 assets per user) |
| GET | `/api/uploads` | List active uploads |
| GET | `/api/uploads/{id}` | Get upload metadata |
| DELETE | `/api/uploads/{id}` | Soft-delete an upload |

## Chat pipeline

The `/api/chat` endpoint runs a multi-agent LangChain flow:

1. **Clarifier** – asks follow-up questions if the query is underspecified
2. **Query rewriter** – generates statute-oriented search queries
3. **Retrieval** – pgvector search over corpus + user uploads
4. **Answerer** – grounded answer with citations
5. **Validator** – checks faithfulness; may regenerate up to 3 times

Prompts live in `dharmiq/llm/prompts/*.yaml`. Request tracking uses the `chat_requests` table (migration `005`).

## User uploads

Files are stored under `data/uploads/{user_uuid}/raw/`. Supported types: PDF and images (JPEG, PNG, WebP, TIFF). Uploading enqueues `dharmiq.ingestion.process_user_upload`.

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

Pipeline modules: `dharmiq.ingestion.scanner`, `parser`, `ocr`, `chunker`, `pipeline`.

Corpus tables (`source_documents`, `document_sections`, `document_chunks`) are created by migration `003`.

## LLM & retrieval

Configured in `config/*.yaml`:

```yaml
openrouter:
  base_url: https://openrouter.ai/api/v1
  default_model: deepseek/deepseek-v4-pro
  timeout_seconds: 60
  max_retries: 3

embeddings:
  backend: local          # local | remote
  local_model_name: sentence-transformers/all-MiniLM-L6-v2
  local_dimensions: 384
  remote_model_id: openai/text-embedding-3-small
  remote_dimensions: 1536

retrieval:
  top_k: 5
  multi_query_top_k: 5
```

- **`dharmiq.llm.openrouter_client`** – async OpenRouter wrapper (chat + embeddings) with retries
- **`dharmiq.llm.embeddings`** – local CPU (`sentence-transformers`) or remote OpenRouter embeddings
- **`dharmiq.llm.retrieval`** – pgvector cosine search over `document_chunks` and `user_upload_chunks`

## Evaluation

Curated eval datasets are JSONL files under `data/eval/datasets/`. See `dharmiq/eval/dataset_format.md` for the schema. A sample dataset ships locally as `v1_fundamental_rights.jsonl` (under `data/`, which is gitignored—create the directory and add questions yourself, or copy from a teammate).

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
    api/           # FastAPI routes
    auth/          # fastapi-users integration
    config/        # Settings loader
    core/          # Logging, errors
    db/            # SQLAlchemy + models
    eval/          # Dataset loader, RAG eval runner, LLM judge
    ingestion/     # PDF scan, parse, chunk, embed pipeline
    llm/           # OpenRouter client, agents, retrieval, pipeline
    observability/ # Prometheus metrics and HTTP middleware
    tasks/         # Celery tasks (ingestion, eval)
  alembic/         # Database migrations
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
