# v0.5 — Manual test runbook

**Parent:** [`prd.md`](./prd.md) §4.5 · [`trd.md`](./trd.md)  
**When:** Before tagging v0.5; after any change to RAG, corpus, or agent graph.

CI is **deferred** — this runbook is the release gate.

---

## 1. Prerequisites

- Docker (Postgres + Redis)
- `OPENROUTER_API_KEY` in `.env` (live eval only)
- MVP corpus indexed per [`mvp-corpus-allowlist.yaml`](./mvp-corpus-allowlist.yaml)

---

## 2. Automated checks (run locally)

```bash
# From repo root
docker compose up -d postgres redis

cd backend
uv sync --dev
uv run alembic upgrade head
uv run ruff check .
uv run pytest -m "not slow" -q

cd ../frontend
npm ci
npm run lint
npm run build
```

**Pass criteria:** exit code 0 on all commands.

---

## 3. Corpus verification

```bash
cd backend
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml
```

**Pass criteria:** all allowlist `id` values found in `source_documents.source_id`; print chunk counts.

---

## 4. Optional full-stack manual (Docker)

```bash
docker compose -f docker-compose.dev.yml up --build
```

Checklist:

- [ ] Signup / login at http://localhost:5173
- [ ] Chat message → streamed answer with citations
- [ ] Upload PDF → Documents shows stages → ready
- [ ] Attach → ask question citing upload
- [ ] Settings → Export JSON downloads
- [ ] Settings → Delete account (use throwaway user)

---

## 5. Live eval (advisory)

Requires indexed MVP corpus + `OPENROUTER_API_KEY`.

```bash
cd backend

# Single dataset
uv run dharmiq-eval --dataset v1_fundamental_rights

# Full MVP suite + compare to baseline
uv run dharmiq-eval --suite mvp --compare baseline
```

**Pass criteria:** metrics meet targets in [`v02-eval-baseline.md`](../v02-eval-baseline.md) **or** gaps documented in that file with remediation plan before v0.6.

---

## 6. Optional — BhashaBench weak indicator

```bash
cd backend
uv run python -m dharmiq.eval.tools.bhashabench_sample --output ../data/eval/runs/bhashabench_log.md
```

**Not a release blocker.** Review log for domain sanity only.

---

## 7. Sign-off

| Check | Date | Owner |
|-------|------|-------|
| §2 automated green | | |
| §3 corpus 26/26 | | |
| §5 eval advisory review | | |
| [`flow-coverage-matrix.md`](./flow-coverage-matrix.md) complete | | |
