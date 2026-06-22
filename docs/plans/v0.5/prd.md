# Dharmiq v0.5 — Quality gate & smoke tests PRD

**Status:** Draft  
**Version:** 0.5  
**Baseline:** v0.4 (Docker, upload truth, privacy, feedback, internal cost caps)  
**Last updated:** 2026-06-22

Related: [`roadmap.md`](../roadmap.md) · [`datasets.md`](../datasets.md) · [`data-implementation.md`](../data-implementation.md) · [`v02-eval-baseline.md`](../v02-eval-baseline.md) · [`principles.md`](../../principles.md) · [`v0.4/prd.md`](../v0.4/prd.md)

---

## Clarification summary

| Topic | Decision |
|-------|----------|
| **v0.5 purpose** | Prove **MVP statute corpus + stack** are good enough before v0.6 corpus expansion |
| **User-visible features** | **Minimal** — quality is mostly internal; no new product surfaces required |
| **Corpus scope** | **Small MVP allowlist** only (~50–200 PDFs across 3 domains); not full IndiaCode |
| **Self-host bootstrap** | **(A) Documented allowlist** — no bundled corpus zip in v0.5 |
| **Scraper** | Use `indian-law-dataset-scraper` to fetch allowlist PDFs; optional for contributors |
| **Eval owner** | Founder; approves gating JSONL ([`datasets.md` §9](../datasets.md#9-eval-owner-role-transferable)) |
| **Consumer eval seed** | Adapt **Grahak-Nyay** GeneralQA + SectoralQA → `v1_consumer`; add own Qs later |
| **BhashaBench-Legal** | **Weak indicator** — optional periodic report; **never** blocks merge |
| **HC judgments** | **Out of scope** — standalone project later |
| **Case law / SC AWS** | **Out of scope** — v0.11 |
| **Licensing review** | Deferred until pre-release |
| **Re-baseline** | **Yes** — measure v0.4 LangGraph stack first; update `v02-eval-baseline.md` before enforcing targets |
| **Eval runner path** | **`run_eval_rag`** for v0.5 gates (cost/speed); document gap vs production graph; full-graph eval → v0.7 |
| **CI / GitHub Actions** | **Deferred** — manual test runbook for v0.5 |
| **Live eval gate** | **Manual**, **advisory** — `dharmiq-eval` on MVP subset; does not block merges |
| **Regression harness** | Baseline JSON artifact + compare candidate; advisory fail on threshold breach |
| **Automated smoke in CI** | **Deferred** — run pytest smoke manually before releases |
| **Embeddings / DB** | Keep **local MiniLM + single Postgres**; no vector DB migration in v0.5 |
| **v0.6 gate** | Do **not** start central corpus expansion until v0.5 exit criteria pass |

---

## 1. Vision for v0.5

v0.4 made Dharmiq **reproducible and honest**. v0.5 makes it **measurable**.

Principles §1.6: *measured quality > asserted quality*. Before we index more Acts (v0.6) or judgments (v0.11), we must:

1. **Index a documented MVP statute subset** across fundamental rights, consumer, and employment.
2. **Build eval datasets** that reflect citizen questions, refusals, revised law, and retrieval stress.
3. **Run a benchmark harness** with frozen baselines and regression detection.
4. **Manual smoke / test runbook** before tagging v0.5 (CI automation deferred).
5. **Record a v0.4-stack baseline** so quality targets are grounded in reality.

**Positioning:** v0.5 is a **quality release**, not a feature release. Citizens may see slightly better answers from corpus curation fixes, but the deliverable is **confidence to expand data**.

---

## 2. Scope

### 2.1 In scope

| Area | Deliverables |
|------|----------------|
| **MVP corpus** | [`mvp-corpus-allowlist.yaml`](./mvp-corpus-allowlist.yaml) — 26 central instruments; PDFs indexed via existing ingestion |
| **Eval datasets** | `v1_fundamental_rights` (expand), `v1_consumer`, `v1_employment`, `v1_refusal_adversarial`, `v1_revised_law`, `v1_needle_statute` |
| **Eval harness** | Reproducible `dharmiq-eval` runs; baseline JSON; compare + exit code on regression (script or CLI flags) |
| **Re-baseline** | Run eval on v0.4 stack; update `v02-eval-baseline.md` with measured vs target |
| **Grahak adapter** | Script or manual pass to seed `v1_consumer` from Grahak-Nyay QAs + CPA citation mapping |
| **Smoke / E2E** | Extend `test_v02_e2e_smoke.py` (export + delete); flow coverage matrix; **manual** run before release |
| **Manual test runbook** | Document commands for pytest, lint, compose smoke, live eval |
| **Docs** | MVP allowlist in this PRD or linked doc; update `datasets.md` / `data-implementation.md` as needed |
| **BhashaBench (weak)** | Optional script/note to run sampled MCQ eval quarterly — results logged, not gated |

### 2.2 Explicitly out of scope (v0.5)

| Item | Target |
|------|--------|
| Central IndiaCode full expansion | **v0.6** |
| Case law ingestion (AWS SC/HC) | **v0.11** / HC standalone |
| Full LangGraph path as primary eval gate | **v0.7** (stretch in v0.5 if time) |
| Clarifier multi-turn / upload+statute eval sets | **v0.7** |
| User-facing quality dashboard | **v0.10** |
| Feedback → eval automation | **v0.10** |
| BhashaBench as merge gate | Never |
| Bundled `mvp-corpus.zip` release artifact | Optional post–v0.5 |
| Licensing sign-off for corpus redistribution | Pre-release |
| Hindi UI / answers | **v0.14** |
| Admin reindex UI | **v0.10** |
| Playwright browser E2E | Optional stretch |
| **GitHub Actions / CI** | **Deferred** post–v0.5 |

### 2.3 Exit criteria

- [ ] **MVP allowlist** in [`mvp-corpus-allowlist.yaml`](./mvp-corpus-allowlist.yaml) indexed in dev; chunk counts logged
- [ ] **Re-baseline** complete — `v02-eval-baseline.md` reflects v0.4 stack measurements
- [ ] **Gating eval datasets** committed (minimum per domain: ~30 rights/consumer/employment; ~20 refusal; ~15 revised-law; ~20 needle)
- [ ] **Manual live eval** meets targets on MVP subset **or** documented gap + remediation plan before v0.6 *(advisory — not a merge blocker)*
- [x] **Benchmark harness** can compare candidate run vs baseline artifact
- [ ] **Manual smoke runbook** executed — pytest smoke + lint green locally
- [x] **Flow coverage matrix** published
- [ ] **Roadmap rule** — v0.6 not started until above checked (or explicit rescope)

---

## 3. MVP corpus allowlist

Authoritative list: **[`mvp-corpus-allowlist.yaml`](./mvp-corpus-allowlist.yaml)** — **26 central instruments** (10 fundamental rights, 7 consumer, 9 employment), including 4 **superseded** texts (IPC, CrPC, CPA 1986) for revised-law eval.

Small subset strategy ([`data-implementation.md`](../data-implementation.md)): prove retrieval and eval on this set before v0.6 expansion.

### 3.1 Domains

| Domain | Count | Highlights |
|--------|-------|------------|
| **Fundamental rights / police** | 10 | Constitution, BNS, BNSS, IPC*, CrPC*, NSA, PHRA, POCSO, JJ, RTI |
| **Consumer** | 7 | CPA 2019, CPA 1986*, Legal Metrology, FSSA, Competition, Contract Act, IT Act |
| **Employment** | 9 | IDA, Payment of Wages, Minimum Wages, EPF, Bonus, POSH, Contract Labour, Maternity, Equal Remuneration |

\*Superseded — index for `v1_revised_law` negative fixtures only.

### 3.2 Sourcing workflow

1. Use `scraper_instrument_id` / `india_code_handle` from the YAML with `indian-law-dataset-scraper`.  
2. `indiacode download --scope central --extract-text --resume`  
3. Copy matching PDFs → `data/corpus/india_code/raw/` + `manifest.json` (`id` → `source_id`).  
4. `uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs`

**Self-hosters:** same YAML (Option A — no bundled zip).

### 3.3 Allowlist maintenance

- Bump `version` in YAML when acts added/removed.  
- Eval JSONL rows should reference `source_id` from the allowlist.

---

## 4. Eval & benchmarks

### 4.1 Quality metrics (gating)

From [`v02-eval-baseline.md`](../v02-eval-baseline.md) — enforced on **nightly/manual** live eval after re-baseline:

| Metric | Target |
|--------|--------|
| Faithfulness (Ragas) | ≥ 0.85 |
| Answer correctness (Ragas) | ≥ 0.80 |
| LLM citation correctness | ≥ 0.95 |
| Retrieval recall@5 | ≥ 0.77 |
| `blockquote_met` (statutory Qs) | ≥ 0.80 |
| `refusal_correct` | ≥ 0.90 |

Aggregate per dataset and **rolled up MVP suite** (all gating JSONL combined).

### 4.2 Gating datasets

| Dataset | Purpose | Seed / build |
|---------|---------|--------------|
| `v1_fundamental_rights` | Rights, police, arrest | Expand existing JSONL |
| `v1_consumer` | CPA 2019, refunds, defects | **Grahak-Nyay** + citation mapping |
| `v1_employment` | Notice, wages, termination | Scraper sections + manual Qs |
| `v1_refusal_adversarial` | Weak retrieval, off-topic | Auto + owner labels |
| `v1_revised_law` | Must cite BNS not IPC | Scraper pairs + owner review |
| `v1_needle_statute` | recall@5 stress | Auto from indexed sections |

Schema: [`dataset_format.md`](../../../backend/dharmiq/eval/dataset_format.md). Owner sign-off required for gating rows ([`datasets.md` §9](../datasets.md#9-eval-owner-role-transferable)).

### 4.3 Benchmark harness

**Requirements:**

- Run ID, git SHA, model id, corpus manifest hash, timestamp in summary JSON.  
- `data/eval/runs/baseline.json` (or similar) as frozen reference.  
- Compare command exits non-zero if any gating metric drops below target or regresses > configured delta vs baseline.  
- Results written to `data/eval/runs/` and optionally `eval_runs` DB tables.

**Eval path (v0.5):** `run_eval_rag()` — document known gap: no clarifier/validator in eval loop. Production faithfulness may differ; v0.7 closes gap with full-graph eval.

### 4.4 BhashaBench-Legal (weak indicator)

- **Not** a merge gate.  
- Optional: quarterly sampled MCQ run ([BhashaBench-Legal](https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal)) stratified by constitutional / consumer / employment tags.  
- Log scores in eval runs or a simple markdown log for **domain coverage sanity** — low score prompts corpus review, not model blocking.  
- See [`datasets.md` §5.3](../datasets.md#53-bhashabench-legal--weak-indicator-not-a-gate).

### 4.5 Manual testing vs automation

| Check | Command | When | Blocks release? |
|-------|---------|------|-----------------|
| Backend tests | `cd backend && uv run pytest -m "not slow" -q` | Before v0.5 tag / major changes | **Manual gate** |
| Backend lint | `uv run ruff check .` | Same | Manual |
| Frontend lint | `cd frontend && npm run lint` | Same | Manual |
| E2E smoke | `test_v02_e2e_smoke.py` (mocked LLM) | Same | Manual |
| Live `dharmiq-eval` | Full MVP suite | When corpus or RAG changes | **Advisory** |
| BhashaBench sample | Optional script | Quarterly | **Advisory** (weak indicator) |
| **CI (GitHub Actions)** | — | **Deferred** | — |

**Manual test runbook (minimum before v0.5 ship):**

```bash
# Infra
docker compose up -d postgres redis

# Backend
cd backend && uv sync --dev && uv run alembic upgrade head
uv run ruff check .
uv run pytest -m "not slow" -q

# Frontend
cd ../frontend && npm ci && npm run lint && npm run build

# Optional: full stack
docker compose -f docker-compose.dev.yml up
# Manual: signup → chat → upload → cite → export → delete

# Live eval (advisory; needs OPENROUTER_API_KEY + indexed MVP corpus)
cd backend && uv run dharmiq-eval --dataset v1_fundamental_rights
```

---

## 5. Smoke tests & flow coverage

### 5.1 Required E2E path (API, mocked LLM)

Extend existing smoke to cover:

1. Register + login  
2. Create session  
3. Upload → process → attach  
4. POST message → `202` → SSE until `done`  
5. Assert citations, disclaimer, progress events  
6. **Export** account JSON  
7. **Delete** account (or use disposable test user)

### 5.2 Flow coverage matrix (publish in repo)

| Critical path | Test |
|---------------|------|
| Auth signup/login | pytest auth fixtures |
| Chat SSE stream | `test_v02_e2e_smoke` |
| Upload pipeline stages | upload tests + smoke |
| Attach + retrieve user doc | smoke |
| Citation → chunk API | integration tests |
| Export / delete | v0.5 smoke extension |
| Idempotency replay | existing v0.4 tests |
| Cost cap refusal | unit test (mocked) |
| Feedback upsert | v0.4 tests |

### 5.3 Automation (deferred)

CI/GitHub Actions is **out of scope for v0.5**. Use §4.5 manual runbook. Add automated PR checks in a follow-up after the harness and datasets stabilize.

## 6. User stories

### Story 1 — Operator: “Are we safe to expand corpus?”

As an operator, I run the benchmark harness against the MVP subset. If metrics meet targets and the manual test runbook passes, I approve v0.6 central expansion.

### Story 2 — Developer: “Smoke before ship”

Before tagging v0.5, I run pytest smoke and lint locally (no API keys for smoke). Failures block the release.

### Story 3 — Eval owner: “Regression visible”

As eval owner, I compare eval JSON to `baseline.json` after RAG changes. Drops are **investigated** (advisory); they do not auto-block git merges in v0.5.

### Story 4 — Self-hoster: “Minimum corpus”

As a self-hoster, I follow the documented MVP allowlist, drop PDFs in `data/corpus/india_code/raw/`, run sync, and get a working rights/consumer/employment subset.

---

## 7. Implementation phases (suggested)

| Phase | Focus | Done when |
|-------|-------|-----------|
| **P0** | MVP allowlist doc + index PDFs | Corpus indexed; counts logged |
| **P1** | Re-baseline on v0.4 stack | `v02-eval-baseline.md` updated |
| **P2** | Eval datasets (rights, consumer from Grahak, employment) | Owner-approved JSONL committed |
| **P3** | Refusal, revised-law, needle datasets | Owner-approved JSONL committed |
| **P4** | Benchmark harness (baseline + compare) | Script/CLI works |
| **P5** | Smoke extension + flow matrix + manual runbook | Runbook doc'd; smoke passes locally |
| **P6** | BhashaBench weak-indicator note (optional) | Log format documented |
| ~~**P7**~~ | ~~GitHub Actions~~ | **Deferred** |

TRD: [`trd.md`](./trd.md) · Runbook: [`manual-test-runbook.md`](./manual-test-runbook.md)

---

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| v0.2 targets too aggressive for v0.4 stack | Re-baseline first; adjust targets with documented rationale |
| Eval cost (OpenRouter) | Nightly only; subset size caps; cache nothing sensitive |
| Grahak QAs don’t map to CPA sections | Owner review; drop procedural/forum-contact rows |
| `run_eval_rag` ≠ production graph | Document gap; add full-graph eval in v0.7 |
| CI flakiness (SSE, timing) | Deferred CI; mocked LLM in local pytest |
| Allowlist drift vs eval | Manifest hash in eval summary; allowlist `version` in YAML |
| Founder bottleneck on eval review | Rubric in `datasets.md` §9; batch review |

---

## 9. Success metrics

| Metric | Target |
|--------|--------|
| Gating eval suite pass rate | 100% on MVP subset (manual eval, advisory) |
| Manual smoke runbook | Executed before v0.5 tag |
| Critical path coverage | 100% rows in flow matrix have a test |
| Time to v0.6 kickoff | Within 1 sprint of v0.5 exit criteria met |

---

## 10. Resolved decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | CI automation? | **Skip for v0.5** — manual runbook (§4.5) |
| 2 | Live eval blocks merges? | **No** — advisory only |
| 3 | Minimum questions per domain? | ~30 rights/consumer/employment; ~20 refusal; ~15 revised-law; ~20 needle |
| 4 | Allowlist file? | [`mvp-corpus-allowlist.yaml`](./mvp-corpus-allowlist.yaml) |

---

## 11. Document history

| Date | Change |
|------|--------|
| 2026-06-22 | CI deferred; live eval advisory; added `mvp-corpus-allowlist.yaml` |

---

*When v0.5 ships: update [`roadmap.md`](../roadmap.md), [`README.md`](../../../README.md) version badge, and mark exit criteria.*
