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
    ingestion/     # (M4) PDF pipeline
    llm/           # OpenRouter client, embeddings, retrieval
    eval/          # (M8) Evaluation
    observability/ # (M8) Metrics
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
