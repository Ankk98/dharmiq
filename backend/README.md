# Dharmiq Backend

Python 3.12 backend for the Dharmiq legal information assistant.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python environment management
- Docker (optional, for local Postgres + Redis)

## Quick start

```bash
# From repo root – start infrastructure
docker compose up -d

# Set up environment
cp .env.example .env

# Install dependencies and create venv
cd backend
uv sync --dev

# Run database migrations
uv run alembic upgrade head

# Start API server
uv run dharmiq-api
# or: uv run uvicorn dharmiq.main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (separate terminal)
uv run celery -A celery_app worker --loglevel=info
```

## Configuration

Environment-specific YAML files live in `config/` at the repo root:

- `config.dev.yaml` – local development
- `config.beta.yaml` – beta deployment

Select the active config with `DHARMIQ_ENV` (default: `dev`).

Secrets can live in a repo-root `.env` file (auto-loaded) or be exported in your shell:

| Variable | Description |
|----------|-------------|
| `DHARMIQ_DATABASE_PASSWORD` | Postgres password |
| `DHARMIQ_JWT_SECRET` | JWT signing secret (use a strong random value in production) |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `DHARMIQ_ROOT` | Repo root path (auto-detected if unset) |

## API endpoints

### Health

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
| POST | `/api/chat/sessions/{id}/messages` | Append a message |
| GET | `/api/chat/sessions/{id}/messages` | List messages in a session |

### Uploads (authenticated)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/uploads` | Upload a PDF or image (max 100 MB, 30 assets per user) |
| GET | `/api/uploads` | List active uploads |
| GET | `/api/uploads/{id}` | Get upload metadata |
| DELETE | `/api/uploads/{id}` | Soft-delete an upload |

## User uploads (Milestone 5)

Files are stored under `data/uploads/{user_uuid}/raw/`. Supported types: PDF and images (JPEG, PNG, WebP, TIFF). Uploading enqueues `dharmiq.ingestion.process_user_upload`.

```yaml
uploads:
  uploads_dir: data/uploads
  max_assets_per_user: 30
  max_size_bytes: 104857600
```

## Corpus ingestion (Milestone 4)

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

Start worker and beat scheduler:

```bash
uv run celery -A celery_app worker --loglevel=info
uv run celery -A celery_app beat --loglevel=info
```

System dependency for OCR fallback: `tesseract-ocr` (optional if PDFs have extractable text).

Pipeline modules: `dharmiq.ingestion.scanner`, `parser`, `ocr`, `chunker`, `pipeline`.

## LLM & retrieval (Milestone 3)

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
```

- **`dharmiq.llm.openrouter_client`** – async OpenRouter wrapper (chat + embeddings) with retries
- **`dharmiq.llm.embeddings`** – local CPU (`sentence-transformers`) or remote OpenRouter embeddings
- **`dharmiq.llm.retrieval`** – pgvector cosine search over `document_chunks`

Corpus tables (`source_documents`, `document_sections`, `document_chunks`) are created by migration `003`. Ingestion populates them in Milestone 4.

## Evaluation (Milestone 8)

Curated eval datasets live in `data/eval/datasets/` as JSONL files. See
`dharmiq/eval/dataset_format.md` for the schema.

Run an eval manually (requires `OPENROUTER_API_KEY` and indexed corpus for meaningful scores):

```bash
uv run dharmiq-eval --dataset v1_fundamental_rights
```

Or enqueue via Celery:

```bash
uv run celery -A celery_app call dharmiq.eval.run_dataset --args='["v1_fundamental_rights"]'
```

Results are stored in `eval_runs` / `eval_results` and written to `data/eval/runs/`.

Metrics computed per question:

- **Ragas**: faithfulness, answer_correctness
- **LLM judge** (OpenRouter): semantic answer correctness, citation correctness

## Observability (Milestone 8)

The API exposes Prometheus metrics at `GET /metrics`:

- HTTP request counts, latency histograms, 5xx errors
- LLM token usage by model and agent
- Ingestion counters (documents processed/failed, chunks, sync stats)
- Eval run scores

Start Prometheus + Grafana with Docker Compose:

```bash
docker compose up -d prometheus grafana
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin / admin) – **Dharmiq Overview** dashboard

Ensure the API is running on port 8000 so Prometheus can scrape `host.docker.internal:8000/metrics`.

Run migration after pulling:

```bash
uv run alembic upgrade head
```

Run tests (skips slow local model download by default):

```bash
uv run pytest -m "not slow"
uv run pytest -m slow   # includes sentence-transformers round-trip
```

## Project layout

```
backend/
  dharmiq/
    api/           # FastAPI routes
    config/        # Settings loader
    core/          # Logging, errors
    auth/          # fastapi-users integration
    db/            # SQLAlchemy + models
    tasks/         # Celery tasks
    ingestion/     # PDF scan, parse, chunk, embed pipeline
    llm/           # OpenRouter client, embeddings, retrieval
    eval/          # Dataset loader, RAG eval runner, LLM judge
    observability/ # Prometheus metrics and HTTP middleware
  alembic/         # Database migrations
  celery_app.py    # Celery CLI entry point
```

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check .
```
