## 03 – Dharmiq MVP – Implementation Plan

### 1. Repo structure

Top-level layout:

```text
/ (repo root)
  backend/
    dharmiq/
      api/
      config/
      core/
      db/
      ingestion/
      llm/
      tasks/
      eval/
      observability/
    alembic/
    pyproject.toml
    celery_app.py
    README.md
  frontend/
    (React + assistant-ui app)
  config/
    config.dev.yaml
    config.beta.yaml
```

***

### 2. Milestones

#### Milestone 1 – Skeleton & infrastructure

- Initialize repo with Python 3.12, FastAPI, and basic project layout.  
- Add Poetry or pip-tools-based dependency management.  
- Configure:
  - FastAPI app with health check endpoint.  
  - Postgres connection and Alembic migrations.  
  - Redis and Celery basic setup.
- Implement basic logging and configuration loading from `config/*.yaml`.

#### Milestone 2 – Auth & chat scaffolding

- Integrate fastapi-users with email/password auth.  
- Define `users`, `chat_sessions`, `chat_messages` models and migrations.  
- Implement basic `/auth/*` endpoints.  
- Implement `/chat/sessions` and `/chat/messages` endpoints for creating sessions and appending messages (without LLM logic yet).

#### Milestone 3 – LLM integration & simple RAG

- Implement `openrouter_client.py` wrapper:
  - Configurable base URL, API key, default model.  
  - Timeouts and retries.
- Implement embedding backend in `embeddings.py`:
  - Local CPU model (e.g., sentence-transformers) loaded once per process.  
  - Remote embedding via OpenRouter when configured.
- Integrate pgvector with SQLAlchemy models and ensure embeddings can be stored and queried.  
- Build a minimal retrieval pipeline over empty/test data.

#### Milestone 4 – Corpus ingestion pipeline

- Implement `source_documents`, `document_sections`, `document_chunks` models.  
- Implement:
  - `scanner.py` to detect new/updated IndiaCode PDFs.  
  - `parser.py` using pypdf + pdfplumber. [github](https://github.com/py-pdf/pypdf/releases)
  - `ocr.py` using pytesseract. [github](https://github.com/madmaze/pytesseract/releases)
  - `chunker.py` for section and chunk splitting.
- Wire Celery tasks:
  - `sync_india_code_pdfs` (daily).  
  - `process_pdf(document_id)`.
- Add basic logging and metrics for ingestion.

#### Milestone 5 – User uploads

- Implement `user_uploads` and `user_upload_chunks` models.  
- Add `/uploads` API for uploading PDFs/images:
  - Validate size and count limits.  
  - Store files under user-specific directory.  
  - Enqueue `process_user_upload(upload_id)` tasks.

#### Milestone 6 – LangChain agents & chat pipeline

- Implement clarifier, query rewriter, answerer, and validator in `llm/agents/` with prompts from `llm/prompts/*.yaml`.  
- Implement retrieval integration in `llm/retrieval.py` using LangChain vector stores over pgvector.  
- Implement `/api/chat` pipeline:
  - Clarify if needed.  
  - Retrieve context.  
  - Answer.  
  - Validate + regenerate loop.
- Tie together with `chat_requests` table for tracking status.

#### Milestone 7 – Frontend integration

- Create React app in `frontend/` using assistant-ui. [github](https://github.com/keen0429/assistant-ui)
- Implement auth (login/signup) against backend.  
- Implement chat UI that:
  - Shows conversations and messages.  
  - Calls `/api/chat` and shows progress + “taking longer than expected” message.  
  - Displays citations as clickable links to `/api/docs/{id}`.

#### Milestone 8 – Evaluation & observability

- Define eval dataset format and add a small v1 dataset (5–10 Qs).  
- Implement `eval/runner.py` using ragas + LLM judge. [lawansweronline](https://lawansweronline.com/frequently-asked-legal-questions/)
- Set up metrics export and Grafana dashboard for:
  - Request latency, errors.  
  - Ingestion statistics.  
  - Token usage estimates.

***

### 3. Coding conventions & practices

- Use type hints throughout (mypy/pyright-friendly).  
- Centralize prompts in YAML files under `llm/prompts/` for easy tuning.  
- Keep all interactions with OpenRouter behind `openrouter_client.py`.  
- Use async DB and network APIs where possible to keep FastAPI event loop non-blocking. [techbuddies](https://www.techbuddies.io/2026/01/05/top-7-fastapi-asyncio-best-practices-for-non-blocking-web-apis/)
- Write unit tests for:
  - Utility functions (section parsing, chunking).  
  - LLM prompts as golden tests where feasible.  
  - Ingestion idempotence.