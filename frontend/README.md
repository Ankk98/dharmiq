# Dharmiq Frontend

React + assistant-ui chat client for the Dharmiq API.

See the [repo README](../README.md) for full-stack setup.

## Prerequisites

- [nvm](https://github.com/nvm-sh/nvm) for Node.js (version pinned in the repo-root `.nvmrc`)

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

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Production build to `dist/` |
| `npm run preview` | Preview production build |
| `npm run lint` | Run ESLint |

Ensure the backend is running (`cd backend && uv run dharmiq-api`) before using auth or chat.
