# Dharmiq Frontend

React + assistant-ui chat client for the Dharmiq API. **v0.3** ships the Ashoka design system on top of the v0.2 async chat stack.

See the [repo README](../README.md) for full-stack setup. Visual authority lives in [`docs/design/`](../docs/design/README.md) (demo HTML wins on conflict).

## Prerequisites

- [nvm](https://github.com/nvm-sh/nvm) for Node.js (version pinned in the repo-root `.nvmrc`)
- Backend running with `DHARMIQ_AGENT_GRAPH_V2=true` and a Celery worker for async chat

## Setup

```bash
# From repo root – use the pinned Node version
nvm install
nvm use

cd frontend
npm install
npm run dev
```

The dev server runs at http://localhost:5173 and proxies `/api` to the backend on port 8000.

Ensure the backend is running (`cd backend && uv run dharmiq-api`) and Celery is active (`uv run celery -A celery_app worker`) before using chat in v0.2+ mode.

## v0.3 design system (Ashoka)

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

**Deferred to a later release (v0.3 stubs only):**

- **Language / i18n** — Hindi typography rules are in `index.css` (`html[lang="hi"]` size ×1.08, line-height 1.9). No translation files; Settings language toggle is hidden.
- **Privacy** — save history, export JSON, delete account are omitted from Settings until backend support exists.
- **Upload pipeline stages** — Documents page shows cosmetic Uploaded → Ready chips; real per-stage API is v0.4.
- **Doc quote highlight** — citation opens resizable panel with PDF iframe; mono line highlight needs chunk API (v0.4).

## v0.2 UI features (retained)

- **Async chat** – messages POST to `/api/chat/sessions/{id}/messages`; UI subscribes to SSE at `/api/chat/requests/{id}/stream`
- **Live progress** – `MessageProgress` shows 5 user-facing steps (concise) or agent details (detailed)
- **Streamed answers** – assistant text replays token-by-token after validation; citations render inline
- **Clarifier flow** – clarify card with quick-reply chips and “Answer with what you have” (`force_answer`)
- **Documents library** – `/documents` page with dropzone, pipeline UI, and attach-to-chat toggles
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
    assistant-ui/     # Thread, markdown, citations
    auth/             # AuthLayout (aurora + auth card)
    chat/             # MessageProgress, ClarifyCard, RefusalCard, DebugPanel
    documents/        # DocumentPanel, citation links
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

Output goes to `frontend/dist/`. Nginx serves static files and proxies `/api` to the backend (see [`docs/deployment.md`](../docs/deployment.md)). SSE routes need `proxy_buffering off` on `/api/chat/requests/`.
