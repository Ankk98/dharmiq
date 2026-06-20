## 02 – Dharmiq MVP – Technical Requirements & Design (TRD)

> **Note:** This document describes the **v0.1 MVP** architecture. v0.2 technical design (LangGraph, SSE, LiteLLM, hybrid retrieval) is in [`v0.2-prd-trd.md`](./v0.2-prd-trd.md).

### 1. High-level architecture

#### 1.1 Overview

Dharmiq MVP is a single-repo, modular monolith deployed on a single Ubuntu 24 LTS VPS.

Key components:

- **FastAPI** app (Python 3.12) as the main web/API server. [zestminds](https://www.zestminds.com/blog/fastapi-requirements-setup-guide-2025/)
- **PostgreSQL** with **pgvector** for structured data and vector search.  
- **Redis** as Celery broker (and optional cache).  
- **Celery** workers for background tasks (ingestion, parsing, embedding, eval). [github](https://github.com/celery/celery/releases)
- **LangChain** for RAG orchestration and multi-agent flows. [pypi](https://pypi.org/project/langchain/)
- **OpenRouter** as the external LLM provider (DeepSeek v4 Pro as default model) for:
  - Chat agents.  
  - Query rewriting.  
  - Validator and LLM-as-judge (evals).
- **pypdf** + **pdfplumber** for PDF parsing. [pypi](https://pypi.org/project/pdfplumber/)
- **pytesseract** for OCR, with pluggable backends for docTR / PaddleOCR as future options. [github](https://github.com/mindee/doctr)
- **assistant-ui** React frontend as chat UI, talking to FastAPI via REST. [github](https://github.com/keen0429/assistant-ui)
- **Ragas** + LLM-as-judge for RAG evaluation. [lawansweronline](https://lawansweronline.com/frequently-asked-legal-questions/)
- **Grafana** + metrics exporter (Prometheus-compatible) for observability. [github](https://github.com/grafana/grafana/releases)

#### 1.2 Process layout

- **App server**
  - `uvicorn` (optionally under `gunicorn` as process manager) running the FastAPI app.  
  - Number of workers and concurrency tuned for CPU-only environment. [techbuddies](https://www.techbuddies.io/2026/01/05/top-7-fastapi-asyncio-best-practices-for-non-blocking-web-apis/)

- **Workers**
  - Celery workers running in separate processes, consuming tasks from Redis. [github](https://github.com/celery/celery)

- **Database & vector store**
  - Single Postgres instance with `pgvector` extension.  
  - All structured tables + embedding vectors in the same DB.

- **Filesystem**
  - Legal corpus PDFs (IndiaCode) and parsed artifacts stored on local disk.  
  - User uploads stored under user-specific directories.

***

### 2. Tech stack and dependencies

#### 2.1 Backend

- **Language:** Python 3.12  
- **Framework:** FastAPI (`fastapi[standard]`, ~0.135.x)  
- **ASGI server:** `uvicorn[standard]`  
- **Schema/validation:** `pydantic` v2  
- **ORM:** SQLAlchemy 2.x (async) + Alembic for migrations  
- **Auth:** fastapi-users v14.x [github](https://github.com/fastapi-users/fastapi-users)
- **Task queue:** Celery 5.6.x [github](https://github.com/celery/celery/releases)
- **Broker:** Redis 7.x  
- **DB:** PostgreSQL 15/16 with `pgvector` extension  
- **LLM orchestration:** LangChain (latest 1.x) [piwheels](https://www.piwheels.org/project/langchain/)
- **PDF parsing:**
  - pypdf 6.x for baseline text extraction. [github](https://github.com/py-pdf/benchmarks)
  - pdfplumber 0.11.x for advanced layout/table extraction where needed. [pypi](https://pypi.org/project/pdfplumber/)
- **OCR:**
  - pytesseract 0.3.x + system Tesseract, with Hindi/English language packs. [github](https://github.com/madmaze/pytesseract/releases)
  - Optional backends (docTR, PaddleOCR) to be wired via pluggable interface but not mandatory in v1. [github](https://github.com/PaddlePaddle/PaddleOCR/releases)
- **Evaluation:** ragas (latest from PyPI) + LLM-judge using OpenRouter. [lawansweronline](https://lawansweronline.com/frequently-asked-legal-questions/)
- **Logging:** standard `logging` or `structlog` with JSON formatter.  
- **Metrics:** Prometheus-compatible metrics via FastAPI middleware / exporters, with Grafana dashboards. [grafana](https://grafana.com/grafana/download)

#### 2.2 Frontend

- **Build tool:** Vite or Next.js (React/TypeScript).  
- **UI:**
  - `assistant-ui` React library as the main chat UI component. [github](https://github.com/keen0429/assistant-ui)
  - Tailwind CSS or similar utility framework for rapid layout.
- **Auth:**
  - JWT stored in memory/localStorage, attached to API requests.

#### 2.3 External services

- **OpenRouter**
  - Single global API key via `OPENROUTER_API_KEY` env var.  
  - Default chat model: `deepseek/deepseek-v4-pro`.  
  - Embedding model: configurable via config file (can be OpenRouter embedding or local CPU model).

***

### 3. Configuration & environments

#### 3.1 Configuration files

Config directory: `config/`

Environment-specific files:

- `config.dev.yaml`  
- `config.beta.yaml`  
- `config.prod.yaml` (future)

Each config contains:

- Server settings (host, port).  
- DB credentials and URLs.  
- Redis URL.  
- OpenRouter base URL and default model names.  
- Embedding settings:
  - `backend: local | remote`  
  - `local_model_name: ...`  
  - `remote_model_id: ...`
- Ingestion settings:
  - Corpus directories.  
  - Batch sizes, concurrency.
- Eval settings:
  - Path to eval datasets.

Secrets (DB passwords, OpenRouter key) are provided via environment variables and not stored in config files.

#### 3.2 Canonical filesystem layout

On the VPS, a canonical directory structure:

```text
/opt/dharmiq/
  app/                 # Repo checkout
  venv/                # Python virtualenv
  logs/
    app.log
    workers.log
  data/
    corpus/
      india_code/
        raw/           # PDFs from scraper
        parsed/        # extracted text/JSON per doc (optional)
    uploads/
      {user_uuid}/
        raw/           # uploaded PDFs/images
        parsed/        # extracted text/JSON per upload (optional)
    eval/
      datasets/        # synthetic + curated eval sets
      runs/            # eval outputs
  config/
    config.dev.yaml
    config.beta.yaml
```

***

### 4. Data model / DB schema (high-level)

#### 4.1 Users & auth

**Table: users**

- `id` (UUID, PK)  
- `email` (unique)  
- `hashed_password`  
- `created_at`  
- `updated_at`

**Table: user_sessions** (optional if using JWT only)

- `id` (UUID)  
- `user_id` (FK -> users.id)  
- `created_at`  
- `expires_at`

***

#### 4.2 Conversations & messages

**Table: chat_sessions**

- `id` (UUID, PK)  
- `user_id` (FK -> users.id)  
- `title` (nullable, auto-generated from first message)  
- `created_at`  
- `updated_at`

**Table: chat_messages**

- `id` (UUID, PK)  
- `session_id` (FK -> chat_sessions.id)  
- `user_id` (FK -> users.id)  
- `role` (enum: `user`, `assistant`, `clarifier`, `validator`)  
- `content` (text, may store markdown)  
- `metadata` (JSONB: e.g., agent name, tokens used, latency)  
- `created_at`

**Table: chat_requests** (for tracking long-running requests)

- `id` (UUID, PK)  
- `session_id`  
- `user_id`  
- `status` (enum: `pending`, `running`, `completed`, `failed`)  
- `started_at`  
- `finished_at`  
- `error_message` (nullable)  
- `llm_model` (string)  
- `total_tokens` (int)

***

#### 4.3 Corpus documents & chunks

**Table: source_documents**

- `id` (UUID, PK)  
- `source_id` (string, from IndiaCode or other system)  
- `title`  
- `doc_type` (enum: `act`, `rule`, `regulation`, `notification`, `other`)  
- `jurisdiction` (e.g., `central`, `state:KA`)  
- `enactment_date` (date, nullable)  
- `version` (int, default 1)  
- `hash` (string, content hash)  
- `file_path` (filesystem path)  
- `created_at`  
- `updated_at`  
- `indexed_at` (nullable timestamp)

**Table: document_sections** (optional but useful)

- `id` (UUID, PK)  
- `document_id` (FK -> source_documents.id)  
- `label` (e.g., `Section 3`, `3. Short title`)  
- `number` (string or numeric, flexible)  
- `start_page`  
- `end_page`  
- `created_at`

**Table: document_chunks**

- `id` (UUID, PK)  
- `document_id` (FK -> source_documents.id)  
- `section_id` (FK -> document_sections.id, nullable)  
- `chunk_index` (int)  
- `text` (text)  
- `page_start` (int)  
- `page_end` (int)  
- `embedding` (vector)  # pgvector  
- `created_at`

***

#### 4.4 User uploads

**Table: user_uploads**

- `id` (UUID, PK)  
- `user_id` (FK -> users.id)  
- `original_filename`  
- `file_path` (filesystem path)  
- `mime_type`  
- `size_bytes`  
- `hash` (content hash)  
- `created_at`  
- `deleted_at` (nullable; soft delete)

**Table: user_upload_chunks**

- `id` (UUID, PK)  
- `upload_id` (FK -> user_uploads.id)  
- `chunk_index` (int)  
- `text` (text)  
- `page_start` (int, nullable)  
- `page_end` (int, nullable)  
- `embedding` (vector)  
- `created_at`

***

#### 4.5 Evaluation

**Table: eval_datasets**

- `id` (UUID, PK)  
- `name` (e.g., `v1_fundamental_rights`)  
- `description`  
- `created_at`

**Table: eval_questions**

- `id` (UUID, PK)  
- `dataset_id` (FK -> eval_datasets.id)  
- `question` (text)  
- `expected_answer` (text or summary)  
- `expected_citations` (JSONB: list of document/section IDs)  
- `created_at`

**Table: eval_runs**

- `id` (UUID, PK)  
- `dataset_id`  
- `run_at`  
- `model` (string)  
- `metrics` (JSONB: aggregated metrics)

**Table: eval_results**

- `id` (UUID, PK)  
- `run_id` (FK -> eval_runs.id)  
- `question_id` (FK -> eval_questions.id)  
- `answer` (text)  
- `metrics` (JSONB: per-question metrics)

***

### 5. Modules and packages

Repository layout (backend):

```text
dharmiq/
  api/
    __init__.py
    dependencies.py
    routes/
      auth.py
      chat.py
      docs.py
      uploads.py
      health.py
  config/
    __init__.py
    settings.py         # Pydantic settings loader
  core/
    logging.py
    security.py         # JWT, password hashing helpers
    errors.py
  db/
    base.py             # SQLAlchemy base
    session.py          # async session management
    models/
      users.py
      chats.py
      documents.py
      uploads.py
      evals.py
  ingestion/
    scanner.py          # discover new/updated corpus PDFs
    parser.py           # PdfParserBackend implementations
    ocr.py              # OcrBackend implementations
    chunker.py          # section detection & text chunking
    pipeline.py         # orchestrates parse->chunk->embed
  llm/
    openrouter_client.py
    embeddings.py       # local vs remote embedding selection
    prompts/
      clarifier.yaml
      answerer.yaml
      validator.yaml
      query_rewriter.yaml
    agents/
      clarifier.py
      answerer.py
      validator.py
    retrieval.py        # LangChain retriever setup over pgvector
  tasks/
    __init__.py
    celery_app.py
    ingestion_tasks.py
    eval_tasks.py
  eval/
    dataset_format.md   # description of eval dataset format
    runner.py           # runs ragas + LLM judge
  observability/
    metrics.py
    tracing.py          # optional
```

Frontend:

```text
frontend/
  # React + assistant-ui project (Vite/Next.js)
```

***

### 6. LangChain agents and flows

#### 6.1 Clarifier agent

**Purpose**

- Determine whether a question needs more information.  
- Ask follow-up questions if necessary.  
- Classify topic area.

**Implementation**

- LangChain `ChatOpenAI` (wrapped for OpenRouter) with a `StructuredOutputParser` defining fields:
  - `topic`  
  - `needs_more_info`  
  - `followup_questions`  
  - `reason`

Prompt template (`llm/prompts/clarifier.yaml`):

- System message text describing triage behavior.  
- Input variables: `user_question`, `history`.

**Flow**

1. API collects user message + last N messages.  
2. Clarifier runs.  
3. If `needs_more_info` is true:
   - Store clarifier output.  
   - Send `followup_questions` back to user as assistant messages.  
   - Await user responses and then re-run clarifier or move on.

***

#### 6.2 Query rewriter & retrieval

**Purpose**

- Expand user question into multiple search-friendly queries.  
- Retrieve relevant chunks from corpus and user uploads.

**Components**

- Query rewriter chain with a small LLM call.  
- LangChain `MultiQueryRetriever` configured with:
  - VectorStore: Postgres+pgvector.  
  - A wrapper that merges corpus chunks and user-upload chunks.
- Optional `ContextualCompressionRetriever` to remove near-duplicates.

Prompt template (`llm/prompts/query_rewriter.yaml`):

- System: instructs LLM to generate 2–4 statute-oriented queries.  
- Input variables: `user_question`, `topic`, `facts`.

***

#### 6.3 Answering agent

**Purpose**

- Generate legal information answers strictly grounded in retrieved context.

**Implementation**

- LangChain `Runnable`/`LLMChain` using OpenRouter model.  
- Inputs:
  - `user_question`  
  - `facts` (clarified info)  
  - `retrieved_context` (formatted list of chunks with metadata)  
  - Optional `regeneration_instructions` from validator.

Prompt template (`llm/prompts/answerer.yaml`):

- System message describing behavior (careful lawyer-like reasoning, no advice, citations, disclaimers).  
- A section for “Legal context” where chunks are injected.  
- A section for “Regeneration instructions” if present.

**Output**

- Markdown/HTML text with inline citation markers that include document IDs and section labels.

***

#### 6.4 Validator agent

**Purpose**

- Review answer against question and context.  
- Decide whether to regenerate and what to fix.

**Implementation**

- LangChain `ChatOpenAI` with JSON structured output:
  - `must_regenerate` (bool)  
  - `issues` (list of strings)  
  - `regeneration_instructions` (string)  
  - `final_warning` (string)

Prompt template (`llm/prompts/validator.yaml`):

- System: instructs the model as senior lawyer-reviewer.  
- Inputs: `user_question`, `retrieved_context`, `draft_answer`.

**Flow**

1. After answering agent produces a draft, validator runs.  
2. If `must_regenerate` is true and retry count < 3:
   - Pass `regeneration_instructions` as input to answerer.  
   - Re-run answerer and validator.  
3. After final iteration:
   - Attach `final_warning` to the answer (if provided).

***

#### 6.5 Overall request pipeline (backend)

Pseudo-flow in `/api/chat`:

1. Authenticate user via JWT.  
2. Load chat session and history.  
3. Create a new `chat_requests` record with `status=pending`.  
4. Call clarifier agent.
   - If more info needed, respond with follow-up questions.  
5. Once enough info:
   - Update `chat_requests.status=running`.  
   - Run query rewriter.  
   - Run retriever to get top-k corpus chunks and user-upload chunks.  
6. Run answering agent (with context).  
7. Run validator; do regen loop if needed.  
8. Save messages (user, assistant) and updated `chat_requests` status.  
9. Return final answer + citations + warnings and request status.

***

### 7. Ingestion pipeline design

#### 7.1 Daily corpus sync

Trigger: Celery beat or equivalent scheduler runs `ingestion_tasks.sync_india_code_pdfs` daily.

**Steps**

1. Read configured corpus directory: `data/corpus/india_code/raw/`.  
2. For each PDF file (or from a manifest JSON produced by the scraper repo):
   - Compute content hash.  
   - Check `source_documents` for existing entry with same `source_id` and hash.  
   - If unchanged: skip.  
   - If new or changed: create/update `source_documents` row and enqueue a `process_pdf` task.

***

#### 7.2 PDF processing task

`ingestion_tasks.process_pdf(document_id)`:

1. Load PDF from `file_path`.  
2. For each page:
   - Try extracting text via `pypdf`.  
   - If text is empty/very short, treat as image and run OCR via `OcrBackend` (pytesseract by default). [piwheels](https://www.piwheels.org/project/pytesseract/)
3. Aggregate page texts.  
4. Run `chunker`:
   - Detect section headings (regex/heuristics based on common patterns in Indian statutes).  
   - Create `document_sections` rows.  
   - Split sections into chunks of ~512–1024 tokens.  
5. Use `embeddings.py` to compute embedding for each chunk:
   - Local CPU model if `backend=local` in config.  
   - OpenRouter embedding model if `backend=remote`.  
6. Insert chunks into `document_chunks` with vector values.  
7. Update `source_documents.indexed_at`.

***

#### 7.3 User upload processing

Trigger: when user uploads a PDF/image via `/api/uploads`.

**Steps**

1. Store file under `data/uploads/{user_uuid}/raw/`.  
2. Create a `user_uploads` row.  
3. Enqueue `process_user_upload(upload_id)` Celery task.  
4. Task logic is similar to corpus processing:
   - Extract pages, OCR if needed.  
   - Chunk text.  
   - Compute embeddings.  
   - Store in `user_upload_chunks`.

***

### 8. Evaluation workflow

#### 8.1 Eval dataset format

Store datasets as JSONL or YAML in `data/eval/datasets/`, e.g.:

```json
{
  "id": "q1",
  "question": "What are my rights if police arrest me without warrant?",
  "expected_answer": "High-level explanation...",
  "expected_citations": [
    {"document_id": "...", "section": "Article 22"}
  ]
}
```

#### 8.2 Running evals

- Use `eval/runner.py` to:
  - Load a dataset.  
  - For each question:
    - Run the full RAG pipeline.  
    - Compute metrics using `ragas` (answer correctness, faithfulness, context recall). [lawansweronline](https://lawansweronline.com/frequently-asked-legal-questions/)
    - Optionally call LLM-as-judge via OpenRouter for semantic correctness.
- Store results in `eval_runs` and `eval_results` tables.

***

### 9. Observability

#### 9.1 Logging

- Log structure:
  - Request ID, user ID (if any), session ID, chat_request ID.  
  - Timestamps, latency.  
  - Which agents ran, with statuses.
- In debug mode:
  - Log full prompts and responses (in files under `logs/` or separate storage).

#### 9.2 Metrics

- Expose metrics endpoint for Prometheus:
  - Request counts, latency histograms, error rates.  
  - LLM token usage (approximate) per model.  
  - Ingestion metrics: docs processed, failures.

- Grafana dashboards:
  - Chat performance.  
  - Ingestion health.  
  - Eval run history. [grafana](https://grafana.com/docs/grafana/latest/whatsnew/)

***

### 10. Long-running request UX

#### 10.1 Backend

- `/api/chat` can either:
  - Synchronously run the pipeline and return when done; or  
  - Optionally enqueue a background task and poll status.

For MVP:

- Implement synchronous chat with a server timeout (e.g., 60 seconds) but include a `chat_requests` status record.  
- If the process nears 30 seconds, include a flag in the response so the UI shows “taking longer than expected”.

#### 10.2 Frontend behavior

- Show spinner/progress when awaiting response.  
- After 30 seconds, show message: “This answer is taking longer than usual. Please wait; we’re still working on it.”  
- If request fails due to timeout, show a friendly error and allow retry. [youtube](https://www.youtube.com/watch?v=14sQh5yWDnU)

***

### 11. Notes & future considerations

- **Licensing**  
  - MVP may include libraries with stricter licenses (e.g., PyMuPDF) as optional add-ons; main pipeline keeps to permissive licenses where practical. [github](https://github.com/pymupdf/PyMuPDF/blob/main/changes.txt)
- **Non-PDF formats**  
  - DOCX/other formats explicitly deferred; schema and pipeline kept generic so that new parsers can be added later.
- **Language support**  
  - Hindi/multilingual support deferred to v2; prompts and APIs should not hardcode English assumptions.
- **Admin & rate limiting**  
  - Admin web UI and per-user rate limiting deferred to v2; DB/schema designed so that roles and quotas can be added later.

***

