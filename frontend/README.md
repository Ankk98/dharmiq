# Dharmiq Frontend

React + assistant-ui chat client for the Dharmiq API (v0.2).

See the [repo README](../README.md) for full-stack setup.

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

Ensure the backend is running (`cd backend && uv run dharmiq-api`) and Celery is active (`uv run celery -A celery_app worker`) before using chat in v0.2 mode.

## v0.2 UI features

- **Async chat** – messages POST to `/api/chat/sessions/{id}/messages`; UI subscribes to SSE at `/api/chat/requests/{id}/stream`
- **Live progress** – `MessageProgress` stepper shows agent steps; toggle concise ↔ detailed via localStorage (`dharmiq_progress_view`)
- **Streamed answers** – assistant text appears token-by-token after validation; citations render inline
- **Clarifier flow** – follow-up questions with optional “Answer with what you have” (`force_answer`)
- **Upload library** – sidebar panel to upload and manage documents (PDF, DOCX, Markdown, images)
- **Session attachments** – attach library files to the active chat; retrieval uses only attached uploads
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
    assistant-ui/     # Thread, markdown rendering
    chat/             # MessageProgress, DebugPanel
    uploads/          # UploadLibrary, SessionAttachments
  hooks/
    useChatStream.ts  # SSE client with reconnect via after_seq
  lib/
    api.ts            # REST + stream URL helpers
    chatPreferences.ts
    progress.ts       # Progress step state
  providers/
    ChatRuntimeProvider.tsx  # assistant-ui external store + streaming
  pages/
    ChatPage.tsx
```

## Production build

```bash
npm ci
npm run build
```

Output goes to `frontend/dist/`. Nginx serves static files and proxies `/api` to the backend (see [`docs/deployment.md`](../docs/deployment.md)). SSE routes need `proxy_buffering off` on `/api/chat/requests/`.
