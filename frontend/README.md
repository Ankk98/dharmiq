# Dharmiq Frontend

React + assistant-ui chat client for the Dharmiq API. **v0.4** builds on the Ashoka design system (v0.3) with real upload stages, document panel tabs, privacy controls, and feedback.

See the [repo README](../README.md) for full-stack setup (host or Docker). Visual authority lives in [`docs/design/`](../docs/design/README.md) (demo HTML wins on conflict).

## Prerequisites

- [nvm](https://github.com/nvm-sh/nvm) for Node.js (version pinned in the repo-root `.nvmrc`), **or** Docker (`docker-compose.dev.yml` runs Vite in a container)
- Backend running with the agent graph enabled and a Celery worker for async chat

## Setup

### Host (default)

```bash
# From repo root – use the pinned Node version
nvm install
nvm use

cd frontend
npm install
npm run dev
```

The dev server runs at http://localhost:5173 and proxies `/api` to the backend on port 8000.

Ensure the backend is running (`cd backend && uv run dharmiq-api`) and Celery is active (`uv run celery -A celery_app worker`) before using chat.

### Docker dev stack

```bash
# From repo root
docker compose -f docker-compose.dev.yml up frontend
```

Set `VITE_DEV_API_PROXY=http://api:8000` in compose so the Vite proxy reaches the API container. Edit files on the host for HMR.

## v0.4 features

| Area | Implementation |
|------|----------------|
| Upload stages | `UploadLibrary` polls `GET /api/uploads/{id}` every 2s until `ready` or `failed` |
| Document panel | Original / Parsed tabs; span highlight via `qstart` / `qend` URL params |
| Privacy | Settings → Privacy & data: export JSON, delete account |
| Feedback | 👍/👎 on assistant messages; optional reason modal |
| Idempotency | `Idempotency-Key` header on message POST / retry / edit |
| Cost limits | Toast + disabled send on `usage_limit_reached` (429) |

## Ashoka design system (v0.3)

| Area | Implementation |
|------|----------------|
| Theme tokens | `src/index.css` — Ashoka light/dark CSS variables; synced with `docs/design/tokens.json` |
| Default mode | Light; dark via `.dark` class on `<html>` (not OS `prefers-color-scheme`) |
| Theme toggle | `ThemeProvider` → `localStorage` key `dharmiq_theme` (`light` \| `dark`); wired in Settings |
| Fonts | Inter (UI), Fraunces (display/wordmark), Geist Mono (refs/counts), Noto Sans Devanagari |
| App shell | 3-column grid: sidebar (250px / 70px collapsed) \| main \| resizable document panel |
| Mobile | App bar + bottom tab bar (`max-md:`); doc panel is full-screen overlay |
| Reading measure | Chat column `min(72ch, 100%)`, centered |

Compare against `docs/design/dharmiq-design-demo.html` in Light, Dark, and Mobile modes when reviewing UI changes.

### Settings & preferences

| Preference | Storage key | Values | UI |
|------------|-------------|--------|-----|
| Theme | `dharmiq_theme` | `light`, `dark` | Settings → Appearance; persists across reload |
| Progress view | `dharmiq_progress_view` | `concise`, `detailed` | Top nav + Settings → Answer progress |
| Debug progress | N/A (not persisted) | — | `DebugPanel` below top nav; superusers only |

**Deferred to later releases:**

- **Language / i18n** — Hindi typography rules in `index.css`; no translation files
- **Save-history toggle** — export + delete shipped in v0.4; retention preference deferred

## v0.2 UI features (retained)

- **Async chat** – messages POST to `/api/chat/sessions/{id}/messages`; UI subscribes to SSE at `/api/chat/requests/{id}/stream`
- **Live progress** – `MessageProgress` shows 5 user-facing steps (concise) or agent details (detailed)
- **Streamed answers** – assistant text replays token-by-token after validation; citations render inline
- **Clarifier flow** – clarify card from `metadata.followup_items` only; “Answer with what you have” (`force_answer`)
- **Message editing** – edit a user message in-thread; backend re-runs the agent from that point
- **Session deletion** – remove sessions from the sidebar thread list
- **Documents library** – `/documents` page with dropzone, real pipeline stages, attach-to-chat toggles
- **Session attachments** – chips above composer; attach/detach shows in-thread system pill
- **Document panel** – side panel on desktop (50/50, drag resize); `/docs/:id` deep links still work
- **Debug panel** – visible to superusers; shows raw progress/debug events from the stream
- **Retry** – failed requests can be retried via `/api/chat/sessions/{id}/messages/{message_id}/retry`

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |

## Project layout

```
frontend/src/
  components/
    assistant-ui/     # Thread, markdown, citations, feedback
    auth/             # AuthLayout (aurora + auth card)
    chat/             # MessageProgress, ClarifyCard, RefusalCard, DebugPanel
    documents/        # DocumentPanel, ParsedDocumentView, citation links
    layout/           # AppShell, sidebar, top nav, mobile chrome
    uploads/          # UploadLibrary, SessionAttachments
    ui/               # shadcn primitives, DefaultAvatar
  hooks/
    useChatStream.ts  # SSE client with reconnect via after_seq
    useTheme.ts       # Theme context consumer
  lib/
    api.ts            # REST + stream URL helpers
    chatPreferences.ts
    design/constants.ts
    progressDisplay.ts
    progress.ts
    uploadPipeline.ts # processing_stage → UI chips
  providers/
    ChatRuntimeProvider.tsx
    ThemeProvider.tsx
    DocumentPanelProvider.tsx
  pages/
    ChatPage.tsx
    DocumentsPage.tsx
    SettingsPage.tsx
    LoginPage.tsx / SignupPage.tsx
```

## Production build

```bash
nvm use
npm ci
npm run build
```

Output goes to `frontend/dist/`. For Docker prod, `frontend/Dockerfile` builds static assets into an Nginx image. Host deployment: Nginx serves `dist/` and proxies `/api` to the backend (see [`docs/deployment.md`](../docs/deployment.md)). SSE routes need `proxy_buffering off` on `/api/chat/requests/`.
