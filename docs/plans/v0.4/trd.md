# Dharmiq v0.4 — Technical Requirements & Implementation Plan

**Status:** Implemented  
**Version:** 0.4  
**Parent doc:** [`prd.md`](./prd.md)  
**Baseline:** v0.3 — Ashoka UI, LangGraph agent pipeline, cosmetic upload UI, no privacy/feedback/cost persistence, infra-only Docker Compose  
**Last updated:** 2026-06-22

Related: [`roadmap.md`](../roadmap.md) · [`v0.2-implementation-phases.md`](../v0.2-implementation-phases.md) · [`deployment.md`](../../deployment.md) · [`README.md`](../../../README.md)

---

## How to use this document

1. **Read binding decisions first** (§2). They override any ambiguous wording in the PRD or this doc.
2. **One phase at a time.** Do not start phase N+1 until all smoke tests for phase N pass.
3. **Preserve v0.3 behavior** except where this TRD explicitly changes it.
4. **Match existing conventions:** async SQLAlchemy, Pydantic v2, pytest-asyncio, structlog, YAML config in `config/`, Alembic migrations in `backend/alembic/versions/`.
5. **Every phase ends with:** code + migration (if any) + tests + smoke command block.
6. **Do not commit** unless the user asks.

### Global smoke gate (run after every phase)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest -m "not slow" -q
cd frontend && npm run lint
```

### Phase dependency graph

```text
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5
                              │
                    P6 ◄──────┤
                    P7 ◄──────┘
P8 (idempotency/recovery) — after P4 (needs cost check hook) + P1 (upload recovery)
P9 (Docker) — after P0; full stack smoke after P8
```

| ID | Name | Depends on | Est. |
|----|------|------------|------|
| P0 | DB schema v0.4 | — | 1 d |
| P1 | Upload `processing_stage` pipeline + API | P0 | 2 d |
| P2 | Documents poll UI | P1 | 1 d |
| P3 | Chunk API + document panel tabs/highlight | P0 | 2 d |
| P4 | LLM cost rows + session/monthly caps | P0 | 2 d |
| P5 | Agent hygiene (clarifier, loop, step cap) | P0 | 2 d |
| P6 | Export + delete account + Settings UI | P0 | 2 d |
| P7 | Feedback API + UI | P0 | 1 d |
| P8 | Idempotency + Celery dedupe + recovery | P1, P4 | 2 d |
| P9 | Dockerfiles + compose dev/prod + docs | P0–P8 | 3 d |

---

## 1. Current codebase snapshot (v0.3)

Ground truth for implementers — verify paths before editing.

### 1.1 Backend layout

| Area | Path | v0.3 state |
|------|------|------------|
| FastAPI entry | `backend/dharmiq/main.py` | Routers: health, auth, chat, chat_stream, chat_attachments, uploads, docs, metrics |
| Chat POST | `backend/dharmiq/api/routes/chat.py` | `POST /api/chat/sessions/{id}/messages` → `202` + Celery enqueue; no `Idempotency-Key` |
| SSE stream | `backend/dharmiq/api/routes/chat_stream.py` | `GET /api/chat/requests/{id}/stream?after_seq=0` — reconnect supported |
| Uploads API | `backend/dharmiq/api/routes/uploads.py` | `indexed` computed via chunk existence query; no `processing_stage` |
| Docs API | `backend/dharmiq/api/routes/docs.py` | Metadata + file download only; **no chunk endpoints** |
| Upload pipeline | `backend/dharmiq/ingestion/upload_pipeline.py` | Single-shot `process_user_upload`; no stage writes; failures only logged |
| Ingestion task | `backend/dharmiq/tasks/ingestion_tasks.py` | `process_user_upload` Celery task |
| Chat task | `backend/dharmiq/tasks/chat_tasks.py` | `enqueue_agent_graph` always `.delay()`; `recover_pending_agent_graph_requests` on worker ready |
| Celery app | `backend/dharmiq/tasks/celery_app.py` | `worker_ready` → recover pending/running chat requests |
| Beat schedule | `backend/dharmiq/tasks/beat_schedule.py` | Daily `sync_india_code_pdfs` at 02:00 UTC |
| Agent graph | `backend/dharmiq/agents/graph.py` | `with_progress` wrapper; clarifier round cap `< 3`; **no step cap** |
| Clarifier node | `backend/dharmiq/agents/nodes/clarifier.py` | Writes `followup_items` to state; markdown fallback possible via `_parse_followup_items` |
| Clarifier LLM | `backend/dharmiq/llm/agents/clarifier.py` | Falls back from `followup_items` to `followup_questions` list |
| LiteLLM | `backend/dharmiq/llm/litellm_service.py` | `acompletion` only; **no cost persistence** |
| Token metrics | `backend/dharmiq/observability/metrics.py` | `record_llm_tokens` in-memory + Prometheus |
| User uploads model | `backend/dharmiq/db/models/uploads.py` | No `processing_stage`, `chunk_count`, `processing_error` |
| Chat requests model | `backend/dharmiq/db/models/chats.py` | No `cost_usd`, `idempotency_key` |
| Citations schema | `backend/dharmiq/schemas/citations.py` | Has `quote_start_char`, `quote_end_char` |
| Citation enricher | `backend/dharmiq/agents/citation_validation.py` | Populates span fields via `find_quote_span` |
| Settings | `backend/dharmiq/config/settings.py` | No `cost_limits`, no `beat_schedule` toggle |
| Latest migration | `backend/alembic/versions/010_system_message_role.py` | Next: `011_v04_foundation.py` |
| Version | `backend/dharmiq/__init__.py` | `0.4.0` |

### 1.2 Frontend layout

| Area | Path | v0.3 state |
|------|------|------------|
| Upload library | `frontend/src/components/uploads/UploadLibrary.tsx` | `useCosmeticPipelinePhase` timer (~1.5s per fake stage) |
| Pipeline labels | `frontend/src/lib/uploadPipeline.ts` | 4 cosmetic stages; no `Ready` / `Failed` |
| Document panel | `frontend/src/components/documents/DocumentPanel.tsx` | iframe only; “coming soon” banner |
| Panel params | `frontend/src/providers/document-panel-context.ts` | `chunkId`, `quote` (text); **no char spans** |
| Citation links | `frontend/src/lib/citations.ts` | `documentViewerPath` passes `quote` text, not spans |
| Clarifier parse | `frontend/src/lib/clarifier.ts` | **Markdown fallback** in `parseClarifierItems` |
| Settings | `frontend/src/pages/SettingsPage.tsx` | No Privacy & data card |
| Thread actions | `frontend/src/components/assistant-ui/thread.tsx` | Copy, Regenerate, Export MD — **no thumbs** |
| API client | `frontend/src/lib/api.ts` | `UserUpload.indexed` only; no export/delete/feedback/chunks |
| Citation type | `frontend/src/lib/api.ts` | Missing `quote_start_char`, `quote_end_char` |

### 1.3 Ops layout

| Area | Path | v0.3 state |
|------|------|------------|
| Compose | `docker-compose.yml` | Postgres, Redis (**no volume**), Flower, Prometheus, Grafana only |
| Dockerfiles | — | **None** |
| Env example | `.env.example` | Minimal; no Docker/cost vars |
| Deployment | `docs/deployment.md` | Host `uv` + systemd; no Docker app stack |

---

## 2. Binding decisions (implementation hardening)

These resolve PRD ambiguities. **Do not deviate** without updating this doc and the PRD.

| ID | Topic | Decision |
|----|-------|----------|
| TRD-1 | Idempotency storage | Dedicated table `idempotency_keys` (`user_id`, `key`, `body_hash`, `chat_request_id`, `expires_at`). Unique on `(user_id, key)`. TTL **24 hours**. |
| TRD-2 | Idempotency body hash | SHA-256 of canonical JSON: `{"content": "<trimmed>", "force_answer": <bool>}` with sorted keys, UTF-8. Applies to POST, retry, edit (edit hashes `{"content": "<new>", "force_answer": false}`). |
| TRD-3 | Idempotency HTTP | Duplicate key + same hash → **202** with same `chat_request_id`. Same key + different hash → **409**. Missing/invalid UUID key → ignore (treat as no key). |
| TRD-4 | Cost enforcement point | Check caps in `create_agent_graph_request`, `retry_agent_graph_request`, `edit_user_message_request` **before** DB commit of new `ChatRequest`, **before** Celery enqueue. |
| TRD-5 | Cost cap HTTP | **429** with body `{"detail": "usage_limit_reached", "limit": "conversation" \| "account_monthly"}`. Frontend shows toast and disables send. |
| TRD-6 | Cost currency & month | USD; calendar month **UTC** (`date_trunc('month', now() AT TIME ZONE 'UTC')`). |
| TRD-7 | `indexed` field compat | API continues returning `indexed: bool` = `(processing_stage == "ready")`. Never remove in v0.4. |
| TRD-8 | `processing_stage` enum | Values: `uploaded`, `parsed`, `chunking`, `embedding`, `ready`, `failed`. Postgres: `VARCHAR(32)` + CHECK constraint (no native PG enum). |
| TRD-9 | Parsed tab chunk rows | List **leaf v0.2 chunks only**: `parent_chunk_id IS NOT NULL` OR (`parent_chunk_id IS NULL` AND no child rows exist for that parent). Order by `chunk_index ASC`. Same rule for `document_chunks` (corpus) and `user_upload_chunks` (upload). |
| TRD-10 | Quote highlight | URL query params: `qstart`, `qend` (integers). Highlight **only** when `chunk` + `qstart` + `qend` all present and valid. Parsed tab only. |
| TRD-11 | LLM cost calculation | `from litellm import completion_cost`; `cost_usd = float(completion_cost(completion_response=response))` using the dict returned by `acompletion`. Store `prompt_tokens`, `completion_tokens` from `usage`. |
| TRD-12 | Cost scope | Persist cost for **all** `LiteLLMService.acompletion` calls in agent graph nodes. Embeddings/rerank: **deferred** (document in code comment). |
| TRD-13 | Celery chat dedupe | Pass `task_id=str(chat_request_id)` to `.apply_async()` / `.delay()`. Celery rejects duplicate task_id while first is queued. Also skip enqueue if request `status` is `completed`. |
| TRD-14 | Upload worker recovery | On `worker_ready`, re-enqueue `process_user_upload` for rows where `processing_stage NOT IN ('ready', 'failed')` and `deleted_at IS NULL`. |
| TRD-15 | Beat schedule v0.4 | Add `beat_schedule.enabled: bool` to config (default `false` in new `config.docker.yaml`). When `false`, `celery_app.conf.beat_schedule = {}`. Host/beta keeps `true` until v0.8. |
| TRD-16 | Clarifier hard drop | If `needs_more_info` and `followup_items` empty after **one** LLM retry → fail request with user-visible error. Remove markdown fallback in **frontend only**; backend may keep markdown `content` for export. |
| TRD-17 | Loop detection normalization | `unicodedata.normalize("NFKC", text)`, collapse `\s+` to single space, `.strip().lower()`. |
| TRD-18 | Max graph steps | Increment counter in `with_progress` each node invocation; cap **100**; on exceed → `failed` + SSE error + message: “This question took too many steps. Please simplify or start a new chat.” |
| TRD-19 | Delete account auth | `DELETE /api/account` body `{email, password}`; verify with `UserManager.authenticate`; **409** if email ≠ current user email. |
| TRD-20 | Delete account data | Hard-delete user row (CASCADE handles sessions, messages, requests, events, uploads, chunks, feedback, idempotency_keys, llm_usage_events). Delete directory `data/uploads/{user_id}/` recursively. JWT invalidated by deleting user (no extra token store). |
| TRD-21 | Export scope | JSON attachment per PRD §5.4.1; `Content-Disposition: attachment; filename="dharmiq-export-YYYY-MM-DD.json"`. |
| TRD-22 | Feedback | `rating`: `"up"` \| `"down"`; `reason` optional max 500 chars; unique `(user_id, message_id)` upsert. |
| TRD-23 | Upload poll interval | Frontend `2000` ms while `processing_stage ∉ {ready, failed}`. |
| TRD-24 | Frontend upload size | Align `UploadLibrary` `MAX_BYTES` to **104857600** (100 MiB) matching `config.*.yaml` `uploads.max_size_bytes`. |
| TRD-25 | SQLAlchemy `metadata` | Never declare ORM attribute named `metadata`. Use `message_metadata = mapped_column("metadata", ...)`. |
| TRD-26 | `docker-compose.yml` | Keep as **infra-only** alias; add comment pointing to `docker-compose.dev.yml` / `docker-compose.prod.yml`. |
| TRD-27 | Redis in Compose | Named volume `dharmiq_redis`; `command: redis-server --appendonly yes --save 60 1000`. |
| TRD-28 | Prod frontend | Nginx serves `frontend/dist/`; `proxy_read_timeout 300s`; `proxy_buffering off` for `/api/chat/requests/*/stream`. |
| TRD-29 | Dev frontend | Option A (default): Vite service on `:5173` with bind-mount `frontend/`. Option B: Nginx → Vite HMR upstream — **not required** if Option A works. |
| TRD-30 | CI eval/smoke gate | **Out of scope** v0.4 (v0.5). Phase smoke tests are manual + pytest only. |

---

## 3. Schema (P0)

### 3.1 Migration `011_v04_foundation.py`

Single migration for all v0.4 schema. Downgrade must be implemented.

#### `user_uploads` — add columns

```sql
processing_stage VARCHAR(32) NOT NULL DEFAULT 'uploaded'
  CHECK (processing_stage IN ('uploaded','parsed','chunking','embedding','ready','failed')),
chunk_count INTEGER NOT NULL DEFAULT 0,
processing_error TEXT NULL
```

Backfill existing rows:

```sql
UPDATE user_uploads u
SET processing_stage = 'ready',
    chunk_count = (SELECT COUNT(*) FROM user_upload_chunks c WHERE c.upload_id = u.id)
WHERE EXISTS (SELECT 1 FROM user_upload_chunks c WHERE c.upload_id = u.id)
  AND u.deleted_at IS NULL;

UPDATE user_uploads
SET processing_stage = 'failed', processing_error = 'Unknown (pre-v0.4)'
WHERE deleted_at IS NULL
  AND processing_stage = 'uploaded'
  AND created_at < NOW() - INTERVAL '1 hour';
```

(The 1-hour heuristic avoids marking in-flight host uploads as failed immediately after migration.)

#### `chat_requests` — add columns

```sql
cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
idempotency_key VARCHAR(64) NULL  -- denormalized copy for debugging; canonical store is idempotency_keys
```

Index: `ix_chat_requests_session_id` (exists) used for session cost rollup.

#### `llm_usage_events` — new table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK users CASCADE | |
| `chat_request_id` | UUID FK chat_requests SET NULL NULL | |
| `session_id` | UUID FK chat_sessions SET NULL NULL | denormalized for queries |
| `agent_role` | VARCHAR(64) | e.g. `clarifier`, `answerer` |
| `model` | VARCHAR(255) | resolved LiteLLM model string |
| `prompt_tokens` | INTEGER NOT NULL DEFAULT 0 | |
| `completion_tokens` | INTEGER NOT NULL DEFAULT 0 | |
| `cost_usd` | NUMERIC(12, 6) NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

Indexes: `(user_id, created_at)`, `(chat_request_id)`, `(session_id)`.

#### `message_feedback` — new table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK users CASCADE | |
| `message_id` | UUID FK chat_messages CASCADE | |
| `rating` | VARCHAR(8) CHECK IN (`up`,`down`) | |
| `reason` | VARCHAR(500) NULL | |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

Unique: `(user_id, message_id)`.

#### `idempotency_keys` — new table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK users CASCADE | |
| `key` | VARCHAR(128) | client UUID string |
| `body_hash` | VARCHAR(64) | SHA-256 hex |
| `chat_request_id` | UUID FK chat_requests CASCADE | |
| `created_at` | TIMESTAMPTZ | |
| `expires_at` | TIMESTAMPTZ | created_at + 24h |

Unique: `(user_id, key)`. Index: `(expires_at)` for optional cleanup task later.

### 3.2 SQLAlchemy models

| Model file | Changes |
|------------|---------|
| `backend/dharmiq/db/models/uploads.py` | Add `ProcessingStage` str enum; columns `processing_stage`, `chunk_count`, `processing_error` |
| `backend/dharmiq/db/models/chats.py` | Add `cost_usd` to `ChatRequest` |
| `backend/dharmiq/db/models/llm_usage.py` | **New** `LlmUsageEvent` |
| `backend/dharmiq/db/models/feedback.py` | **New** `MessageFeedback` |
| `backend/dharmiq/db/models/idempotency.py` | **New** `IdempotencyKey` |
| `backend/dharmiq/db/models/__init__.py` | Export new models |

### 3.3 Pydantic schemas

| File | Changes |
|------|---------|
| `backend/dharmiq/schemas/uploads.py` | Add `processing_stage`, `chunk_count`, `processing_error`; keep `indexed` as computed field in `_to_read` |
| `backend/dharmiq/schemas/chunks.py` | **New** `ChunkRead`, `ChunkListItem`, `ChunkListResponse` |
| `backend/dharmiq/schemas/account.py` | **New** `AccountDeleteRequest`, `AccountExportPayload` |
| `backend/dharmiq/schemas/feedback.py` | **New** `MessageFeedbackCreate`, `MessageFeedbackRead` |

### 3.4 Config

Add to `backend/dharmiq/config/settings.py`:

```python
class CostLimitsSettings(BaseModel):
    enforce: bool = True
    per_session_usd: float = 1.0
    per_account_monthly_usd: float = 10.0

class BeatScheduleSettings(BaseModel):
    enabled: bool = True  # false in docker profile

class Settings(BaseModel):
    ...
    cost_limits: CostLimitsSettings = Field(default_factory=CostLimitsSettings)
    beat_schedule: BeatScheduleSettings = Field(default_factory=BeatScheduleSettings)
```

Env overrides in `_apply_env_overrides`:

```python
if flag := os.environ.get("DHARMIQ_COST_LIMITS_ENFORCE"):
    settings_dict.setdefault("cost_limits", {})["enforce"] = flag.lower() not in {"0", "false", "no"}
```

Add to `config/config.dev.yaml` and `config/config.beta.yaml`:

```yaml
cost_limits:
  enforce: true
  per_session_usd: 1.0
  per_account_monthly_usd: 10.0

beat_schedule:
  enabled: true
```

Add `config/config.docker.yaml` (used when `DHARMIQ_ENV=docker`):

```yaml
# extends dev-like settings; database host = postgres service name, etc.
beat_schedule:
  enabled: false

cost_limits:
  enforce: true   # self-hosters set DHARMIQ_COST_LIMITS_ENFORCE=false
```

Wire `beat_schedule.py`:

```python
from dharmiq.config.settings import get_settings
settings = get_settings()
if settings.beat_schedule.enabled:
    celery_app.conf.beat_schedule = { ... existing ... }
else:
    celery_app.conf.beat_schedule = {}
```

---

## P0 — DB schema v0.4

### Goal

All v0.4 tables and columns exist; models import cleanly; migration applies on empty and v0.3 DB.

### Tasks

| # | Task | Files |
|---|------|-------|
| 0.1 | Create migration `011_v04_foundation.py` | `backend/alembic/versions/` |
| 0.2 | Add SQLAlchemy models | `backend/dharmiq/db/models/*.py` |
| 0.3 | Add Pydantic schemas (stubs OK) | `backend/dharmiq/schemas/` |
| 0.4 | Add `CostLimitsSettings`, `BeatScheduleSettings` | `settings.py`, YAML files |
| 0.5 | Test migration up/down | `backend/tests/test_migrations_v04.py` |

### Smoke tests

**Automated**

```bash
cd backend
uv run alembic upgrade head
uv run pytest tests/test_migrations_v04.py -q
```

| Test | Assert |
|------|--------|
| `test_v04_migration_upgrade` | All new columns/tables exist |
| `test_user_upload_processing_stage_default` | New upload row has `processing_stage='uploaded'` |
| `test_models_import` | No circular import from `db.models` |

**Manual**

```bash
cd backend && uv run python -c "from dharmiq.db.models import LlmUsageEvent, MessageFeedback, IdempotencyKey; print('ok')"
```

### Definition of done

- [ ] `alembic upgrade head` succeeds on fresh DB and v0.3 DB
- [ ] `pytest -m "not slow" -q` passes
- [ ] Config loads `cost_limits` and `beat_schedule`

---

## P1 — Upload `processing_stage` pipeline + API

### Goal

Backend truthfully tracks upload stages through `ready` or `failed`; API exposes fields.

### Tasks

| # | Task | Files |
|---|------|-------|
| 1.1 | Add `update_upload_stage(db, upload_id, stage, *, chunk_count=..., error=...)` helper | `backend/dharmiq/ingestion/upload_pipeline.py` |
| 1.2 | Refactor `process_user_upload` to set stages: `uploaded` (create), `parsed` (after pages), `chunking` (after chunk rows), `embedding` (before embed loop), `ready` (commit + count), `failed` (on error) | same |
| 1.3 | Update `process_user_upload_safe` to catch exceptions → `failed` + `processing_error` | same |
| 1.4 | Set `processing_stage='uploaded'` in `create_user_upload` before commit | same |
| 1.5 | Update `_to_read` / `_upload_is_indexed` → use `processing_stage == ready` (keep chunk check as assertion in tests) | `api/routes/uploads.py` |
| 1.6 | Extend `UserUploadRead` schema | `schemas/uploads.py` |
| 1.7 | Update `session_attachments._upload_is_indexed` to use `processing_stage` | `uploads/session_attachments.py` |
| 1.8 | Integration tests for stage transitions | `tests/test_upload_pipeline.py` |

### Stage transition rules

```text
create_user_upload     → uploaded
pages extracted        → parsed
chunks written (no embed yet) → chunking
embedding batch start  → embedding
commit success       → ready (chunk_count = leaf count)
any exception        → failed (processing_error = str(exc)[:2000])
```

Use `await db.commit()` after each stage update so poll API sees progress (same pattern as chunk writes).

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_upload_pipeline.py tests/test_uploads.py -q
```

| Test | Assert |
|------|--------|
| `test_upload_happy_path_stages` | Mock embedder; stages end at `ready`, `chunk_count > 0` |
| `test_upload_parse_failure` | Invalid file → `failed`, `processing_error` set |
| `test_get_upload_returns_stage` | GET `/api/uploads/{id}` includes `processing_stage` |

**Manual** (requires worker)

```bash
# Terminal 1: API + worker
cd backend && uv run dharmiq-api
cd backend && uv run celery -A celery_app worker --loglevel=info

# Upload small PDF
TOKEN=... # login
curl -s -H "Authorization: Bearer $TOKEN" -F file=@/path/to/small.pdf http://localhost:8000/api/uploads | jq .
# Poll until ready
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/uploads/{id} | jq .processing_stage,.chunk_count,.indexed
```

### Definition of done

- [ ] No code path leaves non-terminal stage forever without worker
- [ ] `indexed` === `(processing_stage == "ready")`
- [ ] Failed uploads have `processing_error` string

---

## P2 — Documents poll UI

### Goal

Replace cosmetic timer with real API polling (~2s).

### Tasks

| # | Task | Files |
|---|------|-------|
| 2.1 | Remove `useCosmeticPipelinePhase` | `UploadLibrary.tsx` |
| 2.2 | Add `getUpload(id)` to API client | `frontend/src/lib/api.ts` |
| 2.3 | Extend `UserUpload` type with `processing_stage`, `chunk_count`, `processing_error` | `api.ts` |
| 2.4 | Update `uploadPipeline.ts`: map API stage → chip states; add **Ready** / **Failed** terminal states | `uploadPipeline.ts` |
| 2.5 | Poll: `useEffect` interval 2000ms when any upload `!terminal` | `UploadLibrary.tsx` |
| 2.6 | Show `chunk_count` when `> 0`; show error snippet when `failed` | `UploadLibrary.tsx` |
| 2.7 | Update `SessionAttachments` to filter `processing_stage === 'ready'` (or `indexed`) | `SessionAttachments.tsx` |
| 2.8 | Fix `MAX_BYTES` to 104857600 | `UploadLibrary.tsx` |

### `uploadPipeline.ts` mapping

| API `processing_stage` | Chip index active |
|------------------------|-------------------|
| `uploaded` | 0 Uploaded |
| `parsed` | 1 Parsed |
| `chunking` | 2 Chunking |
| `embedding` | 3 Embedding |
| `ready` | all done + hide pipeline |
| `failed` | show error state (red chip on last reached stage) |

### Smoke tests

**Automated**

```bash
cd frontend && npm run lint
```

**Manual**

1. Open `/documents`, upload a PDF.
2. Confirm chips advance with real delays (not fixed 1.5s timer).
3. Confirm “Processing” label disappears at `ready`.
4. Upload corrupt/empty file → `failed` + error message within ~2 poll cycles.

### Definition of done

- [ ] No `setInterval` fake phase advancement
- [ ] Poll stops when all uploads terminal
- [ ] `indexed` uploads show “ready” in file card subtitle

---

## P3 — Chunk API + document panel tabs/highlight

### Goal

`GET /api/docs/{id}/chunks[/{chunk_id}]`; Original | Parsed tabs; span highlight on citation click.

### Tasks

| # | Task | Files |
|---|------|-------|
| 3.1 | Add chunk list + single-chunk routes | `api/routes/docs.py` |
| 3.2 | Implement `_list_document_chunks(db, document_id, source_type, user)` with TRD-9 filter | new `backend/dharmiq/documents/chunks.py` |
| 3.3 | Ownership: upload chunks require `user_id` match; corpus readable by any authed user | `chunks.py` |
| 3.4 | Schemas `ChunkRead`, `ChunkListItem` | `schemas/chunks.py` |
| 3.5 | Extend `DocumentPanelParams` with `quoteStart?`, `quoteEnd?` | `document-panel-context.ts` |
| 3.6 | Parse `qstart`, `qend` from URL | `DocumentPanelProvider.tsx` |
| 3.7 | Add `fetchDocumentChunks`, `fetchDocumentChunk` | `api.ts` |
| 3.8 | Update `documentViewerPath` to pass `qstart`/`qend` when citation has spans | `api.ts`, `citations.ts` |
| 3.9 | Extend frontend `Citation` type with `quote_start_char?`, `quote_end_char?` | `api.ts` |
| 3.10 | Refactor `DocumentPanel.tsx`: tabs Original/Parsed; remove banner; Parsed = mono line list | `DocumentPanel.tsx` |
| 3.11 | Highlight span in Parsed tab; scroll to `chunk` row | `DocumentPanel.tsx` or `ParsedDocumentView.tsx` |
| 3.12 | Tests | `tests/test_document_chunks.py` |

### API contracts

**List**

```
GET /api/docs/{document_id}/chunks?source_type=corpus|upload
```

```json
{
  "document_id": "uuid",
  "source_type": "upload",
  "chunks": [
    {
      "chunk_id": "uuid",
      "chunk_index": 0,
      "preview": "First 200 chars…",
      "page_start": 1,
      "page_end": 1,
      "section_label": null
    }
  ]
}
```

**Single**

```
GET /api/docs/{document_id}/chunks/{chunk_id}?source_type=…
```

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "source_type": "upload",
  "text": "full chunk text",
  "context_text": "parent context or null",
  "page_start": 1,
  "page_end": 1,
  "section_label": null
}
```

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_document_chunks.py -q
```

| Test | Assert |
|------|--------|
| `test_list_upload_chunks_owned` | 200 for owner; 404 for other user |
| `test_get_chunk_text` | Full text returned |
| `test_corpus_chunks_no_user_filter` | Any authed user can read corpus chunks |

**Manual**

1. Index a corpus doc + user upload.
2. Get answer with citation; click citation link.
3. Panel opens on **Original** tab with PDF.
4. Switch to **Parsed** — mono lines visible.
5. If citation has spans (check message metadata), quoted substring highlighted in Parsed tab.
6. Confirm “coming soon” banner is gone.

### Definition of done

- [ ] Chunk API enforces upload ownership
- [ ] Highlight never runs from blockquote text alone (requires `qstart`/`qend`)
- [ ] Parsed tab labeled as indexed text (footer copy)

---

## P4 — LLM cost rows + session/monthly caps

### Goal

Every agent `acompletion` persists `llm_usage_events`; caps block new requests when exceeded.

### Tasks

| # | Task | Files |
|---|------|-------|
| 4.1 | Extend `LiteLLMService.acompletion` to return cost metadata or add `acompletion_with_usage` | `litellm_service.py` |
| 4.2 | Create `backend/dharmiq/llm/usage.py` with `record_llm_usage(db, *, user_id, chat_request_id, session_id, agent_role, model, response)` | new |
| 4.3 | Wire recording in agent nodes: clarifier, query_rewriter, answerer, validator | `agents/nodes/*.py` |
| 4.4 | After each record, increment `chat_requests.cost_usd` | `usage.py` |
| 4.5 | Create `check_usage_limits(db, user_id, session_id, settings) -> None` raises `UsageLimitExceededError` | `usage.py` |
| 4.6 | Call `check_usage_limits` in `create_agent_graph_request`, `retry_*`, `edit_*` | `agents/runner.py` |
| 4.7 | Exception handler → 429 JSON | `main.py` |
| 4.8 | Session rollup query: `SUM(chat_requests.cost_usd) WHERE session_id = ?` | `usage.py` |
| 4.9 | Monthly rollup: `SUM(llm_usage_events.cost_usd) WHERE user_id = ? AND created_at >= month_start UTC` | `usage.py` |
| 4.10 | Tests with mocked `completion_cost` | `tests/test_llm_usage.py` |

### `record_llm_usage` pseudocode

```python
usage = response.get("usage") or {}
prompt_tokens = int(usage.get("prompt_tokens") or 0)
completion_tokens = int(usage.get("completion_tokens") or 0)
cost_usd = Decimal(str(completion_cost(completion_response=response)))
# insert LlmUsageEvent; chat_request.cost_usd += cost_usd
```

Pass `agent_role` from each node (`"clarifier"`, `"query_rewriter"`, `"answerer"`, `"validator"`).

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_llm_usage.py -q
```

| Test | Assert |
|------|--------|
| `test_records_usage_on_completion` | Row in `llm_usage_events` |
| `test_session_cap_blocks` | Session at $1.00 → `UsageLimitExceededError` |
| `test_monthly_cap_blocks` | User at $10 in month → blocked |
| `test_enforce_false_allows` | `cost_limits.enforce=false` → no raise |

**Manual**

```bash
# Set very low caps in config.dev.yaml for test: per_session_usd: 0.0001
# Send chat message → eventually 429 on next message
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"test"}' \
  http://localhost:8000/api/chat/sessions/$SESSION_ID/messages
# Expect 429
```

### Definition of done

- [ ] At least one usage row per completed agent graph run
- [ ] `chat_requests.cost_usd` matches sum of events for that request
- [ ] Self-host bypass via `DHARMIQ_COST_LIMITS_ENFORCE=false`

---

## P5 — Agent hygiene (clarifier, loop, step cap)

### Goal

Structured clarifier only; duplicate Q/A detection; max 100 node executions.

### Tasks

| # | Task | Files |
|---|------|-------|
| 5.1 | Add `normalize_for_comparison(text: str) -> str` | `backend/dharmiq/agents/text_utils.py` |
| 5.2 | Clarifier: retry once if `needs_more_info` and empty `followup_items`; else raise `ClarifierStructureError` | `llm/agents/clarifier.py` |
| 5.3 | Runner catches structure error → fail request with visible message | `agents/runner.py` |
| 5.4 | Loop: before clarifier return, compare normalized questions to prior clarifier message in session; if duplicate → set `force_answer=True` or return refusal message per PRD 5.3.2 | `agents/runner.py` or `graph.py` |
| 5.5 | Loop: on retry/edit, compare normalized new assistant answer to previous assistant in session; if same → HTTP 409 with detail `duplicate_answer` | `api/routes/chat.py` |
| 5.6 | Add `node_execution_count: int` to `AgentGraphState` | `agents/state.py` |
| 5.7 | In `with_progress`, increment count; if `> 100` raise `GraphStepLimitExceeded` | `agents/graph.py` |
| 5.8 | Handle step limit → failed request + SSE error | `runner.py` |
| 5.9 | Remove markdown fallback in `parseClarifierItems` | `frontend/src/lib/clarifier.ts` |
| 5.10 | `ClarifyCard` / thread: empty items → “Could not load follow-up questions” | `thread.tsx` |
| 5.11 | Tests | `tests/test_agent_hygiene.py` |

### Clarifier failure user message

> “Something went wrong preparing follow-up questions. Please try again.”

### Duplicate answer user message

> “This request produced the same result. Try rephrasing or attach a document.”

### Step limit user message

> “This question took too many steps. Please simplify or start a new chat.”

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_agent_hygiene.py tests/test_agent_graph.py -q
cd frontend && npm run lint
```

| Test | Assert |
|------|--------|
| `test_clarifier_empty_followup_fails` | Mock LLM returns no items twice → request failed |
| `test_duplicate_clarifier_question_force_answer` | Same question round 2 → does not END at clarifier |
| `test_retry_duplicate_answer_409` | Same answer text → 409 |
| `test_step_limit_fails_request` | Mock graph looping → fails at 100 |

**Manual**

1. Trigger clarifier → chips render from metadata only.
2. Temporarily break clarifier JSON in dev → generic error card (no markdown bullets).

### Definition of done

- [ ] No `parseClarifierItems` markdown branch
- [ ] Step counter increments per node invocation (including retries through validator loop)
- [ ] Clarifier round cap (3) unchanged

---

## P6 — Export + delete account + Settings UI

### Goal

Privacy & data card; JSON export; hard delete with email+password.

### Tasks

| # | Task | Files |
|---|------|-------|
| 6.1 | New router `api/routes/account.py` | new |
| 6.2 | `GET /api/account/export` — build JSON per PRD §5.4.1 | `account.py`, `services/account_export.py` |
| 6.3 | `DELETE /api/account` — authenticate, delete files, delete user | `account.py`, `services/account_delete.py` |
| 6.4 | Register router in `main.py` prefix `/api` | `main.py` |
| 6.5 | `exportAccount()`, `deleteAccount(email, password)` in frontend | `api.ts` |
| 6.6 | Settings **Privacy & data** card (no save-history toggle) | `SettingsPage.tsx` |
| 6.7 | Export button → blob download | `SettingsPage.tsx` |
| 6.8 | Delete modal: email + password + warning; on success logout + redirect login | `SettingsPage.tsx` |
| 6.9 | Tests | `tests/test_account_privacy.py` |

### Export implementation notes

- Query user, sessions, messages, uploads (metadata only).
- `messages.metadata` serialized as `metadata` key in JSON.
- Stream as `JSONResponse` with `media_type="application/json"` and Content-Disposition attachment.

### Delete implementation notes

```python
user = await user_manager.authenticate(credentials)
if body.email.lower() != user.email.lower():
    raise HTTPException(409, "Email does not match")
shutil.rmtree(uploads_dir / str(user.id), ignore_errors=True)
await user_db.delete(user)
```

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_account_privacy.py -q
```

| Test | Assert |
|------|--------|
| `test_export_contains_sessions_messages` | Keys match PRD schema |
| `test_export_no_file_bytes` | No binary fields |
| `test_delete_wrong_email_409` | |
| `test_delete_cascades` | Sessions/messages gone |
| `test_delete_removes_upload_dir` | Mock filesystem |

**Manual**

1. Settings → Privacy & data → Export → `dharmiq-export-*.json` downloads.
2. Delete account with wrong email → error.
3. Delete with correct credentials → logged out; cannot login.

### Definition of done

- [ ] Export excludes corpus data and upload file bytes
- [ ] Delete is irreversible (hard delete)
- [ ] UI matches design demo §4.8 minus save-history row

---

## P7 — Feedback API + UI

### Goal

👍/👎 per assistant message with optional reason.

### Tasks

| # | Task | Files |
|---|------|-------|
| 7.1 | `POST /api/chat/messages/{message_id}/feedback` | `api/routes/feedback.py` or extend `chat.py` |
| 7.2 | Validate: message exists, `role == assistant`, same user session | route handler |
| 7.3 | Upsert on `(user_id, message_id)` | SQLAlchemy `merge` or `INSERT ON CONFLICT` |
| 7.4 | `submitFeedback(messageId, rating, reason?)` | `api.ts` |
| 7.5 | Add thumbs buttons to `AssistantActionBar` | `thread.tsx` |
| 7.6 | Optional: small popover for reason (both thumbs) | `thread.tsx` or `FeedbackButton.tsx` |
| 7.7 | Visual state when feedback already submitted (fetch on load optional — v0.4 may POST only) | `thread.tsx` |
| 7.8 | Tests | `tests/test_feedback.py` |

### API contract

```
POST /api/chat/messages/{message_id}/feedback
{ "rating": "up" | "down", "reason": "optional, max 500" }

200 → MessageFeedbackRead
404 → message not found / not assistant
403 → not owner
```

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_feedback.py -q
```

| Test | Assert |
|------|--------|
| `test_feedback_upsert` | Second POST updates reason |
| `test_feedback_assistant_only` | User message → 400 |
| `test_feedback_other_user_404` | |

**Manual**

1. Complete a chat answer.
2. Click 👍 → persists (network tab 200).
3. Click 👎 on another message with reason → 200.
4. Re-submit → upsert (no duplicate rows).

### Definition of done

- [ ] One row per (user, message)
- [ ] Reason optional for both ratings
- [ ] No Grafana work

---

## P8 — Idempotency + Celery dedupe + recovery

### Goal

`Idempotency-Key` on chat POST; Celery no duplicate runs; upload recovery documented.

### Tasks

| # | Task | Files |
|---|------|-------|
| 8.1 | `resolve_idempotency(db, user_id, key, body_hash)` → existing or None | `services/idempotency.py` |
| 8.2 | Wire header `Idempotency-Key` on POST/retry/edit | `api/routes/chat.py` |
| 8.3 | Store row in `idempotency_keys` on new request | `create_agent_graph_request` |
| 8.4 | `enqueue_agent_graph`: `apply_async(task_id=str(chat_request_id))`; skip if status `completed` | `chat_tasks.py` |
| 8.5 | `recover_stale_uploads()` on worker ready | `ingestion_tasks.py`, `celery_app.py` |
| 8.6 | Document recovery matrix | `docs/deployment.md` new § “Recovery behavior” |
| 8.7 | Frontend: generate `crypto.randomUUID()` per send; header on `postSessionMessage` | `api.ts` |
| 8.8 | Tests | `tests/test_idempotency.py`, `tests/test_chat_recovery.py` |

### Recovery matrix (document verbatim)

| Component | On Redis flush | On worker crash | On API restart |
|-----------|----------------|-----------------|----------------|
| LangGraph state | Postgres checkpoint — resume | Resume from checkpoint | N/A |
| SSE `seq` | Redis INCR lost — client uses `?after_seq=N` DB replay | Same | N/A |
| Celery queue | In-flight lost — re-enqueue pending/running from DB | Same | N/A |
| Upload mid-pipeline | Re-enqueue if stage ∉ {ready, failed} | Same | N/A |

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_idempotency.py tests/test_chat_recovery.py -q
```

| Test | Assert |
|------|--------|
| `test_idempotency_replay_same_key` | Two POSTs → same `chat_request_id` |
| `test_idempotency_conflict` | Same key, different body → 409 |
| `test_celery_duplicate_task_id` | Second enqueue no-op |
| `test_upload_recovery_reenqueue` | Stuck `chunking` → task requeued on worker_ready |

**Manual**

1. Send message with fixed `Idempotency-Key` twice → same `chat_request_id`.
2. Kill worker mid-run; restart → request completes.
3. SSE: disconnect and reconnect with `after_seq` from last event.

### Definition of done

- [ ] Idempotency TTL 24h enforced via `expires_at` check
- [ ] Recovery runbook in `deployment.md`
- [ ] No duplicate agent graph runs for same `chat_request_id`

---

## P9 — Dockerfiles + compose dev/prod + docs

### Goal

One-command full stack for self-hosters and `app.dharmiq.in` parity; host path preserved.

### Tasks

| # | Task | Files |
|---|------|-------|
| 9.1 | `backend/Dockerfile` multi-stage (builder + runtime); install tesseract for OCR | new |
| 9.2 | `frontend/Dockerfile` — Node build + nginx alpine runtime | new |
| 9.3 | `docker/nginx/default.conf` — static, `/api` proxy, SSE location | new |
| 9.4 | `docker-compose.dev.yml` — full stack per PRD §5.1.1 | new |
| 9.5 | `docker-compose.prod.yml` — built images, named volumes, no source mounts | new |
| 9.6 | Update `docker-compose.yml` comment + Redis volume/AOF | `docker-compose.yml` |
| 9.7 | Expand `.env.example` | `.env.example` |
| 9.8 | Add Docker sections to `docs/deployment.md` | `deployment.md` |
| 9.9 | README: Docker quick start alongside host path; version badge 0.4 | `README.md` |
| 9.10 | Bump `__version__` to `0.4.0` | `backend/dharmiq/__init__.py` |
| 9.11 | `config/config.docker.yaml` service hostnames | `config/` |

### `docker-compose.dev.yml` services (minimum)

| Service | Image / build | Notes |
|---------|---------------|-------|
| postgres | pgvector/pgvector:pg16 | volume `dharmiq_pgdata` |
| redis | redis:7-alpine | AOF + volume `dharmiq_redis` |
| api | build `backend/Dockerfile` | bind `./backend`, `./config`; `DHARMIQ_ENV=docker`; reload |
| celery-worker | same image | `celery worker`; bind-mount backend |
| celery-beat | same image | `beat_schedule.enabled=false` |
| frontend | node:22 or build dev target | bind `./frontend`; `npm run dev -- --host` |
| prometheus, grafana, flower | reuse existing images | optional profiles |

Bind mounts:

- `./data/corpus` → `/app/data/corpus`
- `./data/eval` → `/app/data/eval` (optional)
- `./data/uploads` → `/app/data/uploads`

### `docker-compose.prod.yml` services (minimum)

| Service | Notes |
|---------|-------|
| nginx | Serves frontend static + proxies API |
| api | gunicorn/uvicorn workers, no bind mounts |
| celery-worker, celery-beat | Same image as api |
| postgres, redis | Named volumes only |
| prometheus, grafana | Optional profile `observability` |

Volumes: `dharmiq_pgdata`, `dharmiq_redis`, `dharmiq_uploads`, `dharmiq_corpus`.

### `.env.example` additions

```bash
# Docker / production
DHARMIQ_ENV=dev
DHARMIQ_COST_LIMITS_ENFORCE=true
# DHARMIQ_ROOT=/app  # set in containers

# Compose service URLs (docker profile)
# DHARMIQ_DATABASE_PASSWORD=
# DHARMIQ_JWT_SECRET=
# OPENROUTER_API_KEY=
```

### Final smoke test (full stack)

```bash
cp .env.example .env
# Set OPENROUTER_API_KEY, secrets

docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Wait for healthy
curl -s http://localhost/api/health | jq .

# Manual checklist
# [ ] Signup/login
# [ ] Chat message → streamed answer
# [ ] Upload PDF → stages → ready → attach → cite
# [ ] Citation → document panel Parsed highlight
# [ ] Settings export JSON
# [ ] Thumbs feedback
# [ ] docker compose down && up → pending chat/upload recovers
```

Dev stack:

```bash
docker compose -f docker-compose.dev.yml up
# Edit backend file → API reloads
# Edit frontend → HMR
```

### Definition of done

- [ ] Prod compose: Nginx on port 80 (or documented 443 TLS termination)
- [ ] Dev compose: hot reload works for API + frontend
- [ ] README documents **both** host and Docker paths
- [ ] `docker-compose.yml` still starts infra for existing contributors
- [ ] All PRD §2.3 exit criteria checked

---

## 4. API summary (v0.4 delta)

| Method | Path | Phase | Description |
|--------|------|-------|-------------|
| GET | `/api/account/export` | P6 | JSON export download |
| DELETE | `/api/account` | P6 | Hard delete + body auth |
| POST | `/api/chat/messages/{id}/feedback` | P7 | Upsert feedback |
| GET | `/api/docs/{id}/chunks` | P3 | Ordered chunk list |
| GET | `/api/docs/{id}/chunks/{chunk_id}` | P3 | Single chunk text |
| GET | `/api/uploads/{id}` | P1 | + stage, count, error |
| POST | `/api/chat/sessions/{id}/messages` | P8 | + `Idempotency-Key` header |
| POST | `.../messages/{id}/retry` | P8 | + `Idempotency-Key` |
| PATCH | `.../messages/{id}` | P8 | + `Idempotency-Key` |

---

## 5. Testing expectations (v0.4)

| Layer | Scope |
|-------|-------|
| Unit | Stage transitions, cost math (mocked), idempotency, feedback upsert, normalization, step counter |
| Integration | Export/delete cascade, chunk auth, cap enforcement, clarifier structure |
| Manual | Full docker-compose.prod smoke (P9 checklist) |
| CI eval gate | **Deferred v0.5** (TRD-30) |

---

## 6. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `completion_cost` missing OpenRouter model price | Log warning; store `cost_usd=0` but keep tokens; reconcile manually |
| Parent/child chunk display confusing | Parsed tab shows leaf chunks only (TRD-9); footer explains “indexed text” |
| Beat schedule regression on beta | `beat_schedule.enabled` default `true` in beta yaml |
| Docker image size (sentence-transformers) | Multi-stage build; document min 8GB RAM |
| Per-session $1 cap tight | Monitor; admin reset deferred v0.10 |
| Migration marks in-flight uploads failed | 1-hour heuristic + upload recovery in P8 |

---

## 7. Post-ship checklist

- [x] Update [`roadmap.md`](../roadmap.md) v0.4 checkboxes
- [x] Bump README version badge to 0.4
- [ ] Optional: `docs/plans/v0.4/implementation.md` if phase notes diverge during build

---

## 8. Document history

| Date | Change |
|------|--------|
| 2026-06-22 | Initial TRD from PRD + v0.3 codebase inspection |
| 2026-06-22 | v0.4 implemented (P0–P9); post-ship docs and roadmap updated |

---

*Binding decisions in §2 override the PRD where noted. The PRD remains the product source of truth for scope and user stories.*
