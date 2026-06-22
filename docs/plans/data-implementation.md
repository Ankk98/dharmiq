# Dharmiq — Data implementation & corpus operations

**Status:** Living document · **Last updated:** 2026-06-22  
**Audience:** Engineering, ops, self-hosters  
**Companion:** [`datasets.md`](./datasets.md) (data strategy, evals, benchmarks, gaps)  
**Related:** [`roadmap.md`](./roadmap.md) · [`v02-eval-baseline.md`](./v02-eval-baseline.md) · [`../deployment.md`](../deployment.md)

This document covers **how Dharmiq stores, ingests, indexes, and queries** legal data — pipelines, schema, scale limits, and agent integration. For *what* data we need and *which* external sources to use, see [`datasets.md`](./datasets.md).

**Current posture:** Start with a **small indexed subset**; prove retrieval + eval gates; scale architecture only when subset gates pass.

---

## 1. Implemented today (code baseline)

| Component | Location | Behavior |
|-----------|----------|----------|
| Corpus ingestion | `backend/dharmiq/ingestion/` | PDF scan → parse → parent/child chunk → embed → Postgres |
| Corpus directory | `data/corpus/india_code/raw/` | Optional `manifest.json` — [`scanner.py`](../../backend/dharmiq/ingestion/scanner.py) |
| Sync task | `dharmiq.ingestion.sync_india_code_pdfs` | Celery; content-hash idempotent |
| Doc types | `DocType` in [`documents.py`](../../backend/dharmiq/db/models/documents.py) | `act`, `rule`, `regulation`, `notification`, `other` — **no `judgment` yet** |
| Chunks | `document_chunks` | 384-dim vectors (`all-MiniLM-L6-v2`), BM25 `search_vector`, parent/child |
| Chunk settings | `config/*.yaml` → `ingestion.*` | ~300-token children, 2048-token parents, 64-token overlap |
| User uploads | `user_upload_chunks` + `upload_pipeline.py` | Same chunking; session attachments |
| Retrieval | `llm/retrieval.py` | pgvector + BM25 RRF + local cross-encoder rerank |
| Eval CLI | `uv run dharmiq-eval --dataset <name>` | See [`dataset_format.md`](../../backend/dharmiq/eval/dataset_format.md) |
| Eval runner | `eval/runner.py` → `run_eval_rag()` | Rewriter → retrieval → answerer (**not** full LangGraph yet) |
| Smoke | `tests/test_v02_e2e_smoke.py` | Mocked LLM; httpx API; inline Celery |
| Feedback API | v0.4 | 👍/👎 per message — not wired to eval export yet |
| Eval data path | `data/eval/datasets/*.jsonl` | Committed via `.gitignore` exception |
| Docker data mounts | `docker-compose.dev.yml` | `./data/corpus`, `./data/eval` bind-mount |

---

## 2. Target architecture

```text
                    ┌─────────────────────────────────────────┐
                    │           INGESTION LAYER                  │
                    │  IndiaCode scraper │ AWS S3 │ User upload   │
                    └─────────┬───────────────────┬─────────────┘
                              ▼                   ▼
                    ┌─────────────────┐   ┌───────────────────┐
                    │ Curation        │   │ Metadata store     │
                    │ allowlist/dedup │   │ (SQLite/Parquet)   │
                    └────────┬────────┘   └─────────┬─────────┘
                             ▼                       │
                    ┌─────────────────┐              │
                    │ Parse + chunk   │◄─────────────┘
                    │ (type-specific) │
                    └────────┬────────┘
                             ▼
              ┌──────────────┴──────────────┐
              ▼                             ▼
     ┌─────────────────┐          ┌─────────────────┐
     │ HOT: Postgres   │          │ COLD: Object     │
     │ pgvector+BM25   │          │ storage (PDFs)   │
     │ MVP subset now  │          │ HC archive later │
     └────────┬────────┘          └─────────────────┘
              ▼
     ┌─────────────────┐
     │ LangGraph agents│
     │ + hybrid RAG    │
     └─────────────────┘
```

### 2.1 Phased complexity

| Phase | Indexed in Postgres | Notes |
|-------|---------------------|-------|
| **Now (v0.5)** | MVP statute subset (~50–200 PDFs) | Validate pipeline + eval gates on small data |
| **v0.6** | Curated central IndiaCode (allowlist) | Scraper → manifest → existing sync |
| **v0.11** | + SC judgments (subset → full ~35k) | New `judgment` doc type + ingestion path |
| **HC** | **Out of scope** for main app | Standalone project later — see §5 |
| **Full central catalog** | Deferred | Only after subset quality proven |

---

## 3. Pipelines

### 3.1 Existing — statute PDFs

```bash
# Place PDFs (+ optional manifest.json) under:
data/corpus/india_code/raw/

cd backend
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs
```

Flow: `scan_corpus_directory` → `process_document` → `chunk_document` → embed batches → `document_chunks`.

**Manifest example** (per file in `manifest.json`):

```json
{
  "file": "consumer-protection-act-2019.pdf",
  "source_id": "IN-CPA-2019",
  "title": "The Consumer Protection Act, 2019",
  "doc_type": "act",
  "jurisdiction": "central",
  "enactment_date": "2019-08-09",
  "canonical_url": "https://www.indiacode.nic.in/handle/..."
}
```

### 3.2 Planned pipelines

| Pipeline | Input | Output | Version |
|----------|-------|--------|---------|
| `sync_india_code_pdfs` | `data/corpus/india_code/raw/` | `source_documents` + chunks | **Today** |
| `sync_indiacode_scraper` | Scraper SQLite/CSV → allowlist → manifest | PDFs in `raw/` | v0.6 |
| `eval_dataset_builder` | Templates + indexed sections | `data/eval/datasets/*.jsonl` | v0.5 |
| `sync_sc_judgments` | S3 Parquet filter → PDF subset | `doc_type=judgment` | v0.11 |
| `build_amendment_graph` | Scraper + manual edges | chunk / document metadata | v0.6 |
| `feedback_to_eval_queue` | 👎 exports | Review CSV → JSONL | v0.10 |
| `hc_*` | — | **Separate project** | TBD |

### 3.3 IndiaCode scraper → Dharmiq (v0.6)

Repo: `~/repos/indian-law-dataset-scraper`

```bash
indiacode init
indiacode metadata --scope central
indiacode download --scope central --extract-text --resume
indiacode export-csv --out dist/csv
```

Then: SQL/filter CSV → MVP allowlist → copy PDFs → `manifest.json` → `sync_india_code_pdfs`.

Domain filter examples are in [`datasets.md` §4.1](./datasets.md#41-indiacode-scraper-reposindian-law-dataset-scraper).

### 3.4 Eval runs

```bash
cd backend
uv run dharmiq-eval --dataset v1_fundamental_rights
# Requires indexed corpus + OPENROUTER_API_KEY for live runs
```

Targets: [`v02-eval-baseline.md`](./v02-eval-baseline.md). CI should use **miniature seeded corpus** (5–10 PDFs or test fixtures), not production catalogs.

### 3.5 User uploads

Already implemented: `POST /api/uploads` → `process_user_upload` → attach to session → retrieval scoped to user + session attachments.

---

## 4. Agent & retrieval integration

| Data capability | Implementation touchpoints |
|-----------------|----------------------------|
| Statute chunks | `retrieve_multi_query` → answerer → citation enricher |
| Session attachments | `user_upload_chunks`; retrieval filter by `user_id` + attachment IDs |
| Weak retrieval refusal | `min_rerank_score`, `min_relevant_chunks` in config |
| Temporal / as-of (planned) | `enactment_date` on `SourceDocument`; chunk `metadata` |
| Amendment graph (planned) | Retrieval boost / filter on `status` in chunk metadata |
| `judgment` type (planned) | New `DocType`; citation UI “Court held…” vs “Law says…” |
| Jurisdiction (planned) | Clarifier + retrieval filter on `jurisdiction` |
| Full-graph eval (planned) | `dharmiq-eval` should call LangGraph path, not only `run_eval_rag` |

---

## 5. High Court — deferred standalone project

**Decision:** Full HC indexing (~17.8M judgments, ~1.25 TiB) is **not feasible** in the main Dharmiq Postgres stack for the foreseeable future.

Treat HC as a **future standalone initiative** to explore:

- Metadata-only layer (Parquet / DuckDB / Athena on AWS bucket)
- Lazy PDF fetch + parse on demand
- Separate vector store or partitioned index
- Citation-by-metadata without full-text embed of entire HC

Main app: **SC case law first (v0.11)** on manageable scale (~35k PDFs). HC references may link out until standalone project delivers a queryable tier.

---

## 6. Storage tiers & scale

### 6.1 Source size reference

| Corpus | Documents | Raw size | Est. child chunks | Main-app index? |
|--------|-----------|----------|-------------------|-----------------|
| MVP statute | 50–200 | 0.5–2 GB | 50k–200k | **Yes — now** |
| Central curated | 2k–5k | 5–20 GB | 2M–10M | After v0.5 gate |
| SC judgments | ~35k | ~52–69 GB | 0.5M–2M | v0.11 |
| HC judgments | ~17.8M | ~1.25 TiB | 100M+ | **No — standalone** |

### 6.2 Postgres / pgvector math

~**3.2 KB per child chunk** (384-dim vector + text + metadata, order of magnitude).

| Chunks | Est. DB footprint | Verdict |
|--------|-------------------|---------|
| 200k | ~0.6 GB | MVP OK |
| 2M | ~6 GB | OK with 8–16 GB RAM |
| 10M+ | 32 GB+ | Needs redesign before attempting |

**Embedding:** Local `all-MiniLM-L6-v2` on millions of chunks = long Celery backfill. Stay local for MVP subset; revisit at v0.6 expansion.

### 6.3 Tier model

| Tier | Contents | Store |
|------|----------|-------|
| **H0 — Hot** | MVP + curated central statute | Postgres `document_chunks` |
| **H1 — Warm** | Expanded central + SC | Postgres (or dedicated vector DB if >~10M chunks) |
| **C1 — Cold** | Full PDF archives | Filesystem / S3 / AWS public buckets |
| **C2 — Metadata** | HC Parquet | DuckDB / Athena — not in app DB |
| **U — User** | Uploads | `data/uploads/{user_id}/` + PG |

### 6.4 Server guidance (single-node beta)

From [`deployment.md`](../deployment.md): 4 GB RAM min, **8 GB recommended**.

| Phase | Hot index | RAM | Disk |
|-------|-----------|-----|------|
| **v0.5** | MVP subset | 8 GB | 40 GB |
| **v0.6** | Curated central | 16 GB | 100 GB |
| **v0.11** | + SC | 16–32 GB | 200 GB |

Monitor: `pg_database_size`, chunk counts, embedding OOM in Celery logs.

---

## 7. Roadmap → implementation checklist

| Version | Engineering deliverables |
|---------|-------------------------|
| **v0.5** | MVP allowlist indexed; eval JSONL committed; manual smoke runbook; optional `eval_dataset_builder`; re-baseline on v0.4 stack |
| **v0.6** | Scraper bridge; `manifest` from SQLite; temporal fields on documents; amendment metadata for MVP acts |
| **v0.7** | Eval runs full LangGraph; clarifier/upload eval datasets |
| **v0.10** | Feedback → eval review export |
| **v0.11** | `DocType.JUDGMENT`; SC ingestion from AWS; judgment citation UX |
| **v0.12** | State allowlist + dedup in scraper bridge |
| **HC project** | Separate repo/design — not blocking main roadmap |

---

## 8. Self-hosting & corpus bootstrap

Dharmiq is open source; self-hosters need **some** indexed PDFs before chat is useful.

**Decision (v0.5): Option A — documented allowlist only.** No corpus tarball shipped with the repo in v0.5.

1. **MVP corpus allowlist:** [`v0.5/mvp-corpus-allowlist.yaml`](./v0.5/mvp-corpus-allowlist.yaml) (26 central instruments).  
2. Self-hoster downloads PDFs manually or runs `indian-law-dataset-scraper` with the same allowlist → `data/corpus/india_code/raw/` + optional `manifest.json`.  
3. Run `sync_india_code_pdfs` as today.

**Optional later:** release `mvp-corpus.zip` (~20 PDFs) for one-command bootstrap — not required for v0.5.

We do **not** ship terabytes with the repo. Default story: **index the documented small subset first**; expand when eval proves quality.

---

## 9. CI & testing

| Check | Corpus needs |
|-------|--------------|
| `pytest -m "not slow"` | DB fixtures; `_seed_corpus` in smoke test |
| `test_v02_e2e_smoke.py` | Synthetic/minimal corpus in `tmp_path` |
| Live `dharmiq-eval` | Nightly/manual; MVP subset on runner or dev machine |
| Compose integration (v0.5) | Bind-mount minimal `data/corpus` or seed script |

---

## 10. Maintenance

- Log **measured** chunk counts and `pg_database_size` after each indexing run (append to version plan or here).  
- When adding a pipeline, update §3.2 and link PRD/TRD.  
- When eval schema extends, update [`dataset_format.md`](../../backend/dharmiq/eval/dataset_format.md) + [`datasets.md`](./datasets.md).

---

*Implementation changes that affect storage or ingestion should update this doc in the same PR.*
