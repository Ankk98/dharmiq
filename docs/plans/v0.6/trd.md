# Dharmiq v0.6 — Technical Requirements & Implementation Plan

**Status:** Code complete (P0–P8); operational gates pending (62/62 index, live eval, licensing sign-off)  
**Version:** 0.6  
**Parent doc:** [`prd.md`](./prd.md)  
**Baseline:** v0.5 — MVP allowlist tooling, six gating eval datasets, `--suite mvp`, advisory baseline compare  
**Last updated:** 2026-06-23 (PDF download validation added)

Related: [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml) (P0 deliverable) · [`rule-probe-results.json`](./rule-probe-results.json) · [`corpus-indexing-runbook.md`](./corpus-indexing-runbook.md) (P8)

---

## How to use this document

1. **Read §2 binding decisions first.** They override ambiguous PRD wording.
2. **Read §3 pre-flight validation** — scraper/PDF constraints are environment-specific; do not skip.
3. **One phase at a time.** Do not start phase N+1 until that phase’s smoke tests pass.
4. **Preserve v0.5 behavior** except where this TRD explicitly changes corpus, retrieval, eval, or answer footnotes.
5. **Match existing conventions:** async SQLAlchemy, Pydantic v2, pytest-asyncio, structlog, YAML config in `config/`, modules under `backend/dharmiq/`.
6. **Every phase ends with:** code/docs + tests + smoke command block.
7. **Do not commit** unless the user asks.
8. **No GitHub Actions in v0.6** — manual gates only (same as v0.5).
9. **Eval path:** `run_eval_rag()` only — not full LangGraph (v0.7).

### Global smoke gate (after every phase)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest -m "not slow" -q
cd frontend && npm run lint
```

### Phase dependency graph

```text
Pre-flight (§3) ──► P0 ──► P1 ──► P2 ──► P3* ──► P4 ──► P5 ──► P6 ──► P7 ──► P8
                              │      │
                              │      └── retrieval + revised-law tests (fixture DB)
                              └── schema + ingestion temporal fields
* P3 operational indexing — BLOCKED until v0.5 exit (§3.3) AND PDFs on disk
```

| ID | Name | Depends on | Est. |
|----|------|------------|------|
| **P0** | Allowlist YAML + audit + **`download_indiacode_pdfs`** | Pre-flight | 2 d |
| **P1** | DB migration + manifest/scanner/pipeline temporal fields | P0 | 2 d |
| **P2** | `statute_relationships` + retrieval filters (status + latest version) | P1 | 2 d |
| **P3** | Corpus PDF materialize + full index + verify (operational) | P0, P1, P2, v0.5 exit | 2–4 d |
| **P4** | Eval datasets (`v1_property`, `v1_tax`, `v1_cyber`) + needle extend | P0 | 2 d |
| **P5** | `--suite v06` + baseline merge/compare | P4 | 1 d |
| **P6** | As-of footnote (answerer + finalizer + eval) | P1 | 1 d |
| **P7** | Citation `canonical_url` attribution (API + frontend) | P1 | 1 d |
| **P8** | Runbooks, licensing checklist, docs, version `0.6.0` | P3–P7 | 1 d |

---

## 1. Current codebase snapshot (v0.5)

Verify paths before editing.

### 1.1 Corpus & ingestion

| Area | Path | v0.5 state |
|------|------|------------|
| Scanner | `backend/dharmiq/ingestion/scanner.py` | Reads `manifest.json`: `source_id`, `title`, `doc_type`, `jurisdiction` only |
| Pipeline register | `backend/dharmiq/ingestion/pipeline.py` | `_register_scanned_document` ignores `enactment_date` from manifest; creates new `version` row on hash change; **does not delete old version chunks** |
| `SourceDocument` model | `backend/dharmiq/db/models/documents.py` | Has `enactment_date`, `version`; **no** `status`, `canonical_url`, `enforcement_date` |
| Allowlist loader | `backend/dharmiq/eval/tools/allowlist.py` | `AllowlistInstrument` — 7 fields; no `status` / supersession |
| `build_manifest.py` | `backend/dharmiq/eval/tools/build_manifest.py` | Emits basic manifest rows; default allowlist = v0.5 MVP path |
| `verify_corpus_index.py` | `backend/dharmiq/eval/tools/verify_corpus_index.py` | Checks `source_id` + chunk count; default allowlist = v0.5 |
| Hybrid retrieval | `backend/dharmiq/retrieval/hybrid.py` | No `status` filter; no “latest version per source_id” filter |
| Corpus PDFs (dev) | `data/corpus/india_code/raw/` | **3 PDFs** with non-standard filenames (not MVP-ready) |

### 1.2 Eval stack

| Area | Path | v0.5 state |
|------|------|------------|
| CLI | `backend/dharmiq/eval/cli.py` | `--suite mvp` only; `--compare` requires `mvp` |
| Suite | `backend/dharmiq/eval/suite.py` | `MVP_DATASETS` (6 datasets); no `v06` |
| Baseline | `backend/dharmiq/eval/baseline.py` | Writes `suites.mvp` only |
| Compare | `backend/dharmiq/eval/compare.py` | `load_baseline_metrics(..., suite="mvp")` hardcoded in CLI |
| Metadata | `backend/dharmiq/eval/metadata.py` | `default_allowlist_path()` → v0.5 MVP YAML |
| `validate_dataset.py` | `backend/dharmiq/eval/tools/validate_dataset.py` | Minimum counts for 6 MVP datasets only |
| Datasets committed | `data/eval/datasets/` | 6 files, 149 rows total; **no** property/tax/cyber |

### 1.3 Agent / answer path

| Area | Path | v0.5 state |
|------|------|------------|
| Answerer | `backend/dharmiq/llm/agents/answerer.py` | No corpus footnote |
| Finalizer | `backend/dharmiq/agents/nodes/finalizer.py` | Persists `final_answer`; no footnote |
| Refusal | `backend/dharmiq/agents/nodes/refusal.py` | Fixed `REFUSAL_MESSAGE` — footnote must **not** apply |
| Citation enricher | `backend/dharmiq/agents/citation_validation.py` | No `canonical_url` on `CitationRecord` |
| Citation schema | `backend/dharmiq/schemas/citations.py` | No `canonical_url` |

### 1.4 Version

| File | Value |
|------|-------|
| `backend/dharmiq/__init__.py` | `0.6.0` |
| `backend/pyproject.toml` | `0.6.0` |
| `frontend/package.json` | `0.6.0` |

### 1.5 `indian-law-dataset-scraper` (validated 2026-06-23)

| Check | Result |
|-------|--------|
| SQLite at `~/repos/indian-law-dataset-scraper/data/indiacode.sqlite3` | **Exists** — metadata only |
| Central instruments in SQLite | **843** |
| `instrument_versions` / PDF files for central | **0** / **0** |
| CSV `current_content_url` populated | **0** rows |
| `relationships` table | **0** rows |
| `pytest` in scraper repo | **13 failures** (CLI/discovery/http) — **do not gate Dharmiq on scraper tests** |
| BNS/BNSS rows | `type=subordinate` (not `act`) — use allowlist `doc_type`, not scraper `type` |
| RERA row | `instrument_id=247`, `type=regulation` |
| MVP `scraper_instrument_id` values in SQLite | **16/22** found |

**Conclusion:** Scraper is useful for **metadata enrichment** (`canonical_url`, dates, title) when `scraper_instrument_id` matches the correct row. **Do not use `instrument_id` as `india_code_handle`.** PDF acquisition uses **live IndiaCode HTTP** (§1.6, §3.5) — scraper `pdfs_dir` is empty in validated dev.

### 1.6 Live PDF download validation (2026-06-23)

Tested HTTP fetch from IndiaCode (not scraper `download`). **Acts with correct `canonical_url` handles work.**

| `source_id` | `india_code_handle` | Page | Bitstream PDF | Size |
|-------------|---------------------|------|---------------|------|
| `IN-CPA-2019` | `15256` | 200 OK | `.../bitstream/123456789/15256/1/eng201935.pdf` | 450 KB |
| `IN-BNS-2023` | `20062` | 200 OK | `.../bitstream/123456789/20062/1/a202345.pdf` | 896 KB |
| `IN-DPDP-2023` | **`22037`** (not `350`) | 200 OK | `.../bitstream/123456789/22037/1/a2023-22.pdf` | 382 KB |
| `IN-CPA-RULES-ECOMMERCE-2020` | `11445` (invalid guess) | **302** | — | **Not on IndiaCode** — see §1.7 |

**Binding patterns:**

1. **Handle page:** `https://www.indiacode.nic.in/handle/123456789/{handle}`
2. **Bitstream PDF:** parse HTML for `/bitstream/123456789/{handle}/{seq}/{filename}.pdf`
3. **English PDF:** prefer bitstream whose filename contains `eng` (case-insensitive); else first `.pdf` bitstream for that handle
4. **`scraper_instrument_id` ≠ handle** — e.g. DPDP `instrument_id=350`, handle=`22037`. Derive handle **only** from `canonical_url` path or `india_code_handle` field
5. **Rule rows** do not use separate handles — use `pdf_source` + `pdf_url` on parent act page (§1.7, TRD-105)

**Implication:** P0 ships `download_indiacode_pdfs.py` (HTTP bitstream fetch), not scraper PDF copy as primary path.

### 1.7 Rule PDF validation (2026-06-23)

Full probe of **30** candidate rule/notification rows; **14 committed** in v0.6 (Appendix A), **16 deferred** (Appendix B). Artifact: [`rule-probe-results.json`](./rule-probe-results.json). Re-run: `python3 scripts/probe_v06_rules.py`.

| Outcome | Count | Meaning |
|---------|-------|---------|
| **VERIFIED** / **BUNDLE** | 10 | Distinct `%PDF` URL confirmed |
| **SUBSET** | 4 | Shares PDF with another row (GST invoice/return/refund/assessment → CGST Rules Part A) |
| **NOT_ON_INDIACODE** | 14 | No central PDF on IndiaCode parent page (CPA 2020 rules, CLRA central, ITR Rules, etc.) |
| **UT_ONLY** | 2 | RERA parent has UT rules only |

**v0.6 scope decision (binding):** **16 rule/notification rows** without a verified IndiaCode PDF are **deferred** — not in `central-corpus-allowlist.yaml`. See **Appendix B**. v0.6 ships **62** instruments (26 MVP + 36 new), each with a PDF path. Eval datasets must not use deferred `id`s as `required_source_ids` until a later release.

**Rule sourcing patterns (binding for committed rows):**

| `pdf_source` | When | `canonical_url` | `pdf_url` |
|--------------|------|-----------------|-----------|
| `bitstream` | Act-style own handle | Self handle | Parsed bitstream |
| `parent_view_file` | Rule PDF on parent act page | **Parent act** handle | Full `ViewFileUploaded?...&file=...` href |
| `bundle` | Act+rules combined PDF | Bundle handle (e.g. POSH **9178**) | Bitstream on bundle handle |
| `subset` | Logical rule; text in another PDF | Parent handle | Same as `shared_pdf_with` row |

**Critical:** `--verify-handles` alone is **insufficient** for rules. Many verified rules have no bitstream on their row’s handle. Use `--verify-pdf-sources` (TRD-107) on **every** committed row.

---

## 2. Binding decisions (implementation hardening)

Do not deviate without updating this doc and [`prd.md`](./prd.md).

| ID | Topic | Decision |
|----|-------|----------|
| **TRD-71** | Scraper PDF dependency | **Never required.** Primary: `download_indiacode_pdfs.py` (HTTP bitstream). Optional `--copy-pdfs` from scraper only when `instrument_version_files > 0`. |
| **TRD-72** | Scraper metadata | Optional `--enrich-from-scraper` reads SQLite by `scraper_instrument_id`; **canonical_url in allowlist is authoritative** over scraper URLs. |
| **TRD-73** | Central-only | Allowlist `jurisdiction` must be `central`; bridge rejects rows whose `canonical_url` lacks `/handle/123456789/`. |
| **TRD-74** | Allowlist file | `docs/plans/v0.6/central-corpus-allowlist.yaml` — **superset** of MVP 26; MVP `id` values unchanged. |
| **TRD-75** | Instrument count | **62 committed** instruments (26 MVP + 36 new) — see §Appendix A. **16 rules deferred** to Appendix B (no IndiaCode PDF). Original 78-target documented for v0.7+. |
| **TRD-76** | `InstrumentStatus` | Enum: `in_force`, `superseded`, `repealed`. DB default `in_force` for NULL legacy rows. |
| **TRD-77** | Superseded in retrieval | Exclude `superseded` and `repealed` from corpus search when `retrieval.include_superseded=false` (default). **Still indexed** for audit; excluded at query time. |
| **TRD-78** | Latest document version | Retrieval joins **only** the row with `max(version)` per `source_id` among documents with `indexed_at IS NOT NULL`. |
| **TRD-79** | Amendment graph storage | Postgres table `statute_relationships` (not JSONB-only). Seed from allowlist `supersedes` / `superseded_by` at sync time. |
| **TRD-80** | `manifest.json` schema v0.6 | Extend TRD-59 array entries with: `status`, `enactment_date`, `enforcement_date`, `canonical_url`, `superseded_by` (optional), `scraper_instrument_id` (optional). |
| **TRD-81** | Filename convention | Unchanged: `source_id_to_filename()` in `allowlist.py` — `IN-CPA-2019` → `cpa_2019.pdf`. |
| **TRD-82** | Rules in v0.6 | **14 rule rows** committed (10 distinct PDFs + 4 GST subset aliases). **16 deferred** — Appendix B. PDF URLs in [`rule-probe-results.json`](./rule-probe-results.json). |
| **TRD-83** | Eval path | `run_eval_rag()` only; metadata `eval_path` unchanged. |
| **TRD-84** | `--suite v06` | Runs `MVP_DATASETS` + `v1_property`, `v1_tax`, `v1_cyber` in that order. |
| **TRD-85** | Baseline schema | `baseline.json` may contain **both** `suites.mvp` and `suites.v06`. `--write-baseline` with `--suite v06` updates/adds `suites.v06` **without deleting** `suites.mvp`. |
| **TRD-86** | Compare suite | `--compare baseline` uses suite name matching `--suite` (`mvp` → `suites.mvp`, `v06` → `suites.v06`). |
| **TRD-87** | Regression deltas | Same TRD-54 as v0.5: float ±0.02, boolean ±0.05. Add `revised_law_met` to boolean regression set. |
| **TRD-88** | New dataset minimums | `v1_property` ≥15, `v1_tax` ≥15, `v1_cyber` ≥15 rows. |
| **TRD-89** | Needle extension | Append **≥10** rows to `v1_needle_statute.jsonl` (single file) with `topic` in `property`, `tax`, or `cyber`. |
| **TRD-90** | Footnote text | Exact template in §9.1; idempotent (`Sources indexed:` marker). |
| **TRD-91** | Footnote scope | Append for normal answers only — **not** `REFUSAL_MESSAGE`, **not** `VALIDATION_FAILED_MESSAGE`. |
| **TRD-92** | Corpus index date | `max(source_documents.indexed_at)` UTC date; fallback `unknown` if no indexed docs. |
| **TRD-93** | Chunk budget | After P3, `corpus_chunk_count` ≤ **250000** or **stop** and rescope allowlist (do not tune chunk sizes first). |
| **TRD-94** | P3 gate | Requires v0.5 operational exit (§3.3) **and** `verify_corpus_index --allowlist central` → **62/62** (every Appendix A row has PDF on disk + chunks). |
| **TRD-95** | Citation attribution | Add optional `canonical_url` to `CitationRecord` + API JSON; frontend shows “View on IndiaCode” when set. |
| **TRD-96** | Alembic revision | `012_v06_corpus_temporal.py` — next after `011_v04_foundation.py`. |
| **TRD-97** | Config | Add `corpus.default_allowlist_path` and `retrieval.include_superseded` to `config/*.yaml`. |
| **TRD-98** | Old document versions | On new version insert for same `source_id`, **delete chunks** for older `document_id` rows (same `source_id`, lower `version`). |
| **TRD-99** | Handle vs instrument_id | **`india_code_handle` is the numeric path segment in `canonical_url`**, never the scraper `instrument_id`. Example: DPDP `instrument_id=350`, handle=`22037`. |
| **TRD-100** | Primary PDF tool | `download_indiacode_pdfs.py` — `bitstream`, `parent_view_file`, `bundle`, `subset` modes (TRD-105). HTTP to IndiaCode; scraper `--copy-pdfs` optional fallback only. |
| **TRD-101** | Handle verification | `audit_allowlist --verify-handles` GETs each `canonical_url`; exit **1** if status ≠ 200. Required before P3. |
| **TRD-102** | Bitstream probe | `download_indiacode_pdfs.py --probe` (or `--dry-run`) prints bitstream URL per instrument without writing files. |
| **TRD-103** | Scraper enrich handles | `enrich_allowlist_from_scraper` must set `india_code_handle` from SQLite `canonical_url` when YAML handle empty/wrong — **never** copy `instrument_id` to handle. |
| **TRD-104** | ~~Unverified rule handles~~ | **Superseded by TRD-105–110.** Guessed handles `11445` etc. were invalid; rules use `parent_view_file` or `bundle`, not separate handles. |
| **TRD-105** | `pdf_source` field | Required for `doc_type` ∈ `{rule, notification}` in committed YAML: `parent_view_file`, `bundle`, or `subset`. Acts default `bitstream`. |
| **TRD-106** | `pdf_url` field | Required when `pdf_source` ∈ `{parent_view_file, bundle, subset}`. Store **exact** IndiaCode href (with `&file=`). |
| **TRD-107** | `--verify-pdf-sources` | `audit_allowlist` mode: GET each row’s resolved PDF URL; require `%PDF` and size ≥ 5000 bytes. Exit **1** on failure. Applies to **all 62** committed rows. |
| **TRD-108** | Rule `canonical_url` | For `parent_view_file` / `subset`: `canonical_url` = **parent act** handle URL. `id` remains the rule `source_id`. |
| **TRD-109** | Deferred rules | Appendix B `id`s are **not** in `central-corpus-allowlist.yaml`, manifest, or `verify_corpus_index` for v0.6. Re-add when PDF source exists (v0.7+). |
| **TRD-110** | Subset dedup | Rows with `pdf_source=subset` and same `pdf_url` as another row: index PDF **once**; manifest lists both `source_id`s pointing to same file or symlink policy in P3 runbook. |
| **TRD-111** | Eval vs deferred rules | `required_source_ids` and `expected_citations.document_id` must ⊆ **Appendix A only**. Cite parent acts where a deferred rule would apply (e.g. `IN-CPA-2019` not `IN-CPA-RULES-2020`). |

### Quality targets (unchanged — [`v02-eval-baseline.md`](../v02-eval-baseline.md))

| Metric | Target |
|--------|--------|
| `faithfulness` | ≥ 0.85 |
| `answer_correctness` | ≥ 0.80 |
| `llm_citation_correctness` | ≥ 0.95 |
| `recall_at_5` | ≥ 0.77 |
| `blockquote_met` | ≥ 0.80 |
| `refusal_correct` | ≥ 0.90 |
| `revised_law_met` | ≥ 0.95 |

---

## 3. Pre-flight validation (run before P0)

### 3.1 Environment

```bash
docker compose up -d postgres redis
cd backend && uv sync --dev && uv run alembic upgrade head
test -d ../data/corpus/india_code/raw || mkdir -p ../data/corpus/india_code/raw
```

### 3.2 Scraper audit (informational — records in P0 report)

```bash
python3 << 'PY'
import sqlite3
from pathlib import Path
db = Path.home() / "repos/indian-law-dataset-scraper/data/indiacode.sqlite3"
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM instrument_versions")
print("instrument_versions:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM instrument_version_files")
print("version_files:", cur.fetchone()[0])
conn.close()
PY
```

**Expected in current dev:** `instrument_versions: 0`. If zero, skip any plan that copies PDFs from scraper.

### 3.3 v0.5 soft gate (required before P3 only)

| Check | Command | Pass |
|-------|---------|------|
| MVP indexed | `uv run python -m dharmiq.eval.tools.verify_corpus_index --allowlist ../docs/plans/v0.5/mvp-corpus-allowlist.yaml` | 26/26 |
| Re-baseline doc | `docs/plans/v02-eval-baseline.md` has measured v0.5 row | dated row present |
| Manual runbook | `docs/plans/v0.5/manual-test-runbook.md` executed | signed/checklisted |

P0–P2, P4–P2 may proceed without v0.5 exit.

### 3.4 PDF acquisition strategy (binding workflow)

**Primary path (validated):** `download_indiacode_pdfs.py` — no scraper PDFs required.

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

**Manual fallback:** browser download from bitstream URL if automated tool fails (rate limit / block).

### 3.5 PDF tooling smoke (run in P0 / before P3)

```bash
cd backend

# Probe bitstream URLs without writing (no DB)
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --probe --limit 3

# Expect 200 + bitstream for IN-CPA-2019, IN-BNS-2023, IN-DPDP-2023

# Verify all canonical_url pages reachable
uv run python -m dharmiq.eval.tools.audit_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --verify-handles

# Download all PDFs (P3)
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --write
```

**Validated probe targets (minimum):**

| `source_id` | Expected handle |
|-------------|-----------------|
| `IN-CPA-2019` | `15256` |
| `IN-BNS-2023` | `20062` |
| `IN-DPDP-2023` | `22037` |

Optional scraper download (only if operator confirms `instrument_version_files > 0`):

```bash
cd ~/repos/indian-law-dataset-scraper
indiacode download --scope central --resume
# Fallback only:
uv run python -m dharmiq.eval.tools.import_corpus_pdfs --copy-pdfs ...
```

---

## 4. Phase P0 — Allowlist + loader + audit tools

### Goal

Commit `central-corpus-allowlist.yaml` (**62 instruments**, Appendix A) and extend tooling to parse v0.6 fields. No DB migration yet.

### Tasks

| # | Task | Files |
|---|------|-------|
| 0.1 | Create `central-corpus-allowlist.yaml` from §Appendix A (copy MVP 26 verbatim from v0.5 YAML) | `docs/plans/v0.6/central-corpus-allowlist.yaml` |
| 0.2 | Extend `AllowlistInstrument` + `load_allowlist()` for `status`, `superseded_by`, `supersedes`, `enforcement_date`, `india_code_handle`, `scraper_instrument_id`, `parent_act_id`, `pdf_source`, `pdf_url`, `shared_pdf_with`, `notes` | `backend/dharmiq/eval/tools/allowlist.py` |
| 0.3 | Extend `build_manifest_entries()` to emit TRD-80 fields | `allowlist.py` |
| 0.4 | Add `audit_allowlist.py` — validates YAML; `--verify-handles`; **`--verify-pdf-sources`** (TRD-107) | `backend/dharmiq/eval/tools/audit_allowlist.py` |
| 0.5 | Add `enrich_allowlist_from_scraper.py` — fills dates/title/**handle from `canonical_url`** (TRD-103) | `backend/dharmiq/eval/tools/enrich_allowlist_from_scraper.py` |
| 0.6 | Add **`download_indiacode_pdfs.py`** — bitstream + `parent_view_file` + `bundle` (TRD-100, TRD-105) | `backend/dharmiq/eval/tools/download_indiacode_pdfs.py` |
| 0.6b | Add `import_corpus_pdfs.py` — optional `--copy-pdfs` from scraper `pdfs_dir` when files exist | `backend/dharmiq/eval/tools/import_corpus_pdfs.py` |
| 0.7 | Update `build_manifest.py` default `--allowlist` to v0.6 path; keep `--allowlist` override | `build_manifest.py` |
| 0.8 | Fixture YAML for tests | `backend/tests/fixtures/v06-allowlist-fixture.yaml` |
| 0.9 | Unit tests | `tests/test_allowlist_v06.py`, extend `test_build_manifest.py` |

### `audit_allowlist.py` behavior

```bash
cd backend
uv run python -m dharmiq.eval.tools.audit_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml
```

Exit **0** iff:

- Exactly **62** instruments across 6 domains (Appendix A — excludes Appendix B deferred rules)
- All `id` unique; all `status` ∈ `{in_force, superseded, repealed}`
- All `canonical_url` match regex `https://www\.indiacode\.nic\.in/handle/123456789/\d+`
- MVP 26 `id` values match `docs/plans/v0.5/mvp-corpus-allowlist.yaml` exactly
- Superseded rows: `IN-IPC-1860`, `IN-CRPC-1973`, `IN-CPA-1986` present with `superseded_by`

Exit **1** with stderr list otherwise.

**`--verify-handles`:** For each instrument, `GET canonical_url` with browser User-Agent; require HTTP **200**. For acts, HTML should contain `/bitstream/123456789/` **or** the row has `pdf_source=parent_view_file` (TRD-108).

**`--verify-pdf-sources` (TRD-107):** For **every** committed row: GET resolved PDF URL (`pdf_url` or bitstream); require body starts with `%PDF` and size ≥ 5000 bytes.

### `download_indiacode_pdfs.py` (TRD-100, TRD-105)

```bash
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --probe --limit 3
```

**Algorithm (binding):**

1. Load allowlist (62 rows)
2. **`bitstream` (acts):** resolve `handle` from `india_code_handle` or `canonical_url`; `GET` handle page; regex bitstream paths; prefer `eng*` filename
3. **`parent_view_file` / `subset`:** `GET` row `pdf_url` directly (exact href from allowlist — do not rewrite `&file=`)
4. **`bundle`:** `GET` bitstream on bundle handle (e.g. POSH rules `9178`) or use `pdf_url` if set
5. Validate `%PDF` and size ≥ 5000 bytes
6. `--probe`: print `source_id`, `pdf_source`, URL, status — do not write
7. `--write`: save to `{corpus_dir}/{source_id_to_filename(id)}`; for `subset` rows sharing `pdf_url`, write once and record alias in manifest (`TRD-110`)
8. Polite delay 0.5s between instruments

**Errors:** Log per-instrument failure; exit **1** if any instrument in `--require-all` set fails (default when `--write` without `--continue-on-error`).

### `enrich_allowlist_from_scraper.py`

```bash
uv run python -m dharmiq.eval.tools.enrich_allowlist_from_scraper \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --scraper-db ~/repos/indian-law-dataset-scraper/data/indiacode.sqlite3 \
  --dry-run
```

- Match `instruments.instrument_id` = YAML `scraper_instrument_id` (when set)
- When SQLite row found: set `india_code_handle` from `canonical_url` path if YAML handle empty (TRD-103)
- Fill **only empty** YAML fields: `enactment_date`, `enforcement_date`, `title` (if truncated)
- **Never overwrite** existing `canonical_url` or a verified `india_code_handle`
- Log warning when scraper `type` disagrees with allowlist `doc_type`
- **Reject** mapping if scraper `short_title` and YAML `title` share no significant token (anti wrong-row)
- **Do not** fail if scraper row missing — manual handles are valid

### Smoke tests

```bash
cd backend
uv run pytest tests/test_allowlist_v06.py tests/test_build_manifest.py -q
uv run python -m dharmiq.eval.tools.audit_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml
uv run python -m dharmiq.eval.tools.build_manifest \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw
```

| Test | Assert |
|------|--------|
| `test_load_v06_allowlist_status_fields` | Parses `status`, `superseded_by` |
| `test_build_manifest_includes_temporal_fields` | JSON has `status`, `canonical_url` |
| `test_audit_allowlist_rejects_non_central_url` | Exit 1 on state handle |
| `test_mvp_ids_preserved_in_v06_allowlist` | 26 MVP ids subset check |
| `test_download_indiacode_pdfs_probe_cpa` | Mock HTTP → bitstream URL parsed |
| `test_download_indiacode_pdfs_parent_view_file` | Mock `pdf_url` → `%PDF` saved |
| `test_handle_from_canonical_url_not_instrument_id` | DPDP: id 350 → handle 22037 |
| `test_audit_verify_pdf_sources_subset` | Subset row shares parent `pdf_url` |

### Definition of done

- [x] `central-corpus-allowlist.yaml` committed (**62** instruments, Appendix A only)
- [x] `audit_allowlist` passes (`--verify-handles` + `--verify-pdf-sources` on all 62 rows)
- [x] `download_indiacode_pdfs --probe --limit 3` succeeds for CPA (bitstream), DPDP rules (`parent_view_file`), POSH bundle
- [x] `build_manifest` prints **62** expected filenames
- [x] Unit tests green

---

## 5. Phase P1 — Schema + ingestion temporal fields

### Goal

Persist temporal metadata from manifest → `source_documents`; purge stale version chunks (TRD-98).

### Tasks

| # | Task | Files |
|---|------|-------|
| 1.1 | Alembic `012_v06_corpus_temporal.py` | `backend/alembic/versions/012_v06_corpus_temporal.py` |
| 1.2 | Add `InstrumentStatus` enum + model columns | `backend/dharmiq/db/models/documents.py` |
| 1.3 | Create `StatuteRelationship` model + table | `backend/dharmiq/db/models/statute_relationships.py`, export in `db/models/__init__.py` |
| 1.4 | Extend `ScannedDocument` dataclass + `scan_corpus_directory()` | `backend/dharmiq/ingestion/scanner.py` |
| 1.5 | `_register_scanned_document` persists dates/status/url; TRD-98 purge | `backend/dharmiq/ingestion/pipeline.py` |
| 1.6 | `sync_statute_relationships(db, allowlist_path)` — upsert edges from YAML | `backend/dharmiq/ingestion/relationships.py` |
| 1.7 | Call relationship sync at end of `sync_corpus_documents` | `pipeline.py` |
| 1.8 | Extend `DocumentRead` / docs API with new fields | `schemas/documents.py`, `api/routes/docs.py` |
| 1.9 | Add `CorpusSettings` + `retrieval.include_superseded` | `config/settings.py`, `config/config.dev.yaml`, `config/config.beta.yaml` |
| 1.10 | Tests | `tests/test_ingestion_temporal.py`, `tests/test_statute_relationships.py` |

### Migration `012_v06_corpus_temporal.py`

```sql
-- instrument_status enum: in_force, superseded, repealed
ALTER TABLE source_documents ADD COLUMN status instrument_status NOT NULL DEFAULT 'in_force';
ALTER TABLE source_documents ADD COLUMN superseded_by_source_id VARCHAR(255) NULL;
ALTER TABLE source_documents ADD COLUMN enforcement_date DATE NULL;
ALTER TABLE source_documents ADD COLUMN canonical_url VARCHAR(1024) NULL;
ALTER TABLE source_documents ADD COLUMN instrument_metadata JSONB NOT NULL DEFAULT '{}';

CREATE TABLE statute_relationships (
  id UUID PRIMARY KEY,
  from_source_id VARCHAR(255) NOT NULL,
  to_source_id VARCHAR(255) NOT NULL,
  relationship VARCHAR(32) NOT NULL,  -- 'superseded_by' | 'amends' (only superseded_by used in v0.6)
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (from_source_id, to_source_id, relationship)
);
```

### Manifest → scanner field map

| Manifest key | `SourceDocument` column |
|--------------|-------------------------|
| `enactment_date` | `enactment_date` (parse ISO date) |
| `enforcement_date` | `enforcement_date` |
| `status` | `status` |
| `superseded_by` | `superseded_by_source_id` |
| `canonical_url` | `canonical_url` |
| (extra keys) | `instrument_metadata` |

### TRD-98 purge logic (in `_register_scanned_document` after flush)

When creating `version = existing.version + 1` for same `source_id`:

```python
# Delete chunks + sections for all older document_ids with same source_id and version < new.version
```

### `sync_statute_relationships` seeds (minimum)

| from_source_id | to_source_id | relationship |
|----------------|--------------|--------------|
| `IN-IPC-1860` | `IN-BNS-2023` | `superseded_by` |
| `IN-CRPC-1973` | `IN-BNSS-2023` | `superseded_by` |
| `IN-CPA-1986` | `IN-CPA-2019` | `superseded_by` |

Plus any `superseded_by` on allowlist rows (generic loop).

### Smoke tests

```bash
cd backend
uv run alembic upgrade head
uv run pytest tests/test_ingestion_temporal.py tests/test_statute_relationships.py tests/test_scanner.py -q
```

| Test | Assert |
|------|--------|
| `test_scanner_reads_manifest_status_and_dates` | ScannedDocument fields populated |
| `test_register_document_persists_temporal_fields` | DB row matches manifest |
| `test_new_version_purges_old_chunks` | Only latest version has chunks |
| `test_sync_statute_relationships_idempotent` | Re-run upsert → same count |

### Definition of done

- [x] Migration applies cleanly on empty + existing DB
- [x] Manifest temporal fields persist through sync
- [x] Relationship seeds present
- [x] Tests green

---

## 6. Phase P2 — Retrieval filters

### Goal

Default retrieval excludes superseded/repealed and non-current document versions.

### Tasks

| # | Task | Files |
|---|------|-------|
| 2.1 | Add `_CORPUS_DOCUMENT_FILTER` SQL fragment | `backend/dharmiq/retrieval/hybrid.py` |
| 2.2 | Implement `latest_source_documents` subquery / JOIN | same |
| 2.3 | Wire `settings.retrieval.include_superseded` | same, `config/settings.py` |
| 2.4 | Optional in-force boost in reranker tie-break (ε=0.01) | `backend/dharmiq/retrieval/reranker.py` or inline in hybrid post-rerank |
| 2.5 | Answerer prompt addition: prefer in-force when both retrieved | `backend/dharmiq/llm/prompts/answerer.yaml` |
| 2.6 | Tests with seeded superseded + in-force docs | `tests/test_retrieval_temporal.py` |

### SQL fragment (binding)

```sql
-- Latest indexed document per source_id
JOIN (
  SELECT DISTINCT ON (source_id) id AS document_id, source_id, status
  FROM source_documents
  WHERE indexed_at IS NOT NULL
  ORDER BY source_id, version DESC
) sd ON dc.document_id = sd.document_id
-- Status filter (when include_superseded=false)
AND (sd.status IS NULL OR sd.status = 'in_force')
```

Apply to `_CORPUS_VECTOR_SQL` and `_CORPUS_BM25_SQL` (replace simple `JOIN source_documents sd`).

### Smoke tests

```bash
cd backend
uv run pytest tests/test_retrieval_temporal.py tests/test_retrieval.py -q
```

| Test | Assert |
|------|--------|
| `test_superseded_ipc_not_retrieved_when_bns_indexed` | Query “theft punishment BNS”; top chunks not from `IN-IPC-1860` |
| `test_include_superseded_flag` | When true, superseded may appear |
| `test_old_version_chunks_excluded` | Two versions same source_id → only latest chunks |

### Definition of done

- [x] Superseded docs indexed but excluded by default
- [x] `v1_revised_law` fixture corpus test passes (seed in test)
- [x] No regression in existing `test_retrieval.py`

---

## 7. Phase P3 — Full corpus index (operational)

### Goal

62/62 PDFs on disk, indexed, chunk budget OK.

### Prerequisites

- v0.5 exit (§3.3)
- P0–P2 merged
- Operator acquired PDFs

### Tasks

| # | Task | Operational |
|---|------|-------------|
| 3.1 | `download_indiacode_pdfs --write` (or verify PDFs already on disk) | `data/corpus/india_code/raw/` |
| 3.2 | `build_manifest --write` | generates `manifest.json` |
| 3.3 | `uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs` | wait for Celery completion |
| 3.4 | `verify_corpus_index --allowlist central --write-report` | exit 0 |
| 3.5 | Log `corpus_chunk_count`; assert ≤ 250000 | `data/eval/runs/corpus_index_report.json` |
| 3.6 | `sync_statute_relationships` verified via SQL count ≥ 3 | manual |

### Smoke tests

```bash
cd backend
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw \
  --write

uv run python -m dharmiq.eval.tools.build_manifest \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw --write

uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
# wait for worker logs: corpus_sync_complete

uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --write-report

python3 -c "import json; r=json.load(open('../data/eval/runs/corpus_index_report.json')); assert r['indexed_document_count']==62; assert r['corpus_chunk_count']<=250000"
```

### Definition of done

- [ ] **62/62** indexed, chunks ≤ 250k
- [ ] `corpus_index_report.json` committed to operator log (not necessarily git)
- [ ] Temporal fields populated (spot-check 5 docs in DB)

---

## 8. Phase P4 — Eval datasets

### Goal

Three new gating datasets + needle extension; validation minimums.

### Tasks

| # | Task | Files |
|---|------|-------|
| 4.1 | Author `v1_property.jsonl` ≥15 rows | `data/eval/datasets/v1_property.jsonl` |
| 4.2 | Author `v1_tax.jsonl` ≥15 rows | `data/eval/datasets/v1_tax.jsonl` |
| 4.3 | Author `v1_cyber.jsonl` ≥15 rows | `data/eval/datasets/v1_cyber.jsonl` |
| 4.4 | Append ≥10 needle rows (property/tax/cyber topics) | `v1_needle_statute.jsonl` |
| 4.5 | Extend `GATING_MINIMUM_COUNTS` | `validate_dataset.py` |
| 4.6 | Add `FORBIDDEN_TOPICS` if needed (no case law rows) | `validate_dataset.py` |
| 4.7 | Loader smoke tests | `tests/test_eval_dataset_loader.py` |

### Content rules (binding)

- Citizen phrasing; each row: `expected_citations` with `section` + `document_id` as allowlist `source_id` where possible
- `required_source_ids` ⊆ **Appendix A** ids only (TRD-111 — no deferred Appendix B rules)
- **No** state-law-only questions; **no** case-law citations
- Tax rows: **no** numeric slab rates unless quoted in `expected_answer` from statute
- Property rows: central acts only (RERA, Registration, etc.)
- Cyber rows: DPDP + IT Act sections (IT Act already indexed as `IN-IT-2000`)

### Example row (`v1_property`)

```json
{
  "id": "p1",
  "question": "Does my builder have to register the project with RERA before selling flats?",
  "expected_answer": "Under the Real Estate (Regulation and Development) Act, 2016, registration of the real estate project with the Real Estate Regulatory Authority is required before advertising or selling.",
  "expected_citations": [{"document_id": "IN-RERA-2016", "section": "Section 3"}],
  "topic": "rera_registration",
  "min_citation_count": 1,
  "expect_blockquote": true,
  "required_source_ids": ["IN-RERA-2016"]
}
```

### Smoke tests

```bash
cd backend
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_property
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_tax
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_cyber
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_needle_statute
uv run pytest tests/test_eval_dataset_loader.py -q
```

### Definition of done

- [x] Three new datasets committed, validate passes
- [x] Needle file ≥30 rows total
- [ ] Eval owner sign-off (PR note)

---

## 9. Phase P5 — `--suite v06` + baseline

### Goal

CLI suite, compare, and baseline merge for v0.6.

### Tasks

| # | Task | Files |
|---|------|-------|
| 5.1 | `V06_DATASETS`, `V06_SUITE_ORDER`, `run_v06_suite()` | `backend/dharmiq/eval/suite.py` |
| 5.2 | `build_v06_baseline()`, `merge_baseline_suite()` | `backend/dharmiq/eval/baseline.py` |
| 5.3 | CLI `--suite v06`; `--compare` works with v06; `--allowlist` flag | `cli.py` |
| 5.4 | `collect_run_metadata(..., allowlist_path=)` default v0.6 when `--suite v06` | `metadata.py` — add `default_v06_allowlist_path()` |
| 5.5 | `compare.py` — `revised_law_met` in `BOOLEAN_METRICS` | `compare.py` |
| 5.6 | Tests | `tests/test_eval_suite_v06.py`, extend `test_eval_compare.py` |

### `V06_SUITE_ORDER` (TRD-84)

```python
V06_DATASETS = [
    "v1_property",
    "v1_tax",
    "v1_cyber",
]

def v06_suite_datasets() -> list[str]:
    return [*MVP_DATASETS, *V06_DATASETS]
```

### Baseline merge (TRD-85)

`--suite v06 --write-baseline --yes`:

1. Load existing `baseline.json` if present
2. Set `suites.v06` from current run
3. Preserve `suites.mvp` unchanged
4. Write file

### Smoke tests

```bash
cd backend
uv run pytest tests/test_eval_suite_v06.py tests/test_eval_compare.py tests/test_eval_suite.py -q
uv run dharmiq-eval --suite v06 --limit 1   # needs corpus + OPENROUTER_API_KEY
```

### Definition of done

- [x] `--suite v06` runs 9 datasets
- [x] Compare loads `suites.v06`
- [x] Write baseline merges without dropping mvp
- [x] Unit tests green

---

## 10. Phase P6 — As-of footnote

### Goal

Append TRD-90 footnote to statutory answers in production graph and eval.

### Tasks

| # | Task | Files |
|---|------|-------|
| 6.1 | `get_corpus_indexed_date(db) -> date | None` | `backend/dharmiq/corpus/indexed_at.py` |
| 6.2 | `append_corpus_footnote(answer, indexed_date) -> str` | `backend/dharmiq/corpus/footnote.py` |
| 6.3 | Call from `finalizer_node` when not refusal/validation failure | `agents/nodes/finalizer.py` |
| 6.4 | Call from `run_eval_rag` after answerer | `eval/runner.py` |
| 6.5 | Tests | `tests/test_corpus_footnote.py` |

### Footnote template (TRD-90)

```text

---
Sources indexed: {YYYY-MM-DD} (UTC). Citations refer to central law as indexed; confirm critical details with a qualified lawyer.
```

Idempotent: if `Sources indexed:` in answer, return unchanged.

Skip when answer text starts with or equals `REFUSAL_MESSAGE` or `VALIDATION_FAILED_MESSAGE` prefix.

### Smoke tests

```bash
cd backend
uv run pytest tests/test_corpus_footnote.py -q
```

| Test | Assert |
|------|--------|
| `test_footnote_appended_once` | Second call does not duplicate |
| `test_footnote_skipped_on_refusal` | Refusal message unchanged |
| `test_footnote_unknown_date` | Uses `unknown` when no indexed docs |

### Definition of done

- [x] Footnote in finalizer path (unit tested)
- [x] Footnote in eval runner path
- [x] Tests green

---

## 11. Phase P7 — Citation IndiaCode attribution

### Goal

Expose `canonical_url` on citations for corpus sources (TRD-95).

### Tasks

| # | Task | Files |
|---|------|-------|
| 7.1 | Add `canonical_url: str | None = None` to `CitationRecord` | `schemas/citations.py` |
| 7.2 | Load from `SourceDocument` in enricher (batch lookup by document_id) | `agents/citation_validation.py` or new `citation_metadata.py` |
| 7.3 | Include in SSE `emit_citation` payload | `agents/streaming.py` |
| 7.4 | Frontend: show link “View on IndiaCode” when `canonical_url` set | `frontend/src/lib/citations.ts`, citation list component |
| 7.5 | Tests | `tests/test_citation_enricher.py`, frontend lint |

### API shape (additive)

```json
{
  "marker": 1,
  "document_title": "The Consumer Protection Act, 2019",
  "canonical_url": "https://www.indiacode.nic.in/handle/123456789/15256",
  "source_type": "corpus"
}
```

### Smoke tests

```bash
cd backend && uv run pytest tests/test_citation_enricher.py -q
cd frontend && npm run lint
```

### Definition of done

- [x] `canonical_url` on corpus citations in API/SSE
- [x] Frontend link renders when URL present
- [x] Upload citations unaffected (`canonical_url` null)

---

## 12. Phase P8 — Docs, runbooks, version bump

### Goal

Operator docs, licensing checklist, README/roadmap updates, `0.6.0`.

### Tasks

| # | Task | Files |
|---|------|-------|
| 8.1 | Write `corpus-indexing-runbook.md` | `docs/plans/v0.6/corpus-indexing-runbook.md` |
| 8.2 | Write `licensing-checklist.md` with sign-off table | `docs/plans/v0.6/licensing-checklist.md` |
| 8.3 | Update `data-implementation.md` §3.2 pipelines row for v0.6 | docs |
| 8.4 | Update `datasets.md` §6.3 inventory | docs |
| 8.5 | Bump version to `0.6.0` | `__init__.py`, `pyproject.toml`, `package.json` |
| 8.6 | README eval section: `--suite v06` | `README.md` |
| 8.7 | Mark PRD/TRD exit criteria | `prd.md`, this file |

### `corpus-indexing-runbook.md` minimum sections

1. Prerequisites (Docker, Celery worker, 16 GB RAM)
2. PDF acquisition (§3.4)
3. `build_manifest` → `sync` → `verify`
4. Add one instrument (edit YAML → PDF → manifest → sync)
5. Rollback (restore manifest + PDF from backup)
6. Metrics to log (`corpus_chunk_count`, `pg_database_size`, allowlist version)
7. Chunk budget stop rule (TRD-93)

### Smoke tests

```bash
test -f docs/plans/v0.6/corpus-indexing-runbook.md
test -f docs/plans/v0.6/licensing-checklist.md
grep -q "0.6.0" backend/dharmiq/__init__.py
cd backend && uv run pytest -m "not slow" -q
```

### Definition of done

- [x] Runbook + checklist committed
- [x] Version 0.6.0
- [x] Docs cross-linked
- [x] PRD exit criteria checkboxes updated

---

## 13. CLI reference (post v0.6)

```bash
cd backend

# Allowlist audit
uv run python -m dharmiq.eval.tools.audit_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml

# Optional scraper metadata enrich
uv run python -m dharmiq.eval.tools.enrich_allowlist_from_scraper \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --scraper-db ~/repos/indian-law-dataset-scraper/data/indiacode.sqlite3 \
  --dry-run

# Allowlist audit + handle probe
uv run python -m dharmiq.eval.tools.audit_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml --verify-handles

# PDF probe / download
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw --probe --limit 3
uv run python -m dharmiq.eval.tools.download_indiacode_pdfs \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw --write

# Manifest + sync + verify
uv run python -m dharmiq.eval.tools.build_manifest \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --corpus-dir ../data/corpus/india_code/raw --write
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml --write-report

# Eval
uv run dharmiq-eval --suite v06 --limit 5
uv run dharmiq-eval --suite mvp --compare baseline      # regression
uv run dharmiq-eval --suite v06 --compare baseline      # v0.6 gate
uv run dharmiq-eval --suite v06 --write-baseline --yes  # merges suites.v06

# Dataset lint
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_property
```

---

## 14. Agent prompt templates

Copy-paste when spawning an agent for **one phase only**.

```text
Implement Dharmiq v0.6 phase {PHASE_ID} from docs/plans/v0.6/trd.md.

Rules:
- Read docs/plans/v0.6/prd.md and trd.md §2 binding decisions first
- Implement ONLY this phase's tasks
- Do not depend on indian-law-dataset-scraper PDFs (metadata optional only)
- Match existing code style in backend/dharmiq/
- Run phase smoke tests listed in trd.md for {PHASE_ID}
- Run global smoke gate (ruff + pytest -m "not slow" + frontend lint)
- Do not commit unless asked
- Eval path: run_eval_rag only

Phase: {PHASE_ID} — {PHASE_NAME}
```

### Example (P2)

```text
Implement Dharmiq v0.6 phase P2 from docs/plans/v0.6/trd.md.
Add retrieval filters for instrument status and latest document version per source_id.
Update hybrid.py SQL, config retrieval.include_superseded, answerer.yaml prompt line,
and tests/test_retrieval_temporal.py. Run smoke tests in trd.md §6.
```

---

## 15. Final smoke test (v0.6 ship)

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
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml

# 3. Eval (advisory; needs OPENROUTER_API_KEY + indexed corpus)
uv run dharmiq-eval --suite mvp --compare baseline
uv run dharmiq-eval --suite v06 --compare baseline

# 4. Manual: chat footnote visible; citation IndiaCode link on hover
# 5. Sign licensing-checklist.md
```

---

## 16. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Scraper has no PDFs | `download_indiacode_pdfs.py` HTTP bitstream path (§3.5) |
| Wrong handle (instrument_id ≠ handle) | TRD-99; enrich from `canonical_url`; DPDP=22037 |
| Rule handles invalid (302) | Superseded — use `pdf_source` + `parent_view_file` (TRD-105–110) |
| Rule PDF not on IndiaCode | **16 rules deferred** to Appendix B; eval cites parent acts (TRD-111) |
| Scraper missing subordinate rows | Use `enrich_allowlist_from_scraper`; manual `canonical_url` / handle from live IndiaCode |
| IndiaCode rate limit / block | 0.5s delay; `--limit` batches; manual bitstream URL fallback |
| Scraper tests fail | Do not block Dharmiq on scraper CI |
| Multi-version chunk leak | TRD-78 + TRD-98 |
| Tax/property eval too hard | Scope questions to indexed sections; owner review |
| Chunk budget exceeded | TRD-93 stop; rescope allowlist |
| `revised_law` regression after filter | Keep superseded indexed; test in P2 |
| v0.5 exit delayed | P3 blocked; P0–P2/P4–P7 proceed |

---

## Appendix A — `central-corpus-allowlist.yaml` instrument manifest (**62 committed**)

**P0 must commit YAML with exactly these 62 `id` values.** Format follows v0.5 YAML. **Do not** include Appendix B deferred rules.

**Handle / PDF resolution (P0 binding):**

1. **Acts:** handle from SQLite `canonical_url` (not `instrument_id`); `pdf_source=bitstream` (default)
2. **Rules:** copy `pdf_source`, `pdf_url`, `parent_act_id` from [`rule-probe-results.json`](./rule-probe-results.json) for committed rows only
3. `audit_allowlist --verify-handles` on all rows
4. `audit_allowlist --verify-pdf-sources` on all **62** rows
5. Scraper metadata (optional): `enrich_allowlist_from_scraper` against `indian-law-dataset-scraper` SQLite

**Failed handle probe (obsolete):** `11445`, `11443`, `11441`, `11442` — invalid guessed handles; do not use.

**Verified act handles (2026-06-23 live download + scraper `canonical_url`):**

| `source_id` | `india_code_handle` | Notes |
|-------------|---------------------|-------|
| `IN-CPA-2019` | `15256` | PDF downloaded ✓ |
| `IN-BNS-2023` | `20062` | PDF downloaded ✓ |
| `IN-DPDP-2023` | `22037` | `scraper_instrument_id=350` — **not** handle 350 |
| `IN-RERA-2016` | `2158` | scraper id 247 |
| `IN-TPA-1882` | `2338` | scraper id 47 |
| `IN-REGISTRATION-1908` | `2190` | scraper id 249 |
| `IN-STAMP-1899` | `15510` | scraper id 26 |
| `IN-LARR-2013` | `2121` | scraper id 458 |
| `IN-EASEMENTS-1882` | `2349` | scraper id 65 |
| `IN-SRA-1963` | `1583` | scraper id **671** (not 280) |
| `IN-LIMITATION-1963` | `1565` | scraper id **542** (not 277) |
| `IN-ITA-1961` | `2435` | scraper id 619 |
| `IN-CGST-2017` | `15689` | scraper id 184 |
| `IN-IGST-2017` | `2251` | scraper id 202 |
| `IN-GST-COMPENSATION-2017` | `2253` | scraper id 236 |

### A.1 MVP core (26) — copy unchanged from [`mvp-corpus-allowlist.yaml`](../v0.5/mvp-corpus-allowlist.yaml)

All 26 `id` values and metadata from v0.5 file — do not rename or remove.

### A.2 Cross-domain deepen (12 committed)

Consumer / employment / rights — acts and rules with verified PDFs:

| id | title | doc_type | pdf_source | status |
|----|-------|----------|------------|--------|
| `IN-POSH-RULES-2013` | Sexual Harassment of Women at Workplace Rules, 2013 | rule | `bundle` (9178) | VERIFIED |
| `IN-EPF-SCHEME-1952` | Employees' Provident Funds Scheme, 1952 | rule | `parent_view_file` | VERIFIED |
| `IN-ESIC-1948` | Employees' State Insurance Act, 1948 | act | `bitstream` | TBD handle |
| `IN-PAYMENT-GRATUITY-1972` | Payment of Gratuity Act, 1972 | act | `bitstream` | TBD handle |
| `IN-DOWRY-1961` | Dowry Prohibition Act, 1961 | act | `bitstream` | TBD handle |
| `IN-DOMESTIC-VIOLENCE-2005` | Protection of Women from Domestic Violence Act, 2005 | act | `bitstream` | TBD handle |
| `IN-SC-ST-PREVENTION-1989` | Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989 | act | `bitstream` | TBD handle |
| `IN-MTP-1971` | Medical Termination of Pregnancy Act, 1971 | act | `bitstream` | handle 1593 |
| `IN-MTP-RULES-2003` | Medical Termination of Pregnancy Rules, 2003 | rule | `parent_view_file` | VERIFIED |
| `IN-DPDP-RULES` | Digital Personal Data Protection Rules (current central rules) | rule | `parent_view_file` | VERIFIED |
| `IN-IT-RULES-INTERMEDIARY-2021` | IT (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021 | rule | `parent_view_file` | VERIFIED |
| `IN-IT-RULES-SPDI-2011` | IT (Reasonable Security Practices and Sensitive Personal Data or Information) Rules, 2011 | rule | `parent_view_file` | VERIFIED |

### A.3 Property (10 committed)

| id | title | doc_type | scraper_id | handle |
|----|-------|----------|------------|--------|
| `IN-RERA-2016` | Real Estate (Regulation and Development) Act, 2016 | regulation | 247 | 2158 |
| `IN-TPA-1882` | Transfer of Property Act, 1882 | act | 47 | 2338 |
| `IN-REGISTRATION-1908` | Registration Act, 1908 | act | 249 | 2190 |
| `IN-STAMP-1899` | Indian Stamp Act, 1899 | act | 26 | 15510 |
| `IN-LARR-2013` | Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act, 2013 | act | 458 | 2121 |
| `IN-EASEMENTS-1882` | Indian Easements Act, 1882 | act | 65 | 2349 |
| `IN-SRA-1963` | Specific Relief Act, 1963 | act | 671 | 1583 |
| `IN-LIMITATION-1963` | Limitation Act, 1963 | act | 542 | 1565 |
| `IN-MODEL-TENANCY-ACT-2021` | Model Tenancy Act, 2021 | act | null | TBD |
| `IN-LARR-RULES-2014` | Land Acquisition Rules, 2014 | rule | — | VERIFIED (`parent_view_file`) |

**P0 act handles (from scraper `canonical_url` path):** resolve TBD for rows with `scraper_instrument_id` by browsing IndiaCode act page and copying handle from URL.

### A.4 Tax (10 committed)

| id | title | doc_type | scraper_id | handle |
|----|-------|----------|------------|--------|
| `IN-ITA-1961` | Income-tax Act, 1961 | act | 619 | 2435 |
| `IN-CGST-2017` | Central Goods and Services Tax Act, 2017 | act | 184 | 15689 |
| `IN-IGST-2017` | Integrated Goods and Services Tax Act, 2017 | act | 202 | 2251 |
| `IN-GST-COMPENSATION-2017` | Goods and Services Tax (Compensation to States) Act, 2017 | act | 236 | 2253 |
| `IN-CGST-RULES-2017` | Central Goods and Services Tax Rules, 2017 | rule | — | VERIFIED (`parent_view_file`) |
| `IN-IGST-RULES-2017` | Integrated Goods and Services Tax Rules, 2017 | rule | — | VERIFIED (`parent_view_file`) |
| `IN-GST-INVOICE-RULES-2017` | GST Invoice Rules | rule | — | SUBSET → CGST Rules |
| `IN-GST-RETURN-RULES-2017` | GST Return Rules | rule | — | SUBSET → CGST Rules |
| `IN-GST-REFUND-RULES-2017` | GST Refund Rules | rule | — | SUBSET → CGST Rules |
| `IN-GST-ASSESSMENT-RULES-2017` | GST Assessment and Audit Rules | rule | — | SUBSET → CGST Rules |

### A.5 Cyber-only additions (3 committed — not listed in A.2)

| id | title | doc_type | scraper_id | handle |
|----|-------|----------|------------|--------|
| `IN-DPDP-2023` | Digital Personal Data Protection Act, 2023 | act | 350 | **22037** |
| `IN-IT-AMENDMENT-ACT-2008` | Information Technology (Amendment) Act, 2008 | act | 331 | TBD |
| `IN-IT-ELECTRONIC-SIGNATURES-2015` | Electronic Signatures Rules | rule | — | VERIFIED (`parent_view_file`) |

Do **not** add a second `IN-IT-2000` row (already in MVP as `IN-IT-2000`).

### A.6 Employment deepen (1 committed)

| id | title | doc_type | scraper_id | handle |
|----|-------|----------|------------|--------|
| `IN-FACTORIES-1948` | Factories Act, 1948 | act | null | TBD |

### A.7 Final count (binding)

| Segment | Count |
|---------|-------|
| A.1 MVP | 26 |
| A.2 Cross-domain deepen | 12 |
| A.3 Property | 10 |
| A.4 Tax | 10 |
| A.5 Cyber-only | 3 |
| A.6 Employment deepen | 1 |
| **Total committed** | **62** |

Each `id` appears **once** in committed YAML.

---

## Appendix B — Deferred rules (v0.6 — **not in allowlist**)

**16** rule/notification rows probed without a central IndiaCode PDF. **Skipped for v0.6** per product decision. Revisit in v0.7+ (scraper fix, eGazette, or IndiaCode update). Eval must cite **parent acts** instead (TRD-111).

| id | title | probe status | parent act (for eval) |
|----|-------|--------------|------------------------|
| `IN-CPA-RULES-ECOMMERCE-2020` | Consumer Protection (E-Commerce) Rules, 2020 | NOT_ON_INDIACODE | `IN-CPA-2019` |
| `IN-CPA-RULES-2020` | Consumer Protection Rules, 2020 | NOT_ON_INDIACODE | `IN-CPA-2019` |
| `IN-CLRA-RULES-1971` | Contract Labour Central Rules, 1971 | NOT_ON_INDIACODE | `IN-CLRA-1970` |
| `IN-BNSS-RULES-2024` | BNSS central rules | NOT_ON_INDIACODE | `IN-BNSS-2023` |
| `IN-IT-RULES-CERTIN-2022` | CERT-In Directions, 2022 | NOT_ON_INDIACODE | `IN-IT-2000` |
| `IN-RERA-RULES-2016` | RERA Rules, 2016 | UT_ONLY | `IN-RERA-2016` |
| `IN-RERA-GENERAL-RULES-2017` | RERA General Rules, 2017 | UT_ONLY | `IN-RERA-2016` |
| `IN-REGISTRATION-RULES-1961` | Registration Rules, 1961 | NOT_ON_INDIACODE | `IN-REGISTRATION-1908` |
| `IN-STAMP-RULES-1958` | Indian Stamp Rules (central) | NOT_ON_INDIACODE | `IN-STAMP-1899` |
| `IN-ITR-RULES-1962` | Income-tax Rules, 1962 | NOT_ON_INDIACODE | `IN-ITA-1961` |
| `IN-TDS-RULES-1962` | Income-tax (TDS) Rules | NOT_ON_INDIACODE | `IN-ITA-1961` |
| `IN-IT-DATA-RETENTION-2022` | IT (Data Retention) Rules | NOT_ON_INDIACODE | `IN-IT-2000` |
| `IN-IT-CYBER-APPELLATE-RULES` | IT Cyber Appellate Tribunal Rules | NOT_ON_INDIACODE | `IN-IT-2000` |
| `IN-MINIMUM-WAGES-RULES-1950` | Minimum Wages (Central) Rules | NOT_ON_INDIACODE | `IN-MWA-1948` |
| `IN-BONUS-RULES-1975` | Payment of Bonus Rules, 1975 | NOT_ON_INDIACODE | `IN-POBA-1965` |
| `IN-EQUAL-REMUNERATION-RULES-1976` | Equal Remuneration Rules, 1976 | NOT_ON_INDIACODE | `IN-ERA-1976` |

Probe details: [`rule-probe-results.json`](./rule-probe-results.json).

---

## 17. Document history

| Date | Change |
|------|--------|
| 2026-06-23 | Initial TRD from PRD + codebase/scraper validation |
| 2026-06-23 | **Deferred 16 rules** (Appendix B); committed corpus **62** instruments; TRD-109/111; fixed 78/78 contradictions |
| 2026-06-23 | Rule PDF validation sprint (§1.7); TRD-105–110; [`rule-probe-results.json`](./rule-probe-results.json) |
| 2026-06-23 | Live PDF download validation; TRD-99–104; handle fixes (DPDP 22037) |
| 2026-06-23 | P8 complete — runbooks, licensing checklist, version 0.6.0, docs cross-linked |

---

*Ship checklist: **62/62** indexed (PDF + chunks), chunk ≤250k, `--suite v06 --compare baseline`, MVP regression clean, licensing checklist signed, version 0.6.0.*
