# Dharmiq v0.5 — Technical Requirements & Implementation Plan

**Status:** Draft  
**Version:** 0.5  
**Parent doc:** [`prd.md`](./prd.md)  
**Baseline:** v0.4 — Docker, upload truth, privacy, feedback, cost caps, mocked pytest smoke  
**Last updated:** 2026-06-22

Related: [`mvp-corpus-allowlist.yaml`](./mvp-corpus-allowlist.yaml) · [`flow-coverage-matrix.md`](./flow-coverage-matrix.md) · [`manual-test-runbook.md`](./manual-test-runbook.md) · [`datasets.md`](../datasets.md) · [`data-implementation.md`](../data-implementation.md) · [`v02-eval-baseline.md`](../v02-eval-baseline.md)

---

## How to use this document

1. **Read binding decisions first** (§2). They override ambiguous PRD wording.
2. **One phase at a time.** Do not start phase N+1 until that phase’s smoke tests pass.
3. **Preserve v0.4 behavior** except where this TRD explicitly changes eval/smoke/docs.
4. **Match existing conventions:** async SQLAlchemy, Pydantic v2, pytest-asyncio, structlog, YAML config in `config/`, package layout under `backend/dharmiq/`.
5. **Every phase ends with:** code/docs + tests + smoke command block.
6. **Do not commit** unless the user asks.
7. **No CI/GitHub Actions in v0.5** — all gates are manual ([`manual-test-runbook.md`](./manual-test-runbook.md)).

### Global smoke gate (after every phase)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest -m "not slow" -q
cd frontend && npm run lint
```

### Phase dependency graph

```text
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5 ──► P6 ──► P7 (optional)
 │      │
 │      └── requires indexed MVP corpus (P0 exit)
 └── corpus tooling + index (operational)
```

| ID | Name | Depends on | Est. |
|----|------|------------|------|
| **P0** | Corpus bootstrap tooling + MVP index | — | 1–2 d |
| **P1** | Eval metadata + re-baseline | P0 | 1 d |
| **P2** | Dataset schema + loader + rights expansion | P0 | 2 d |
| **P3** | Consumer (Grahak) + employment datasets | P2 | 2 d |
| **P4** | Refusal / revised-law / needle + recall@5 | P2 | 2 d |
| **P5** | Benchmark harness (baseline + compare + suite) | P1, P2–P4 datasets | 2 d |
| **P6** | E2E smoke extension + flow matrix + runbook | P5 | 1 d |
| **P7** | BhashaBench weak indicator (optional) | — | 0.5 d |

---

## 1. Current codebase snapshot (v0.4)

Verify paths before editing.

### 1.1 Eval stack

| Area | Path | v0.4 state |
|------|------|------------|
| CLI | `backend/dharmiq/eval/cli.py` | `--dataset` only; no `--suite`, `--compare`, `--write-baseline` |
| Runner | `backend/dharmiq/eval/runner.py` | `run_eval_rag()` → rewriter + retrieval + answerer; **no** clarifier/validator |
| Dataset loader | `backend/dharmiq/eval/dataset_loader.py` | `EvalDatasetRecord` — no `must_not_cite`, `required_source_ids`, recall fields |
| Expectations | `backend/dharmiq/eval/expectations.py` | citation count, blockquote, refusal heuristics |
| Judge | `backend/dharmiq/eval/judge.py` | LLM JSON judge for answer + citation correctness |
| Celery eval | `backend/dharmiq/tasks/eval_tasks.py` | `dharmiq.eval.run_dataset` task |
| DB models | `backend/dharmiq/db/models/evals.py` | `eval_datasets`, `eval_questions`, `eval_runs`, `eval_results` |
| Config | `backend/dharmiq/config/settings.py` | `EvalSettings`: `datasets_dir`, `runs_dir` only |
| Format doc | `backend/dharmiq/eval/dataset_format.md` | v0.2 fields documented |
| Preflight | `runner._preflight_corpus()` | Fails if no `source_documents` / `document_chunks` |
| **recall@5** | — | **Not implemented** |
| **Baseline compare** | — | **Not implemented** |

### 1.2 Corpus & ingestion

| Area | Path | v0.4 state |
|------|------|------------|
| Scanner | `backend/dharmiq/ingestion/scanner.py` | Reads `manifest.json` (list or dict); `source_id`, `title`, `doc_type`, `jurisdiction` |
| Pipeline | `backend/dharmiq/ingestion/pipeline.py` | `sync_corpus_documents`, `process_document` |
| Corpus dir | `data/corpus/india_code/raw/` | Manual PDFs; gitignored |
| Allowlist | `docs/plans/v0.5/mvp-corpus-allowlist.yaml` | 26 instruments defined |
| Manifest builder | — | **Does not exist** |
| Corpus verify | — | **Does not exist** |

### 1.3 Smoke & privacy tests

| Area | Path | v0.4 state |
|------|------|------------|
| E2E smoke | `backend/tests/test_v02_e2e_smoke.py` | Chat + upload + attach + SSE; **no** export/delete |
| Account privacy | `backend/tests/test_account_privacy.py` | Export + delete covered **separately** |
| Eval preflight | `backend/tests/test_eval_runner.py` | Empty corpus → `EvalError` |
| Dataset loader test | `backend/tests/test_eval_dataset_loader.py` | Expects **8** rows in `v1_fundamental_rights` |

### 1.4 Committed eval data

| File | Rows | Notes |
|------|------|-------|
| `data/eval/datasets/v1_fundamental_rights.jsonl` | 8 | q1–q8; q4 consumer, q5 RTI, q6 CrPC (migrate revised-law to P4 dataset) |
| Other gating datasets | — | **Do not exist yet** |

### 1.5 Version

| File | Value |
|------|-------|
| `backend/dharmiq/__init__.py` | `0.4.0` → bump to `0.5.0` in **P6** only |

---

## 2. Binding decisions (implementation hardening)

Do not deviate without updating this doc and [`prd.md`](./prd.md).

| ID | Topic | Decision |
|----|-------|----------|
| **TRD-50** | CI | **No GitHub Actions** in v0.5. Manual [`manual-test-runbook.md`](./manual-test-runbook.md). |
| **TRD-51** | Eval pipeline | **`run_eval_rag()` only** for all v0.5 gates. Full LangGraph eval → v0.7. |
| **TRD-52** | Live eval blocking | **Advisory only** — compare exits non-zero but does not block git merges by automation. |
| **TRD-53** | Baseline file | `data/eval/runs/baseline.json` — committed after P1 re-baseline (aggregate MVP metrics + per-dataset). |
| **TRD-54** | Regression delta | Float metrics: fail `--compare` if drop **> 0.02** absolute vs baseline (faithfulness, answer_correctness, llm_citation_correctness, recall_at_5). Boolean aggregates: fail if any drop **> 0.05** absolute. |
| **TRD-55** | recall@5 | Computed on **post-rerank top-5** chunks. Hit if any `expected_citations[].section` appears as case-insensitive substring in chunk `text` OR chunk `metadata.section_label`. |
| **TRD-56** | Revised-law check | JSONL field `must_not_cite_sections`: list of strings; **fail** `revised_law_met` if answer contains any (case-insensitive). Separate from `must_not_cite_source_ids` (optional v0.5: sections only). |
| **TRD-57** | Loader backward compat | New JSONL fields optional; missing fields = no op. |
| **TRD-58** | MVP suite | Hardcoded list in `backend/dharmiq/eval/suite.py` — see §5.5. |
| **TRD-59** | `manifest.json` | JSON **array** of objects: `file`, `source_id`, `title`, `doc_type`, `jurisdiction`, `canonical_url` (optional `enactment_date`). Filename = `data/corpus/india_code/raw/manifest.json`. |
| **TRD-60** | Tooling package | New modules under `backend/dharmiq/eval/tools/` (not loose repo scripts). |
| **TRD-61** | E2E smoke | **Extend** `test_v02_e2e_smoke.py` with export + delete steps; do not rename file (avoid churn). |
| **TRD-62** | Slow tests | Any test calling live OpenRouter/Ragas: `@pytest.mark.slow`. |
| **TRD-63** | Grahak input | Adapter reads clone at `$GRAHAK_NYAY_REPO` or `../GrahakNyay` relative to repo root. |
| **TRD-64** | BhashaBench | Optional `bhashabench_sample.py`; append-only log `data/eval/runs/bhashabench_log.md`. |
| **TRD-65** | Dataset minimum counts | rights ≥30, consumer ≥30, employment ≥30, refusal ≥20, revised_law ≥15, needle ≥20 (per PRD). |
| **TRD-66** | Rights dataset q6 | **Keep** q6 (CrPC) in `v1_fundamental_rights` until BNSS corpus proven; add parallel `v1_revised_law` rows expecting **BNSS** citations. |
| **TRD-67** | Eval summary metadata | Every run JSON includes: `git_sha`, `allowlist_version`, `allowlist_sha256`, `corpus_document_count`, `corpus_chunk_count`, `dharmiq_version`, `eval_path: "run_eval_rag"`. |
| **TRD-68** | Compare CLI | `dharmiq-eval --compare baseline` reads `data/eval/runs/baseline.json`. `--write-baseline` overwrites it from latest run. |
| **TRD-69** | Threshold targets | Use [`v02-eval-baseline.md`](../v02-eval-baseline.md) targets; P1 records **measured** v0.4 stack values before enforcing. |
| **TRD-70** | Owner sign-off | Gating JSONL changes require eval owner review (founder); note in PR description only — no code gate. |

### Quality targets (from v02-eval-baseline)

| Metric | Target | Aggregated in |
|--------|--------|---------------|
| `faithfulness` | ≥ 0.85 | per dataset + MVP suite |
| `answer_correctness` | ≥ 0.80 | per dataset + MVP suite |
| `llm_citation_correctness` | ≥ 0.95 | per dataset + MVP suite |
| `recall_at_5` | ≥ 0.77 | needle + any row with `expected_citations` |
| `blockquote_met` | ≥ 0.80 | rows with `expect_blockquote: true` |
| `refusal_correct` | ≥ 0.90 | rows with `expect_refusal` set |

---

## 3. Pre-flight validation (before P1 live eval)

Run once after P0 indexes corpus.

### 3.1 Environment check

```bash
test -n "$OPENROUTER_API_KEY" || echo "MISSING OPENROUTER_API_KEY"
cd backend && uv run python -c "from dharmiq.config.settings import get_settings; get_settings()"
docker compose ps postgres redis
```

### 3.2 Single-question eval spike

```bash
cd backend
# Temporarily trim v1_fundamental_rights to q1 only OR add --limit flag in P1
uv run dharmiq-eval --dataset v1_fundamental_rights --limit 1
```

**Pass:** Ragas + judge complete; JSON written under `data/eval/runs/`.

If Ragas fails (embedding download, API error), fix before P1 — do not proceed.

---

## 4. Phase P0 — Corpus bootstrap tooling + MVP index

### Goal

Index all 26 allowlist instruments; reproducible manifest; verification script.

### Tasks

| # | Task | Files |
|---|------|-------|
| 0.1 | `build_manifest.py` — read YAML allowlist → write `manifest.json` + print expected filenames | `backend/dharmiq/eval/tools/build_manifest.py` |
| 0.2 | `verify_corpus_index.py` — check each `id` in `source_documents.source_id`; report chunk counts | `backend/dharmiq/eval/tools/verify_corpus_index.py` |
| 0.3 | `tools/__init__.py` + `python -m dharmiq.eval.tools.build_manifest` CLI | same |
| 0.4 | Document operational download steps in tool `--help` and TRD smoke | |
| 0.5 | **Operational:** download PDFs via `indian-law-dataset-scraper`; copy to `data/corpus/india_code/raw/` | external |
| 0.6 | Run `build_manifest` → `sync_india_code_pdfs` | |
| 0.7 | Write `data/eval/runs/corpus_index_report.json` (doc counts, chunk counts, timestamp) | generated |

### `build_manifest.py` behavior

```bash
cd backend
uv run python -m dharmiq.eval.tools.build_manifest \
  --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --write
```

- For each instrument, emit manifest row with `source_id` = YAML `id`.
- **Filename convention:** `{slug}.pdf` where slug = lowercased `id` with `IN-` stripped and hyphens → underscores, e.g. `IN-CPA-2019` → `cpa_2019.pdf`.
- If PDF on disk uses different name, **rename PDF** to match manifest `file` field (binding for v0.5).
- `--write` creates/overwrites `manifest.json`.

### `verify_corpus_index.py` behavior

```bash
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml
```

- Exit **0** if all 26 `source_id` present and `chunk_count > 0` per document.
- Exit **1** with stderr listing missing/stale IDs.

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_build_manifest.py tests/test_verify_corpus_index.py -q
```

| Test | Assert |
|------|--------|
| `test_build_manifest_from_fixture_yaml` | Parses fixture YAML → expected JSON list length |
| `test_verify_fails_missing_docs` | DB without corpus → exit 1 |
| `test_verify_passes_when_seeded` | Seed `SourceDocument` rows → exit 0 |

**Manual (required for P0 done)**

```bash
# After PDF download + sync
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml
# Expect: 26/26 indexed
```

### Definition of done

- [ ] `build_manifest.py` and `verify_corpus_index.py` merged with unit tests
- [ ] MVP PDFs on disk; `manifest.json` generated
- [ ] `sync_india_code_pdfs` completed; `corpus_index_report.json` saved
- [ ] `verify_corpus_index` → 26/26

---

## 5. Phase P1 — Eval metadata + re-baseline

### Goal

Enrich eval run summaries; measure v0.4 stack; update baseline doc + `baseline.json`.

### Tasks

| # | Task | Files |
|---|------|-------|
| 1.1 | Add `collect_run_metadata()` — git sha, allowlist version/hash, corpus counts | `backend/dharmiq/eval/metadata.py` |
| 1.2 | Extend `run_eval_dataset` summary JSON with TRD-67 fields | `runner.py` |
| 1.3 | CLI `--limit N` (optional) for spike runs | `cli.py` |
| 1.4 | Run full `v1_fundamental_rights` (8 q) live eval; record results | operational |
| 1.5 | Update [`v02-eval-baseline.md`](../v02-eval-baseline.md) **measured** column for v0.4 stack | docs |
| 1.6 | If measured &lt; targets, add **Remediation** subsection — do **not** lower targets without PRD change | docs |
| 1.7 | `--write-baseline` stub (full impl in P5) or minimal write of single-dataset baseline | `cli.py` |

### `metadata.py` API

```python
async def collect_run_metadata(db: AsyncSession, *, settings: Settings) -> dict[str, str | int]:
    """Returns git_sha, allowlist_version, allowlist_sha256, corpus_document_count, corpus_chunk_count, dharmiq_version, eval_path."""
```

- `allowlist_sha256`: SHA-256 of `docs/plans/v0.5/mvp-corpus-allowlist.yaml` file bytes.
- `git_sha`: `git rev-parse HEAD` or `"unknown"` if not a git repo.

### Smoke tests

**Automated**

```bash
cd backend
uv run pytest tests/test_eval_metadata.py -q
```

**Manual (required)**

```bash
cd backend
uv run dharmiq-eval --dataset v1_fundamental_rights
# Inspect data/eval/runs/v1_fundamental_rights_*.json for TRD-67 fields
```

### Definition of done

- [ ] Summary JSON includes metadata block
- [ ] `v02-eval-baseline.md` has v0.4 measured row dated 2026-06-*
- [ ] Spike + full rights eval complete without error

---

## 6. Phase P2 — Dataset schema + loader + rights expansion

### Goal

Extend JSONL schema; expand `v1_fundamental_rights` to ≥30 questions.

### Schema additions (update `dataset_format.md`)

| Field | Type | Purpose |
|-------|------|---------|
| `required_source_ids` | string[] | Preflight: warn if not indexed (optional) |
| `must_not_cite_sections` | string[] | Revised-law answer check (TRD-56) |
| `source_type` | string | `statute` (default) |
| `locale` | string | `en` (default) |

### Tasks

| # | Task | Files |
|---|------|-------|
| 2.1 | Extend `EvalDatasetRecord` + loader validation | `dataset_loader.py` |
| 2.2 | Update `dataset_format.md` | docs |
| 2.3 | Expand `v1_fundamental_rights.jsonl` to ≥30 rows (owner-approved content) | `data/eval/datasets/` |
| 2.4 | Topics: police_arrest, constitutional_rights, rti — **not** consumer (move q4 to consumer dataset in P3) | data |
| 2.5 | Update `test_eval_dataset_loader.py` expected count | tests |
| 2.6 | `validate_dataset.py` tool — JSONL lint | `eval/tools/validate_dataset.py` |

### Rights expansion content rules

- Citizen plain-language questions.
- Every row: `expected_answer`, `expected_citations` with `section`.
- Statutory rows: `min_citation_count` ≥ 1; `expect_blockquote` true when quoting Constitution/BNSS.
- Include 2–3 RTI rows, 2–3 Article 21/14 rows, remainder police/BNSS.
- **Remove or relocate** q4 (consumer) to `v1_consumer` in P3.

### Smoke tests

```bash
cd backend
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_fundamental_rights
uv run pytest tests/test_eval_dataset_loader.py tests/test_validate_dataset.py -q
```

### Definition of done

- [ ] ≥30 rows in `v1_fundamental_rights.jsonl`
- [ ] Loader tests green
- [ ] `validate_dataset` passes

---

## 7. Phase P3 — Consumer + employment datasets

### Goal

Create `v1_consumer` (Grahak seed) and `v1_employment` (manual + templates).

### Tasks

| # | Task | Files |
|---|------|-------|
| 3.1 | `adapt_grahak_nyay.py` — read GeneralQA + SectoralQA → Dharmiq JSONL draft | `eval/tools/adapt_grahak_nyay.py` |
| 3.2 | Map to CPA 2019 sections; set `topic: consumer`; `min_citation_count: 1` | data |
| 3.3 | Owner review: drop forum-phone/procedural-only rows | manual |
| 3.4 | Commit `v1_consumer.jsonl` ≥30 rows | data |
| 3.5 | Author `v1_employment.jsonl` ≥30 rows (IDA, POWA, MWA, POSH, etc.) | data |
| 3.6 | Tests: loader smoke for both datasets | tests |

### Grahak adapter

```bash
export GRAHAK_NYAY_REPO=../GrahakNyay  # git clone https://github.com/ShreyGanatra/GrahakNyay.git
cd backend
uv run python -m dharmiq.eval.tools.adapt_grahak_nyay \
  --output ../data/eval/datasets/v1_consumer.draft.jsonl
```

- Input paths (adjust if repo layout differs): search for `GeneralQA`, `SectoralQA` JSON/CSV under clone.
- Output **draft** only; owner renames to `v1_consumer.jsonl` after review.
- Add `expected_citations: [{"section": "..."}]` manually or via mapping table in adapter for CPA sections.

### Employment authoring guide

| Topic | Acts (allowlist `id`) |
|-------|------------------------|
| Termination / dispute | IN-IDA-1947 |
| Unpaid wages | IN-POWA-1936 |
| Minimum wage | IN-MWA-1948 |
| Harassment | IN-POSH-2013 |
| Maternity | IN-MBA-1961 |
| Equal pay | IN-ERA-1976 |

### Smoke tests

```bash
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_consumer
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_employment
uv run pytest tests/test_eval_dataset_loader.py -q -k "consumer or employment"
```

### Definition of done

- [ ] `v1_consumer.jsonl` ≥30 committed
- [ ] `v1_employment.jsonl` ≥30 committed
- [ ] validate_dataset passes both

---

## 8. Phase P4 — Refusal, revised-law, needle + recall@5

### Goal

Adversarial datasets; implement `recall_at_5` metric.

### Tasks

| # | Task | Files |
|---|------|-------|
| 4.1 | `recall.py` — `compute_recall_at_k(chunks, expected_citations, k=5)` | `backend/dharmiq/eval/recall.py` |
| 4.2 | Wire into `_evaluate_question` when `expected_citations` non-empty | `runner.py` |
| 4.3 | Aggregate `recall_at_5` in `_aggregate_metrics` | `runner.py` |
| 4.4 | `revised_law.py` — `check_must_not_cite_sections(answer, sections)` | `eval/revised_law.py` |
| 4.5 | `v1_refusal_adversarial.jsonl` ≥20 rows | data |
| 4.6 | `v1_revised_law.jsonl` ≥15 rows (BNS not IPC; BNSS not CrPC; CPA 2019 not 1986) | data |
| 4.7 | `v1_needle_statute.jsonl` ≥20 rows with specific section targets | data |
| 4.8 | Tests | `tests/test_eval_recall.py`, `tests/test_revised_law.py` |

### `v1_refusal_adversarial.jsonl` categories

| Category | Example | `expect_refusal` |
|----------|---------|------------------|
| Fictitious statute | q8-style Intergalactic Trade Act | true |
| Off-topic | “Recipe for biryani” | true |
| Wrong domain indexed | Question about US law only | true |
| Valid (control) | Normal rights question | false |

### `v1_revised_law.jsonl` pattern

```json
{
  "id": "rl1",
  "question": "What is the punishment for theft under current Indian criminal law?",
  "expected_answer": "... cite BNS provisions ...",
  "expected_citations": [{"section": "Bharatiya Nyaya Sanhita"}],
  "must_not_cite_sections": ["Indian Penal Code", "IPC", "Section 379 IPC"],
  "topic": "criminal",
  "expect_refusal": false,
  "min_citation_count": 1
}
```

### `v1_needle_statute.jsonl` pattern

- Questions targeting **specific section numbers** in long acts (Constitution, BNSS, IDA).
- `expected_citations` required for recall@5.

### Smoke tests

```bash
uv run pytest tests/test_eval_recall.py tests/test_revised_law.py -q
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_refusal_adversarial
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_revised_law
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_needle_statute
```

### Definition of done

- [ ] recall@5 in eval JSON for citation-bearing rows
- [ ] Three datasets committed and validated
- [ ] Unit tests for recall + revised-law checks

---

## 9. Phase P5 — Benchmark harness

### Goal

`--suite mvp`, `--compare baseline`, `--write-baseline`; MVP rollup metrics.

### Tasks

| # | Task | Files |
|---|------|-------|
| 5.1 | `suite.py` — `MVP_DATASETS` list + `run_mvp_suite()` | `backend/dharmiq/eval/suite.py` |
| 5.2 | `compare.py` — load baseline, diff metrics, exit code | `backend/dharmiq/eval/compare.py` |
| 5.3 | CLI flags: `--suite mvp`, `--compare [NAME]`, `--write-baseline` | `cli.py` |
| 5.4 | `baseline.json` schema — see §9.1 | data |
| 5.5 | Tests with fixture baseline | `tests/test_eval_compare.py` |

### 5.1 `baseline.json` schema

```json
{
  "created_at": "2026-06-22T12:00:00Z",
  "git_sha": "abc123",
  "allowlist_version": "1",
  "allowlist_sha256": "...",
  "eval_path": "run_eval_rag",
  "model": "deepseek/deepseek-v4-flash",
  "suites": {
    "mvp": {
      "aggregate_metrics": {
        "faithfulness": 0.86,
        "answer_correctness": 0.81,
        "llm_citation_correctness": 0.96,
        "recall_at_5": 0.78,
        "blockquote_met": 0.82,
        "refusal_correct": 0.91,
        "question_count": 155
      },
      "datasets": {
        "v1_fundamental_rights": { "aggregate_metrics": { "...": 0.0 } }
      }
    }
  }
}
```

### 5.2 MVP suite dataset order (TRD-58)

```python
MVP_DATASETS = [
    "v1_fundamental_rights",
    "v1_consumer",
    "v1_employment",
    "v1_refusal_adversarial",
    "v1_revised_law",
    "v1_needle_statute",
]
```

### Compare behavior

```bash
uv run dharmiq-eval --suite mvp --compare baseline
```

1. Run all MVP datasets sequentially (continue on single-dataset failure; mark failed in summary).
2. Compute weighted aggregate across all questions.
3. Load `data/eval/runs/baseline.json` → `suites.mvp.aggregate_metrics`.
4. Print delta table stdout.
5. Exit **1** if TRD-54 violated or any target in TRD-70 violated.
6. Exit **0** otherwise.

**Advisory:** exit code is for human/operator use only in v0.5.

### Write baseline

```bash
uv run dharmiq-eval --suite mvp --write-baseline
```

Overwrites `data/eval/runs/baseline.json` with latest MVP run (prompt confirm on stdin in interactive; `--yes` flag for scripts).

### Smoke tests

```bash
uv run pytest tests/test_eval_compare.py tests/test_eval_suite.py -q
```

### Definition of done

- [ ] `--suite mvp` runs all 6 datasets
- [ ] `--compare baseline` works with fixture baseline
- [ ] `baseline.json` committed after first passing MVP run (or measured partial with remediation note)

---

## 10. Phase P6 — E2E smoke extension + docs + version bump

### Goal

Extend smoke test; finalize flow matrix + runbook; bump version.

### Tasks

| # | Task | Files |
|---|------|-------|
| 6.1 | Extend `test_v02_e2e_smoke.py`: after chat, `GET /api/account/export`, assert JSON shape | tests |
| 6.2 | Register **second** disposable user OR export then `DELETE /api/account` with email+password on same user at end | tests |
| 6.3 | Prefer **separate test** `test_v05_export_delete_smoke` in same file to keep original test stable | tests |
| 6.4 | [`flow-coverage-matrix.md`](./flow-coverage-matrix.md) — already created; verify rows | docs |
| 6.5 | [`manual-test-runbook.md`](./manual-test-runbook.md) — already created; link from README | docs |
| 6.6 | Bump `__version__` to `0.5.0` | `dharmiq/__init__.py` |
| 6.7 | Update README eval section with suite/compare commands | `README.md` |
| 6.8 | Mark PRD exit criteria checkboxes | `prd.md` |

### Export/delete smoke spec

```python
@pytest.mark.asyncio
async def test_v05_export_delete_smoke(client, unique_email, ...):
    # 1. register/login (unique_email)
    # 2. create session + one message (optional)
    # 3. GET /api/account/export → 200, user.email match
    # 4. DELETE /api/account {"email", "password"} → 204/200
    # 5. subsequent GET export → 401
```

Use patterns from `tests/test_account_privacy.py`.

### Smoke tests

```bash
cd backend && uv run pytest tests/test_v02_e2e_smoke.py -q
```

### Definition of done

- [ ] Export/delete smoke green
- [ ] Flow matrix + runbook linked
- [ ] Version 0.5.0
- [ ] Full manual runbook executed once

---

## 11. Phase P7 — BhashaBench weak indicator (optional)

### Goal

Optional quarterly MCQ sample; log only.

### Tasks

| # | Task | Files |
|---|------|-------|
| 7.1 | `bhashabench_sample.py` — load HF dataset subset (constitutional, consumer, employment tags) | `eval/tools/bhashabench_sample.py` |
| 7.2 | Run MCQ through **no RAG** model call OR skip model — **binding:** only **count** questions per domain + log sample IDs (no automated MCQ scoring in v0.5) | |
| 7.3 | Append markdown section to `data/eval/runs/bhashabench_log.md` | data |

**Simpler binding for v0.5:** script documents how to run BhashaBench externally + template log entry — **no HF dependency required** if `datasets` install is heavy. Implement **log template + README section** only unless owner requests full HF integration.

### Smoke tests

```bash
uv run python -m dharmiq.eval.tools.bhashabench_sample --dry-run
```

### Definition of done

- [ ] Dry-run prints sample plan
- [ ] `datasets.md` §5.3 cross-link satisfied

---

## 12. CLI reference (post v0.5)

```bash
cd backend

# Single dataset
uv run dharmiq-eval --dataset v1_fundamental_rights
uv run dharmiq-eval --dataset v1_fundamental_rights --limit 5

# MVP suite
uv run dharmiq-eval --suite mvp
uv run dharmiq-eval --suite mvp --write-baseline --yes
uv run dharmiq-eval --suite mvp --compare baseline

# Corpus tools
uv run python -m dharmiq.eval.tools.build_manifest --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml --write
uv run python -m dharmiq.eval.tools.verify_corpus_index --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_consumer
```

---

## 13. Agent prompt templates

Copy-paste when spawning an agent for **one phase only**.

### Template

```text
Implement Dharmiq v0.5 phase {PHASE_ID} from docs/plans/v0.5/trd.md.

Rules:
- Read docs/plans/v0.5/prd.md and trd.md §2 binding decisions first
- Implement ONLY this phase's tasks
- Match existing code style in backend/dharmiq/
- Run phase smoke tests listed in trd.md for {PHASE_ID}
- Run global smoke gate (ruff + pytest -m "not slow" + frontend lint)
- Do not commit unless asked
- Do not add GitHub Actions
- Eval path: run_eval_rag only

Phase: {PHASE_ID} — {PHASE_NAME}
```

### Example (P4)

```text
Implement Dharmiq v0.5 phase P4 from docs/plans/v0.5/trd.md.
Add recall_at_5 metric, revised-law section checks, and three JSONL datasets
(refusal, revised_law, needle). Files: backend/dharmiq/eval/recall.py,
revised_law.py, runner.py, data/eval/datasets/*.jsonl, tests.
Run smoke tests in trd.md §8.
```

---

## 14. Final smoke test (v0.5 ship)

```bash
# 1. Global automated
docker compose up -d postgres redis
cd backend && uv sync --dev && uv run alembic upgrade head
uv run ruff check .
uv run pytest -m "not slow" -q
cd ../frontend && npm ci && npm run lint && npm run build

# 2. Corpus
cd backend
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml

# 3. Live eval (advisory; needs OPENROUTER_API_KEY)
uv run dharmiq-eval --suite mvp --compare baseline

# 4. Sign manual-test-runbook.md
```

---

## 15. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| IndiaCode PDF download fails | Manual PDF placement; verify script blocks P1 |
| Ragas non-deterministic | TRD-54 delta; run compare on same machine |
| Grahak repo layout changes | Adapter documents paths; fail with clear error |
| recall@5 noisy | Tune section strings; needle dataset audit |
| Eval cost | `--limit` for dev; full suite only before release |
| q6 CrPC vs BNSS confusion | `v1_revised_law` dataset isolates supersession |

---

## 16. Document history

| Date | Change |
|------|--------|
| 2026-06-22 | Initial TRD from PRD + codebase inspection |

---

*When v0.5 ships: update [`roadmap.md`](../roadmap.md), [`README.md`](../../../README.md), mark PRD exit criteria.*
