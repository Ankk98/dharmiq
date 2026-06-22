# Dharmiq

[![Status: Alpha](https://img.shields.io/badge/status-alpha-orange)](https://dharmiq.in)
[![Version](https://img.shields.io/badge/version-0.4-blue)](https://github.com/Ankk98/dharmiq)
[![Landing](https://img.shields.io/badge/landing-dharmiq.in-2563eb)](https://dharmiq.in)
[![App](https://img.shields.io/badge/app-app.dharmiq.in-2563eb)](https://app.dharmiq.in)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Open-source Indian legal information assistant for citizens. Dharmiq explains rights and obligations in plain language, grounded in statutory documents (IndiaCode corpus), with citations and clear disclaimers that it does not provide legal advice.

**Alpha (v0.4)** — Ashoka design system on the v0.2 agentic chat stack: app shell, document panel, clarifier cards, streamed answers with citations, privacy/export, feedback, cost caps, and one-command Docker deploy. [Landing page](https://dharmiq.in) · [App](https://app.dharmiq.in)

![Dharmiq chat UI (v0.1 screenshot; v0.3 restyles the shell, progress, and answer surfaces)](screenshots/ui-v0.1-without-dataset.png)

## Design philosophy

Dharmiq is opinionated by design. We make deliberate tradeoffs that make it
excellent at one thing — a grounded, trustworthy, Indian-citizen-first legal
assistant — rather than mediocre at everything. These tradeoffs are our moat: by
optimizing hard for trust over speed, breadth, and cost, Dharmiq aims to be a
reliable source of information and be helpful where generic chatbots can't be.

The working set of principles, rationale, anti-goals, and tie-breaker guidance
lives in [`docs/principles.md`](docs/principles.md). It is an initial statement of
direction for product and engineering decisions, not final doctrine.

## Features

### v0.3 (current)

- **Ashoka design system** – calm navy + India-green accent; Inter, Fraunces, Geist Mono, and Noto Sans Devanagari; light/dark theme toggle; aurora wallpaper
- **App shell** – sidebar navigation (Chat, Documents, Settings), mobile app bar + tab bar, resizable document panel beside chat
- **Documents library** – `/documents` page with dropzone, upload pipeline UI, and attach-to-chat toggles
- **Settings** – theme and progress-view preferences (concise ↔ detailed); debug progress gated to superusers
- **Chat UX** – clarify card with structured follow-up chips, refusal/disclaimer states, streaming caret, Law vs Your document citation styling
- **Auth screens** – aurora-backed login and signup matching the design demo
- **Message editing** – edit a user message in-thread and re-run the agent pipeline from that point
- **Session management** – delete chat sessions from the sidebar

Visual authority: [`docs/design/dharmiq-design-demo.html`](docs/design/dharmiq-design-demo.html). Implementation plan: [`docs/plans/v0.3.md`](docs/plans/v0.3.md).

### v0.2 foundation

- **LangGraph agent pipeline** – async Celery jobs with clarifier, hybrid retrieval, answerer, citation enricher, and validator (correctness over latency)
- **Live progress** – Perplexity-style step updates via SSE; concise and detailed view tiers (debug for superusers)
- **Streamed answers** – validated answer replayed token-by-token after the validator passes; heavy inline citations and statutory blockquotes
- **Hybrid retrieval** – pgvector + BM25 (RRF merge) with local cross-encoder reranking
- **Session attachments** – upload to a personal library, then explicitly attach files to a chat for focused retrieval
- **Extended uploads** – PDF, images, DOCX, and Markdown in addition to v0.1 formats
- **Input guardrails** – rate limits, message length caps, and off-topic / prompt-injection heuristics
- **LiteLLM gateway** – unified chat model routing (DeepSeek V4 flash/pro via OpenRouter)

### v0.1 foundation

- **RAG chat** – multi-agent pipeline over indexed legal PDFs
- **Corpus ingestion** – daily scan, parse, chunk, embed pipeline for IndiaCode PDFs
- **Citations** – answers link back to source documents in the UI
- **Evaluation** – Ragas + LLM-judge scoring on curated Q&A datasets
- **Observability** – Prometheus metrics and Grafana dashboards

MVP scope covers fundamental rights, consumer issues, and employment (see [`docs/plans/prd.md`](docs/plans/prd.md)). v0.2 agent architecture is in [`docs/plans/v0.2-prd-trd.md`](docs/plans/v0.2-prd-trd.md); v0.3 design system in [`docs/plans/v0.3.md`](docs/plans/v0.3.md).

## Repository layout

```text
dharmiq/
  backend/          # FastAPI app, Celery workers, LangGraph agents, RAG pipeline
  frontend/         # React + assistant-ui chat client (SSE streaming, progress UI)
  config/           # Environment YAML (dev, beta) + Grafana/Prometheus
  docs/             # PRD, TRD, deployment, design system, v0.2/v0.3 plans
  data/             # Local corpus, uploads, eval data (gitignored)
  docker-compose.yml
  docker-compose.dev.yml
  docker-compose.prod.yml
```

| Path | Description |
|------|-------------|
| [`docs/principles.md`](docs/principles.md) | Design principles — product taste, tradeoffs, anti-goals (work in progress) |
| [`docs/design/README.md`](docs/design/README.md) | Ashoka design system — tokens, components, demo HTML |
| [`backend/README.md`](backend/README.md) | API setup, endpoints, agents, ingestion, eval, metrics |
| [`frontend/README.md`](frontend/README.md) | Vite dev server, Ashoka UI, streaming chat, attachments |
| [`docs/plans/prd.md`](docs/plans/prd.md) | v0.1 product requirements |
| [`docs/plans/trd.md`](docs/plans/trd.md) | v0.1 technical design |
| [`docs/plans/plan.md`](docs/plans/plan.md) | v0.1 implementation milestones |
| [`docs/plans/v0.2-prd-trd.md`](docs/plans/v0.2-prd-trd.md) | v0.2 PRD & TRD (implemented) |
| [`docs/plans/v0.2-implementation-phases.md`](docs/plans/v0.2-implementation-phases.md) | v0.2 phase playbook (completed) |
| [`docs/plans/v0.3.md`](docs/plans/v0.3.md) | v0.3 design system implementation plan (implemented) |
| [`docs/plans/v0.4/prd.md`](docs/plans/v0.4/prd.md) | v0.4 product requirements (reliability & ops) |
| [`docs/plans/v0.4/trd.md`](docs/plans/v0.4/trd.md) | v0.4 technical design |
| [`docs/plans/roadmap.md`](docs/plans/roadmap.md) | v0.4+ product roadmap (accuracy → reliability → breadth → monetization) |
| [`docs/deployment.md`](docs/deployment.md) | Production deployment on Ubuntu + Nginx, Docker stacks |

## Prerequisites

- [Docker](https://docs.docker.com/) – Postgres, Redis, Prometheus, Grafana
- [uv](https://docs.astral.sh/uv/) – Python backend
- [nvm](https://github.com/nvm-sh/nvm) – Node.js (see `.nvmrc`)
- [OpenRouter](https://openrouter.ai/) API key – chat and eval LLM calls

## Quick start

Choose **host** (uv + npm, best for day-to-day development) or **Docker** (full stack in containers).

### Option A — Host (contributors)

#### 1. Infrastructure

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY in .env
# Agent graph is enabled by default; set DHARMIQ_AGENT_GRAPH_V2=false to fall back to v0.1 sync chat

docker compose up -d
```

Starts Postgres, Redis, Redis Commander, Flower, Prometheus, and Grafana. See [Monitoring & observability](#monitoring--observability) for URLs.

#### 2. Backend

```bash
cd backend
uv sync --dev
uv run alembic upgrade head
mkdir -p ../data/corpus/india_code/raw ../data/eval/datasets ../data/eval/runs

# One-time LangGraph checkpoint tables (idempotent; safe to re-run)
uv run python -c "
import asyncio
from dharmiq.agents.checkpoint import get_checkpointer, close_checkpointer
async def main():
    await get_checkpointer()
    await close_checkpointer()
asyncio.run(main())
"

uv run dharmiq-api
```

In another terminal (from `backend/`):

```bash
uv run celery -A celery_app worker --loglevel=info
```

With the agent graph enabled (default), chat messages are processed asynchronously by Celery. The API returns `202 Accepted` with a `chat_request_id`; the frontend subscribes to `GET /api/chat/requests/{id}/stream` for progress and the final answer.

#### 3. Frontend

```bash
nvm install && nvm use
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The frontend proxies `/api` to the backend on port 8000.

### Option B — Docker (full stack)

Runs API, Celery worker + beat, frontend, Postgres, and Redis in containers. Corpus, uploads, and eval data bind-mount from `./data/` in dev.

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY in .env

docker compose -f docker-compose.dev.yml up --build
```

| Service | URL |
|---------|-----|
| App (Vite) | http://localhost:5173 |
| API | http://localhost:8000 |
| API health | http://localhost:8000/api/health |

Edit `backend/` or `frontend/` on the host — API reloads and Vite HMR apply inside the containers.

**Production-like stack** (built images, Nginx on port 80, named volumes):

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
curl -s http://localhost/api/health
```

Optional observability profile: append `--profile observability` to either compose command. See [`docs/deployment.md`](docs/deployment.md#18-docker-deployment) for volumes, TLS, and smoke-test checklist.

**Infra only** (Postgres, Redis, Prometheus, Grafana — API/Celery on host):

```bash
docker compose up -d
```

## Monitoring & observability

After `docker compose up -d` and starting the API + Celery worker, these local URLs are available:

### Application

| Service | URL | Notes |
|---------|-----|-------|
| App (frontend) | http://localhost:5173 | Vite dev server |
| API | http://localhost:8000 | FastAPI |
| API health | http://localhost:8000/api/health | DB + Redis check |
| API liveness | http://localhost:8000/api/health/live | Lightweight probe |
| Prometheus metrics | http://localhost:8000/metrics | Scraped by Prometheus below |

### Infrastructure (Docker Compose)

| Service | URL | Notes |
|---------|-----|-------|
| PostgreSQL | `localhost:5433` | No web UI; `psql -h localhost -p 5433 -U dharmiq -d dharmiq` |
| Redis | `localhost:6379` | No web UI; `redis-cli -p 6379 ping` |
| **Redis Commander** | http://localhost:8081 | Browse keys — Celery queue `celery`, SSE seq `chat:req:{id}:seq` |
| **Flower** | http://localhost:5555 | Celery workers, active/completed/failed tasks |
| **Prometheus** | http://localhost:9090 | Metrics store; check targets at http://localhost:9090/targets |
| **Grafana** | http://localhost:3000 | Login `admin` / `admin` → **Dashboards → Dharmiq → Dharmiq Overview** |

**Grafana** needs the API running on port 8000 so Prometheus can scrape `host.docker.internal:8000/metrics`. **Flower** shows workers once `uv run celery -A celery_app worker` is running on the host (same Redis broker as Docker).

Start observability only:

```bash
docker compose up -d prometheus grafana redis-commander flower
```

Production monitoring (SSH tunnel, no public exposure) is described in [`docs/deployment.md`](docs/deployment.md#12-observability-optional).

## Configuration

Non-secret settings live in `config/config.dev.yaml` (local) and `config/config.beta.yaml` (deployment). Secrets go in `.env`:

| Variable | Description |
|----------|-------------|
| `DHARMIQ_ENV` | Config profile (`dev`, `beta`) |
| `DHARMIQ_DATABASE_PASSWORD` | Postgres password (default: `dharmiq`) |
| `DHARMIQ_JWT_SECRET` | JWT signing secret |
| `OPENROUTER_API_KEY` | Required for chat and eval |
| `DHARMIQ_AGENT_GRAPH_V2` | Set `false` to disable the LangGraph pipeline and use v0.1 sync chat (enabled by default) |
| `DHARMIQ_DEBUG_PROGRESS` | Set `true` with a superuser account to expose debug progress events |

Local Postgres is exposed on **port 5433** via Docker Compose.

## Data & ingestion

Legal PDFs go under `data/corpus/india_code/raw/`. After adding files:

```bash
cd backend
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
```

User uploads (PDF, DOCX, Markdown, images) are stored under `data/uploads/{user_id}/`. Attach files to a chat session before retrieval uses them. The `data/` directory is gitignored.

## Evaluation

See [`backend/dharmiq/eval/dataset_format.md`](backend/dharmiq/eval/dataset_format.md). Requires an indexed corpus:

```bash
cd backend
uv run dharmiq-eval --dataset v1_fundamental_rights
```

v0.2 extends the eval dataset with citation count, blockquote, and refusal expectations. See [`docs/plans/v02-eval-baseline.md`](docs/plans/v02-eval-baseline.md) for baseline vs target metrics.

## Development

```bash
# Backend tests
cd backend && uv run pytest -m "not slow"

# Backend lint
cd backend && uv run ruff check .

# Frontend lint
cd frontend && npm run lint
```

## Architecture (high level)

```text
┌─────────────┐   REST/JWT + SSE   ┌──────────────────────────────────────────┐
│  Frontend   │ ─────────────────► │  FastAPI (auth, chat, uploads, stream)   │
│  (React)    │                      │  LangGraph agents + pgvector/BM25 RAG    │
└─────────────┘                      └───────────────┬──────────────────────────┘
                                                    │
                    ┌───────────────────────────────┼─────────────────────────┐
                    ▼                               ▼                         ▼
              PostgreSQL                        Redis                     OpenRouter
         (+ pgvector, langgraph)           (Celery + SSE seq)            (LLM via LiteLLM)
                    ▲
                    │ Celery workers: agent graph, ingestion, eval
                    └────────────────────────────────────────────────────────────
```

v0.1 synchronous chat (`POST /api/chat`) remains available when `agent_graph.enabled` is false.

## Disclaimer

Dharmiq provides general legal **information**, not legal advice. Users should consult a qualified lawyer for decisions that matter to them.

## License

[MIT](LICENSE)
