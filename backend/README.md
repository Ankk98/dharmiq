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

Secrets are provided via environment variables:

| Variable | Description |
|----------|-------------|
| `DHARMIQ_DATABASE_PASSWORD` | Postgres password |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `DHARMIQ_ROOT` | Repo root path (auto-detected if unset) |

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Full health check (DB + Redis) |
| GET | `/api/health/live` | Liveness probe |

## Project layout

```
backend/
  dharmiq/
    api/           # FastAPI routes
    config/        # Settings loader
    core/          # Logging, errors
    db/            # SQLAlchemy + models
    tasks/         # Celery tasks
    ingestion/     # (M4) PDF pipeline
    llm/           # (M3+) LLM agents
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
