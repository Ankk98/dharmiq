# Dharmiq v0.4 — Foundation PRD

**Status:** Draft (clarifications complete)  
**Version:** 0.4  
**Baseline:** v0.3 (Ashoka UI, agent graph, cosmetic upload stubs, no privacy/feedback/cost/Docker app stack)  
**Last updated:** 2026-06-22

Related: [`roadmap.md`](../roadmap.md) · [`principles.md`](../../principles.md) · [`v0.3.md`](../v0.3.md) · [`v02-eval-baseline.md`](../v02-eval-baseline.md)

---

## Clarification summary (Round 1)

| Topic | Decision |
|-------|----------|
| Docker audience | Self-hosters **and** production VPS (`app.dharmiq.in`) |
| Host quick start | **Keep** `uv` / `npm` path; **add** Docker path alongside |
| Frontend serving | **Nginx in Compose** (prod parity; SSE proxy) |
| Celery beat | **Include** in v0.4 Compose (infra ready; empty schedule OK) |
| Crash recovery | Auto-resume from LangGraph checkpoint; SSE reconnect with `?after_seq=N` |
| Replay semantics | Same `chat_request_id` resumes same run; **new** POST = new request (probabilistic LLM, similar quality band) |
| Chat idempotency | Industry standard: `Idempotency-Key` header → return existing `chat_request_id` on duplicate |
| Upload progress UX | **Polling** `GET /uploads/{id}` (~2s) while stage ∉ `{ready, failed}` |
| Document viewer | **Tab switch:** Original \| Parsed |
| Upload failure | Explicit `failed` stage + error message |
| Save-history toggle | **Deferred** — v0.4 ships export + delete only |
| Cost caps | **$1 / conversation**, **$10 / account / calendar month** (internal enforcement) |
| Feedback Grafana | **Deferred** to monitoring iteration |
| Legal stubs (signup checkbox, terms pages) | **Deferred** — product far from closed beta |
| Eval / smoke in CI | **v0.5** |

## Clarification summary (Round 2)

| Topic | Decision |
|-------|----------|
| Compose layout | One pattern; **separate files** for dev vs prod |
| Data volumes | **Named Docker volumes** for app data; **dev corpus bind-mount** for PDF access |
| Cost currency | Track and cap in **USD** ($1 ≈ ₹100, $10 ≈ ₹1000) |
| Cap hit behavior | **Hard refuse** with user-visible message; admin override deferred |
| Self-host bypass | Config flag **`cost_limits.enforce`** (default `true`); when `false`, track but do not block |
| Delete account | Require typing **email + password** |
| Export JSON | **Simple** scope (see §6.3); no file binaries |
| Feedback | 👍/👎 **API + UI** in v0.4; optional reason on **both** thumbs |
| Clarifier fallback | **(B) Hard drop** — metadata-only; no markdown parse path; clean/reset local DB acceptable |

## Clarification summary (Round 3)

| Topic | Decision |
|-------|----------|
| Dev compose | Source bind-mounts + hot reload (API, Celery); Vite dev or proxied dev frontend |
| Prod compose | Built images + Nginx; no source mounts |
| Corpus in Docker | Dev: bind-mount `./data/corpus` (and optionally `./data/eval`); prod: volume or documented copy-in |
| Parsed tab data | **No separate parsed blob** — join **chunk text from DB** (see §5.2) |
| Quote highlight | **Only** when citation includes `chunk_id` **and** `quote_start_char` / `quote_end_char` (or equivalent span) |
| Loop detection | **(C)** identical clarifier questions across rounds **and** identical assistant answers on retry/edit |
| Max graph steps | **100** node executions per `chat_request`, then fail with user-visible error |
| Celery beat schedule | **Empty** in v0.4 (container runs; no periodic tasks) |
| PRD location | This document: `docs/plans/v0.4/prd.md` |

---

## 1. Vision for v0.4

v0.4 makes Dharmiq **operationally reproducible and honest about data** before breadth (corpus) or quality gates (v0.5). Users and operators get:

1. **One-command Docker deploy** (dev and prod compose files) without hiding the existing host-based workflow.
2. **Truthful upload pipeline UI** — real `processing_stage`, not timer animation.
3. **Inspectable documents** — chunk text API, Parsed tab, citation-driven quote highlight.
4. **Core privacy** — export JSON and hard delete account (principles §3.1).
5. **Quality feedback loop** — per-message thumbs (+ optional reason).
6. **Internal cost discipline** — every LiteLLM call attributed; caps enforced by default.

**Positioning:** v0.4 is **foundation**, not feature breadth. Accuracy and corpus expansion remain gated at v0.5+.

---

## 2. Scope

### 2.1 In scope

| Area | Deliverables |
|------|----------------|
| **Ops** | Dockerfiles (API, Celery worker, Celery beat, frontend prod); `docker-compose.dev.yml`, `docker-compose.prod.yml`; Redis AOF/RDB volume; idempotent Celery enqueue; checkpoint resume docs |
| **Upload truth** | `processing_stage`, `chunk_count`, `failed` + error; poll-driven Documents UI |
| **Document viewer** | Chunk text API; Original \| Parsed tabs; span highlight from citation click |
| **Agent hygiene** | Structured clarifier only; loop detection; max 100 graph steps |
| **Privacy** | `GET /api/account/export`; `DELETE /api/account` with email+password confirm; Settings Privacy card |
| **Feedback** | `POST /api/chat/messages/{id}/feedback`; thumbs UI on assistant row |
| **Cost (internal)** | Per-call token/cost rows; conversation + monthly account rollups; cap enforcement |
| **Docs** | `.env.example` expansion; `docs/deployment.md` Docker sections |

### 2.2 Explicitly out of scope (v0.4)

| Item | Target |
|------|--------|
| Signup legal checkbox, stub privacy/terms | Deferred (pre–closed-beta) |
| Save-history preference toggle | Deferred |
| Share chat, notifications, Hindi UI | Roadmap v0.14+ |
| User-facing cost dashboard / billing UI | v0.22–v0.23 |
| Feedback Grafana dashboard | Monitoring iteration (post–v0.4) |
| Eval regression gate / E2E smoke in CI | **v0.5** |
| Admin dashboard (cap reset, failed upload retry) | v0.10+ |
| Celery beat periodic jobs | v0.8+ (empty beat OK in v0.4) |
| Export upload file binaries | Revisit later |

### 2.3 Exit criteria

- [ ] `docker compose -f docker-compose.prod.yml up` → working chat with Nginx, API, Celery, beat, Postgres, Redis
- [ ] `docker compose -f docker-compose.dev.yml up` → hot-reload dev stack; corpus PDFs ingestible via bind-mount
- [ ] Upload shows real stages through `ready` or `failed`; Documents page does not use cosmetic timer
- [ ] Citation click opens document panel with quote span highlight when span present
- [ ] Export JSON and delete account work end-to-end
- [ ] Every LiteLLM chat completion records tokens + computed cost; caps refuse over limit
- [ ] 👍/👎 persisted per assistant message
- [ ] Clarifier cards render **only** from `metadata.followup_items` (no markdown fallback)

---

## 3. Current state vs gaps (v0.3 baseline)

| Roadmap item | v0.3 state | v0.4 action |
|--------------|------------|-------------|
| Docker app stack | Only infra in `docker-compose.yml`; API/Celery on host | Add Dockerfiles + dev/prod compose |
| Redis persistence | No volume | AOF/RDB + named volume |
| `processing_stage` / `chunk_count` | `UserUploadRead.indexed: bool` only | Enum + counts on model and API |
| Documents pipeline UI | `useCosmeticPipelinePhase` timer | Poll API |
| Chunk API + highlight | Metadata + file only; “coming soon” banner | `GET .../chunks/{id}`; panel tabs + span highlight |
| Clarifier structured | Backend writes metadata; frontend markdown fallback | Hard drop fallback; validate on write |
| Export / delete account | Not implemented | New account routes |
| Feedback | Hidden in v0.3 | API + UI |
| LLM cost | `record_llm_tokens` metric only | Persist per call + rollups + caps |
| Chat idempotency | Re-enqueue on recover | `Idempotency-Key` + duplicate task no-op |
| Loop / step caps | Clarifier round cap = 3 only | + duplicate Q/A detection; max 100 steps |

**Already solid (minimal v0.4 work):** LangGraph graph, SSE progress, hybrid retrieval, session attachments, content-hash idempotent ingestion, Postgres checkpointer + resume tests.

---

## 4. User stories

### US-1 — Self-hoster one-command deploy

**As** a self-hoster, **I want** `docker compose` to start the full stack, **so that** I do not install `uv` and `nvm` on the host.

**Acceptance**

- Prod compose: Nginx → static frontend + `/api` proxy + SSE-friendly timeouts.
- Dev compose: API and worker containers mount source; reload on change.
- README documents **both** host and Docker quick starts.
- `.env.example` lists all required vars for Compose path.

### US-2 — Honest upload progress

**As** Ravi, **when** I upload a notice PDF, **I want** to see real processing stages, **so that** I know when I can attach it to chat.

**Acceptance**

- Stages: `uploaded` → `parsed` → `chunking` → `embedding` → `ready` (or `failed`).
- `chunk_count` visible when > 0.
- UI polls every ~2s until terminal state.
- Failed uploads show error summary; no infinite “Processing”.

### US-3 — Verify what the system indexed

**As** Anita, **when** I click a citation, **I want** to see the quoted passage highlighted in context, **so that** I can trust the answer.

**Acceptance**

- Document panel: **Original** (iframe/PDF) and **Parsed** (mono line list from chunks).
- Highlight applies **only** if citation has `chunk_id` + char span; no fuzzy guess from blockquote alone.
- “Coming soon” banner removed.

### US-4 — Own my data

**As** a user, **I want** to export my data and delete my account, **so that** I control my footprint (principles §3.1).

**Acceptance**

- Settings → **Privacy & data** card: Export, Delete account.
- Export downloads JSON (profile, sessions, messages, upload metadata).
- Delete requires email + password; hard-deletes user, sessions, messages, uploads, chunks, files on disk.

### US-5 — Improve answer quality

**As** the product team, **I want** thumbs feedback on answers, **so that** we can measure quality before corpus expansion.

**Acceptance**

- Assistant action row: 👍 / 👎; optional short reason for either.
- One feedback row per user per message (upsert).
- No Grafana requirement in v0.4.

### US-6 — Survive worker crashes

**As** a user with a long-running query, **when** a worker restarts mid-run, **I want** the request to resume, **so that** I do not lose progress.

**Acceptance**

- Pending/running requests re-enqueued on worker startup (existing pattern, documented).
- LangGraph checkpoint resume continues graph from last checkpoint.
- SSE client reconnects and receives remaining events.
- Duplicate Celery task for same `chat_request_id` is a no-op.

### US-7 — Bound LLM spend (internal)

**As** the operator, **I want** per-call cost and caps, **so that** runaway usage is blocked before monetization (v0.22).

**Acceptance**

- Each LiteLLM `acompletion` stores model, tokens in/out, computed USD cost.
- Conversation total updated on `chat_requests`; user monthly total in aggregate table or roll-up query.
- Over **$1** on current conversation or **$10** in calendar month → hard refuse before pipeline starts (or before next LLM call — pick one implementation, must be user-visible).
- `cost_limits.enforce: false` disables blocking (self-host); costs still logged.

---

## 5. Functional requirements

### 5.1 Ops & reliability

#### 5.1.1 Compose files

| File | Purpose |
|------|---------|
| `docker-compose.dev.yml` | Full dev stack: postgres, redis (persisted), api, celery-worker, celery-beat, frontend dev **or** nginx→vite proxy, prometheus, grafana, flower (optional) |
| `docker-compose.prod.yml` | Full prod-like stack: built images, nginx serves static frontend, api, workers, beat, infra |
| Existing `docker-compose.yml` | **Deprecate or reduce** to documented “infra-only” alias if needed for backward compat; README points to dev/prod files |

**Dev-specific**

- Bind-mount `./backend`, `./frontend/src` (or full frontend) for reload.
- Bind-mount `./data/corpus` (and `./data/eval` if useful) for ingestion without `docker cp`.
- Env: `DHARMIQ_ENV=dev`, cors includes dev origin.

**Prod-specific**

- Multi-stage Dockerfile builds; no source mounts.
- Named volumes: `dharmiq_pgdata`, `dharmiq_redis`, `dharmiq_uploads`, `dharmiq_corpus` (or document corpus seeding).
- Nginx: `proxy_read_timeout` suitable for SSE (≥ 300s); disable buffering for stream route.

#### 5.1.2 Redis persistence

- Enable **AOF** (and/or RDB) on Redis service.
- Named volume for `/data`.
- Document in `docs/deployment.md`: what is lost vs recovered on `docker compose down` / restart (Celery queue vs SSE seq vs checkpoints).

#### 5.1.3 Idempotency

**Chat POST** (`POST /api/chat/sessions/{id}/messages`, retry, edit):

- Accept optional header `Idempotency-Key: <uuid>`.
- Store `(user_id, key) → chat_request_id` with TTL 24h.
- Duplicate key + same body hash → return **same** `202` + `chat_request_id` (not 409).
- Key reuse with different body → `409 Conflict`.

**Celery**

- `enqueue_agent_graph`: if task already queued/running for `chat_request_id`, skip duplicate.
- Ingestion tasks: retain content-hash idempotency (existing).

#### 5.1.4 Recovery behavior (document)

| Component | On Redis flush | On worker crash | On API restart |
|-----------|----------------|-----------------|----------------|
| LangGraph state | Checkpoint in Postgres — **resume** | Resume from checkpoint | N/A |
| SSE `seq` | Redis INCR lost — client uses DB event replay | Same | N/A |
| Celery queue | In-flight tasks lost — **re-enqueue** pending/running from DB | Same | N/A |
| Upload mid-pipeline | Task lost — re-enqueue or mark `failed` after timeout (v0.4: re-enqueue if stage ∉ terminal) | Same | N/A |

User-facing copy for unrecoverable failure: “Something went wrong. Please retry your message.”

### 5.2 Upload & document truth

#### 5.2.1 `processing_stage` model

Replace boolean `indexed` as the sole source of truth (may keep `indexed` as computed `stage == ready` for compat).

```text
uploaded → parsed → chunking → embedding → ready
                                      ↘ failed
```

| Stage | Meaning |
|-------|---------|
| `uploaded` | Raw file stored; task enqueued |
| `parsed` | Pages/text extracted |
| `chunking` | Chunk groups written |
| `embedding` | Vectors computed |
| `ready` | Fully searchable |
| `failed` | Terminal error; `processing_error` string set |

**API:** `UserUploadRead` adds `processing_stage`, `chunk_count`, `processing_error`.

**Pipeline:** update stage in DB at each step (same transaction pattern as chunk writes).

#### 5.2.2 Parsed content strategy (Q3 decision)

**Do not** add a separate parsed blob on disk or a duplicate full-text column in v0.4.

- **Canonical parsed text** = ordered `user_upload_chunks.text` (and `document_chunks` for corpus).
- **Parsed tab** = server joins chunks by `chunk_index` (and `page_start` when present), returns line list API or single concatenated text with line offsets for highlight.
- **Rationale:** chunks are what RAG retrieves; one source of truth; no sync drift between blob and index.
- **Future:** page-faithful OCR layout may add `parsed_pages.json` on disk at ingest time (not v0.4).

#### 5.2.3 Chunk text API

```
GET /api/docs/{document_id}/chunks/{chunk_id}?source_type=corpus|upload
```

Response:

```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "source_type": "upload",
  "text": "…",
  "context_text": "…",
  "page_start": 1,
  "page_end": 1,
  "section_label": "…"
}
```

Optional list endpoint for Parsed tab:

```
GET /api/docs/{document_id}/chunks?source_type=…
```

Returns ordered summaries for mono line list (truncate long lines in list; full text via single-chunk GET).

#### 5.2.4 Document panel UX

- Remove “quoted passage highlighting coming soon” banner.
- Tabs: **Original** | **Parsed**.
- Original: existing iframe/file URL.
- Parsed: fetch chunk list; mono font; scroll to chunk when opened via citation.
- **Highlight:** if URL/query includes `chunk_id` + `quote_start_char` + `quote_end_char`, highlight that span in Parsed tab only (citation enricher already emits span fields in `CitationRecord`).

### 5.3 Agent loop hygiene

#### 5.3.1 Structured clarifier (hard drop)

**Write path**

- Clarifier node must persist `followup_items` in `message.metadata` with `question`, `why`, `options`.
- If LLM JSON lacks valid `followup_items` when `needs_more_info`, retry once; then fail request with user-visible error (do not save markdown-only clarifier).

**Read path**

- Remove `parseClarifierItems` markdown branch in `frontend/src/lib/clarifier.ts`.
- `ClarifyCard` renders only from metadata; empty metadata → generic error state (“Could not load follow-up questions”).

**Content field:** may keep markdown `content` for search/export readability, but UI **must not** parse it.

#### 5.3.2 Loop detection (6C)

| Signal | Action |
|--------|--------|
| Same normalized clarifier question text in round N and N-1 | Stop clarifying; set `force_answer` or return refusal: “I need different information to continue.” |
| Same normalized assistant answer on retry/edit as previous assistant message in session | Refuse regenerate: “This request produced the same result. Try rephrasing or attach a document.” |

Normalization: NFKC, collapse whitespace, lowercase for comparison.

#### 5.3.3 Graph guardrails

- **Max 100** node executions per `chat_request` (increment in `with_progress` wrapper or graph runtime).
- On exceed: mark request `failed`, emit SSE error, user message: “This question took too many steps. Please simplify or start a new chat.”
- Existing clarifier round cap (3) remains.

### 5.4 Privacy core

#### 5.4.1 Export JSON

`GET /api/account/export` → `application/json` attachment `dharmiq-export-{date}.json`

**v0.4 payload (simple)**

```json
{
  "exported_at": "ISO8601",
  "user": { "id", "email", "created_at" },
  "sessions": [{ "id", "title", "created_at", "updated_at" }],
  "messages": [{ "id", "session_id", "role", "content", "metadata", "created_at" }],
  "uploads": [{ "id", "original_filename", "mime_type", "size_bytes", "content_hash", "processing_stage", "chunk_count", "created_at" }]
}
```

No upload file bytes. No corpus data.

#### 5.4.2 Delete account

`DELETE /api/account` body:

```json
{ "email": "…", "password": "…" }
```

- Validate credentials; `409` if email mismatch.
- Hard delete: user row (cascade sessions, messages, requests, events, uploads, chunks), delete files under `data/uploads/{user_id}/`, invalidate JWT.
- Return `204`.

#### 5.4.3 Settings UI

Add **Privacy & data** card (per design demo §4.8):

- Export my data → triggers download.
- Delete account → modal with email + password fields + irreversibility warning.

### 5.5 Feedback

```
POST /api/chat/messages/{message_id}/feedback
{ "rating": "up" | "down", "reason": "optional string, max 500 chars" }
```

- Auth required; message must be assistant role in user's session.
- Unique `(user_id, message_id)` — upsert.
- UI: thumbs on assistant action row (alongside copy / regenerate / export MD).

### 5.6 Cost tracking & caps (internal)

#### 5.6.1 Per LLM call

On every `LiteLLMService.acompletion` (agents + eval if in-process):

- Persist: `chat_request_id` (nullable for non-chat), `agent_role`, `model`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `created_at`.
- Use LiteLLM response `usage` + model pricing table (config or `litellm` built-in).

Embeddings/rerank: optional v0.4 — at minimum chat agents; document if deferred.

#### 5.6.2 Rollups

- `chat_requests.cost_usd` (sum for request).
- User monthly: sum calls in calendar month (UTC or IST — **default UTC**, document in config).

#### 5.6.3 Caps

| Cap | Value | Scope |
|-----|-------|-------|
| Per conversation | **$1.00** | Sum of `cost_usd` for all `chat_requests` in same `session_id` in rolling window **or** per “conversation topic” — **v0.4: per session** (simpler) |
| Per account / month | **$10.00** | Calendar month, all sessions |

**Enforcement:** before starting agent graph (or before each LLM call — prefer **before graph** for clear UX), if `enforce` and over cap → `402` or `429` with JSON:

```json
{ "detail": "usage_limit_reached", "limit": "conversation" | "account_monthly" }
```

Frontend: toast + disable send.

**Config** (`config.*.yaml`):

```yaml
cost_limits:
  enforce: true
  per_session_usd: 1.0
  per_account_monthly_usd: 10.0
```

Env override: `DHARMIQ_COST_LIMITS_ENFORCE=false` for self-host.

---

## 6. Non-functional requirements

| NFR | Target |
|-----|--------|
| **Correctness** | No change to validator/refusal bar (v0.3 behavior preserved) |
| **Security** | Delete/export auth; feedback scoped to owner; chunk API enforces upload ownership |
| **Observability** | Existing Prometheus metrics retained; cost rows queryable for future admin |
| **Simplicity** | Polling over upload SSE; no new services beyond beat container |
| **Self-host** | `cost_limits.enforce: false`; full stack in Compose |

---

## 7. Technical appendix (implementation guide)

### 7.1 Schema migrations (indicative)

| Table / column | Notes |
|----------------|-------|
| `user_uploads.processing_stage` | enum string |
| `user_uploads.chunk_count` | int, default 0 |
| `user_uploads.processing_error` | text nullable |
| `chat_requests.cost_usd` | numeric |
| `chat_requests.idempotency_key` | string nullable, indexed |
| `llm_usage_events` | new table for per-call rows |
| `message_feedback` | `user_id`, `message_id`, `rating`, `reason`, timestamps |
| `idempotency_keys` | optional dedicated table vs column on `chat_requests` |

### 7.2 New / changed API summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/account/export` | JSON export |
| DELETE | `/api/account` | Hard delete with body |
| POST | `/api/chat/messages/{id}/feedback` | Upsert feedback |
| GET | `/api/docs/{id}/chunks/{chunk_id}` | Chunk text |
| GET | `/api/docs/{id}/chunks` | Ordered chunk list (Parsed tab) |
| GET | `/api/uploads/{id}` | Extended with stage, count, error |
| POST | `/api/chat/sessions/{id}/messages` | + `Idempotency-Key` header |

### 7.3 Frontend tasks (indicative)

| Component | Change |
|-----------|--------|
| `UploadLibrary.tsx` | Remove `useCosmeticPipelinePhase`; poll upload status |
| `uploadPipeline.ts` | Map API stage → chip states |
| `DocumentPanel.tsx` | Tabs; Parsed view; span highlight |
| `clarifier.ts` | Remove markdown fallback |
| `SettingsPage.tsx` | Privacy & data card |
| `thread.tsx` | Feedback buttons + reason modal (optional compact) |
| `api.ts` | export, deleteAccount, submitFeedback, fetchChunks |

### 7.4 Docker images

| Image | Base command |
|-------|----------------|
| `dharmiq-api` | `uv run dharmiq-api` / gunicorn+uvicorn workers for prod |
| `dharmiq-worker` | `celery -A celery_app worker` |
| `dharmiq-beat` | `celery -A celery_app beat` |
| `dharmiq-frontend` | nginx + static `dist/` |

### 7.5 Suggested implementation phases

| Phase | Focus |
|-------|--------|
| **P0** | Migrations: upload stages, `llm_usage_events`, feedback, idempotency |
| **P1** | Upload pipeline stage writes + API; Documents poll UI |
| **P2** | Chunk API + document panel tabs/highlight |
| **P3** | Cost instrumentation + caps; clarifier hard drop + loop/step guards |
| **P4** | Export + delete account + Settings |
| **P5** | Feedback API + UI |
| **P6** | Dockerfiles + compose dev/prod + deployment docs |
| **P7** | Idempotency + Celery dedupe + recovery runbook |

### 7.6 Testing expectations (v0.4)

- Unit/integration: stage transitions, cap enforcement, idempotency key replay, feedback upsert, export/delete cascade.
- Manual: `docker compose -f docker-compose.prod.yml up` smoke (chat + upload + cite + export).
- **CI eval/smoke gate:** deferred to v0.5 (do not block v0.4 PRs on live LLM eval).

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Docker complexity vs host path | Keep both documented; dev compose optional for contributors |
| Corpus in named volume hard to seed | Dev bind-mount `./data/corpus`; prod seed script documented |
| Cap false positives (long sessions) | Per-session $1 may be tight — monitor; admin reset in v0.10 |
| Parsed tab ≠ PDF layout | Label Parsed as “indexed text”; Original for visual |
| Removing clarifier fallback | Alpha only — reset DB; no migration |
| Cost pricing accuracy | Log model id + tokens; reconcile with OpenRouter dashboard manually |

---

## 9. Deferred from roadmap (track elsewhere)

| Item | Version |
|------|---------|
| Signup legal checkbox + stub pages | Pre–closed-beta / v0.21 |
| Save-history toggle | TBD |
| Feedback Grafana panel | Monitoring iteration |
| Eval + smoke CI gate | v0.5 |
| Admin cap reset / failed upload retry | v0.10 |
| Beat maintenance jobs | v0.8 |
| Export with file binaries | TBD |

---

## 10. Document history

| Date | Change |
|------|--------|
| 2026-06-22 | Initial PRD from 3-round clarification + v0.3 gap analysis |

---

*When v0.4 ships: update [`roadmap.md`](../roadmap.md) checkboxes, bump [`README.md`](../../../README.md) version, and add `docs/plans/v0.4/implementation.md` if a phase playbook is needed.*
