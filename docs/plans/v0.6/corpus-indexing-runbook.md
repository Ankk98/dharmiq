# v0.6 — Corpus indexing runbook

**Parent:** [`prd.md`](./prd.md) §9 · [`trd.md`](./trd.md) §3.4 · [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml)  
**When:** After v0.5 operational exit; before `dharmiq-eval --suite v06` sign-off or v0.6 tag.

This runbook covers **central IndiaCode PDF acquisition**, manifest generation, Celery sync, verification, and rollback for the **62-instrument** v0.6 allowlist (Appendix A only — 16 deferred rules in Appendix B are out of scope).

---

## 1. Prerequisites

| Requirement | Notes |
|-------------|-------|
| Docker | Postgres + Redis (`docker compose up -d`) |
| Celery worker | `cd backend && uv run celery -A celery_app worker --loglevel=info` |
| RAM | **16 GB recommended** for full Tier A index (see [`data-implementation.md`](../data-implementation.md)) |
| Disk | **~100 GB** recommended (`data/corpus/`, Postgres volume) |
| Migrations | `cd backend && uv run alembic upgrade head` |
| v0.5 exit | MVP 26/26 indexed; manual smoke runbook executed ([`v0.5/manual-test-runbook.md`](../v0.5/manual-test-runbook.md)) |
| Allowlist | [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml) — 62 instruments, 6 domains |
| Network | Live IndiaCode HTTP for `download_indiacode_pdfs` (scraper `pdfs_dir` is empty in validated dev) |

```bash
# From repo root
docker compose up -d postgres redis
cd backend && uv sync --dev && uv run alembic upgrade head
```

---

## 2. PDF acquisition (TRD §3.4)

**Primary path:** `download_indiacode_pdfs.py` — no scraper PDFs required.

```text
For each allowlist instrument (62 rows — Appendix A only):
  1. Read pdf_source from YAML (default bitstream for acts)
  2. bitstream: canonical_url → parse bitstream; prefer *eng* filename
  3. parent_view_file / subset: GET pdf_url directly (exact href, keep &file=)
  4. bundle: GET pdf_url or bitstream on bundle handle
  5. Validate %PDF and size ≥ 5000 bytes
  6. Save as data/corpus/india_code/raw/{slug}.pdf  (TRD-81)
  7. build_manifest --write
  8. sync_india_code_pdfs (Celery)
```

**Manual fallback:** browser download from bitstream URL if automated tool fails (rate limit / block). Place the file under `data/corpus/india_code/raw/` using the slug from `build_manifest --dry-run`, then re-run manifest + sync.

### Probe before full download

```bash
cd backend

# Probe bitstream URLs without writing (no DB)
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --probe --limit 3

# Verify all canonical_url pages reachable
uv run python -m dharmiq.eval.tools.audit_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --verify-handles
```

**Validated probe targets (minimum):** `IN-CPA-2019` (handle `15256`), `IN-BNS-2023` (`20062`), `IN-DPDP-2023` (`22037`).

### Download all PDFs

```bash
cd backend
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --write
```

Optional scraper fallback (only if `instrument_version_files > 0` in scraper DB):

```bash
cd ~/repos/indian-law-dataset-scraper
indiacode download --scope central --resume
# Then:
cd backend
uv run python -m dharmiq.eval.tools.import_corpus_pdfs --copy-pdfs ...
```

Known rule PDF gaps: see [`rule-probe-results.json`](./rule-probe-results.json) and TRD Appendix B (16 deferred rules).

---

## 3. build_manifest → sync → verify

Full indexing workflow:

```bash
cd backend

# 1. Generate manifest.json from allowlist + on-disk PDFs
uv run python -m dharmiq.eval.tools.build_manifest \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --write

# 2. Index via Celery (ensure worker is running)
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
# Wait for worker log: corpus_sync_complete

# 3. Verify 62/62 indexed + chunk budget
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --write-report
```

**Pass criteria:**

- Exit code **0** from `verify_corpus_index`
- `indexed_document_count` = **62**
- Every row: `chunk_count > 0` and PDF on disk
- `corpus_chunk_count` ≤ **250000** (`chunk_budget_ok: true`)

```bash
python3 -c "
import json
r = json.load(open('../data/eval/runs/corpus_index_report.json'))
assert r['indexed_document_count'] == 62, r
assert r['corpus_chunk_count'] <= 250_000, r
print('OK:', r['corpus_chunk_count'], 'chunks')
"
```

Spot-check temporal fields in DB (5 documents):

```sql
SELECT source_id, status, enactment_date, enforcement_date, canonical_url
FROM source_documents
WHERE source_id IN ('IN-BNS-2023', 'IN-DPDP-2023', 'IN-RERA-2016', 'IN-ITA-1961', 'IN-IPC-1860')
ORDER BY source_id;
```

Verify statute relationship seeds:

```sql
SELECT COUNT(*) FROM statute_relationships;
-- Expect ≥ 3 (IPC→BNS, CrPC→BNSS, CPA 1986→2019)
```

---

## 4. Add one instrument

To add a new central instrument (within allowlist cap — max 110 without PRD amendment):

1. **Edit allowlist** — add row under the correct `domains.*.instruments` block in [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml) with `id`, `title`, `doc_type`, `status`, `canonical_url`, `pdf_source`, etc.
2. **Audit** — `uv run python -m dharmiq.eval.tools.audit_allowlist --allowlist ...`
3. **Acquire PDF** — `download_indiacode_pdfs --write` (or manual drop-in)
4. **Manifest** — `build_manifest --write`
5. **Sync** — `celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs`
6. **Verify** — `verify_corpus_index --allowlist ...`
7. **Eval** — update dataset `required_source_ids` if gating; run `validate_dataset` + smoke eval

---

## 5. Update instrument (new PDF version)

When IndiaCode publishes an amended PDF:

1. Back up current PDF + `manifest.json` (see §7)
2. Replace PDF in `data/corpus/india_code/raw/` (or re-download with `--write`)
3. `build_manifest --write` — content hash change creates a new `version` row
4. `sync_india_code_pdfs` — pipeline registers new version; old version chunks remain but retrieval prefers latest version per `source_id`
5. `verify_corpus_index` — confirm chunk count and budget
6. Run `dharmiq-eval --suite mvp --compare baseline` (regression) and `--suite v06` if domain affected

---

## 6. Remove instrument

1. Remove or comment out the row in allowlist YAML (document reason in PR)
2. Remove PDF from `raw/` (optional — orphan PDFs are ignored if not in manifest)
3. `build_manifest --write`
4. For hard purge: delete `source_documents` / `document_chunks` for that `source_id` via admin SQL (no UI in v0.6) — **prefer soft-delete** by setting `status: repealed` and excluding from retrieval
5. Audit eval datasets: `grep` for `source_id` in `data/eval/datasets/*.jsonl`
6. `verify_corpus_index` on updated allowlist

---

## 7. Rollback

If indexing fails or chunk budget is exceeded:

1. **Stop** Celery worker if sync is mid-flight
2. Restore previous `data/corpus/india_code/raw/` and `manifest.json` from git or timestamped backup:

```bash
cp -a /path/to/backup/raw/* data/corpus/india_code/raw/
cp /path/to/backup/manifest.json data/corpus/india_code/raw/manifest.json
```

3. Re-run `sync_india_code_pdfs` + `verify_corpus_index`
4. If DB is corrupted: restore Postgres snapshot or re-sync from clean manifest on empty `source_documents` for corpus scope (destructive — staging only)

---

## 8. Metrics to log

Record these in `data/eval/runs/corpus_index_report.json` (via `--write-report`) and operator notes before v0.6 sign-off:

| Metric | Source |
|--------|--------|
| `corpus_chunk_count` | `verify_corpus_index --write-report` |
| `corpus_document_count` | same report |
| `indexed_document_count` / `expected_document_count` | same report (target **62/62**) |
| `chunk_budget_ok` | same report |
| `allowlist_version` | YAML `version` field (`1`) |
| `allowlist_sha256` | eval run metadata (`dharmiq-eval`) |
| `pg_database_size` | `SELECT pg_size_pretty(pg_database_size(current_database()));` |

Example:

```bash
psql -h localhost -p 5433 -U dharmiq -d dharmiq \
  -c "SELECT pg_size_pretty(pg_database_size(current_database()));"
```

---

## 9. Chunk budget stop rule (TRD-93)

After P3 indexing, if `corpus_chunk_count` **exceeds 250,000**:

1. **Stop** — do not tune chunk sizes or embeddings first
2. **Rescope** allowlist (remove lowest-priority instruments or defer rules)
3. Re-index and re-verify
4. Document decision in PR if rules were deferred

The verify tool enforces this by default (`--max-chunks 250000`).

---

## 10. Post-index eval gate

Requires indexed corpus + `OPENROUTER_API_KEY`:

```bash
cd backend
uv run dharmiq-eval --suite v06 --compare baseline
uv run dharmiq-eval --suite mvp --compare baseline   # MVP regression
```

After passing: `uv run dharmiq-eval --suite v06 --write-baseline --yes` — merges `suites.v06` into `data/eval/runs/baseline.json` without dropping `suites.mvp`.

---

## 11. Related docs

| Doc | Purpose |
|-----|---------|
| [`trd.md`](./trd.md) §13 | Full CLI reference |
| [`licensing-checklist.md`](./licensing-checklist.md) | Attribution + founder sign-off |
| [`rule-probe-results.json`](./rule-probe-results.json) | Deferred rules, probe outcomes |
| [`data-implementation.md`](../data-implementation.md) | Schema, scale limits |
| [`v0.5/manual-test-runbook.md`](../v0.5/manual-test-runbook.md) | Pre-requisite v0.5 gate |
