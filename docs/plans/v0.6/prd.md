# Dharmiq v0.6 — Central statute corpus PRD

**Status:** Draft  
**Version:** 0.6  
**Baseline:** v0.5 (MVP corpus allowlist, eval harness, smoke tests, advisory regression gate)  
**Last updated:** 2026-06-23

Related: [`roadmap.md`](../roadmap.md) · [`datasets.md`](../datasets.md) · [`data-implementation.md`](../data-implementation.md) · [`v0.5/prd.md`](../v0.5/prd.md) · [`v02-eval-baseline.md`](../v02-eval-baseline.md) · [`principles.md`](../../principles.md)

---

## Clarification summary (Round 1)

| Topic | Decision |
|-------|----------|
| **v0.6 purpose** | Expand **central statutory** coverage with temporal correctness — not case law, not state corpus |
| **Corpus scale** | **Tier A** — ~50–80 **new** instruments on top of the 26-instrument MVP allowlist (~**76–106 total**) |
| **New domains** | **Property**, **taxation**, **cyber/privacy** (in addition to retained MVP domains: rights, consumer, employment) |
| **Subordinate legislation** | **Acts + essential rules** for all v0.6 domains where IndiaCode has them (not full notification corpus) |
| **v0.5 gate** | **Soft** — v0.6 planning and tooling may start now; **expanded corpus indexing and eval sign-off wait** for v0.5 operational exit |
| **As-of UX** | **Answer footnote only** — no banner/chip UI in v0.6 |
| **Case law / SC judgments** | **Out of scope** — v0.11 |
| **State IndiaCode** | **Out of scope** — v0.12 |
| **Full LangGraph eval path** | **Out of scope** — remains v0.7; v0.6 gates use `run_eval_rag()` like v0.5 |
| **CI regression automation** | **Deferred** — manual/advisory compare, same as v0.5 |
| **Licensing** | **Internal checklist + founder sign-off** — not counsel-reviewed (full legal → v0.21) |
| **Self-host bootstrap** | **Documented v0.6 allowlist** — no bundled corpus zip |

---

## 1. Vision for v0.6

v0.5 proved the **MVP statute subset + stack** are measurable. v0.6 makes Dharmiq **broader and temporally honest** within central statutory law — the next step in principles §4.2 (narrow & deep before breadth elsewhere).

Citizens asking about rent, property registration, basic tax rights, or digital privacy should get grounded answers from an expanded, curated central corpus. Answers must prefer **current law** (principles §1.4): repealed IPC must not beat BNS in retrieval; superseded CPA 1986 must not outrank CPA 2019.

**Positioning:** v0.6 is a **data + trust release**. User-visible change is modest (footnote + better coverage); the deliverable is **curated central corpus, temporal metadata, operator runbooks, and eval proof** before v0.7 quality engineering.

---

## 2. Prerequisites (v0.5 soft gate)

v0.6 **implementation** may proceed in parallel with finishing v0.5 operations. **Corpus expansion indexing** and **v0.6 release sign-off** require v0.5 operational exit:

| v0.5 exit item | Required before v0.6 ship? |
|----------------|----------------------------|
| MVP allowlist indexed (`verify_corpus_index` 26/26) | **Yes** |
| Re-baseline recorded in `v02-eval-baseline.md` | **Yes** |
| Manual smoke runbook executed | **Yes** |
| MVP suite meets targets or documented gap + plan | **Yes** (advisory, but blocking for v0.6 **release**) |
| CI/GitHub Actions | No |

**Allowed before v0.5 exit:** schema design, scraper bridge tooling, allowlist YAML drafting, unit tests with fixtures, runbook docs, eval dataset authoring (against fixture corpus).

---

## 3. Scope

### 3.1 In scope

| Area | Deliverables |
|------|----------------|
| **Corpus allowlist** | [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml) — superset of MVP 26 + ~50–80 new instruments across 6 domains |
| **Scraper bridge** | Tooling: IndiaCode scraper SQLite/CSV → allowlist → PDF copy → `manifest.json` |
| **Temporal metadata** | `status`, supersession edges, enactment/enforcement dates on `source_documents`; manifest + ingestion |
| **Retrieval policy** | Default exclude `superseded` / `repealed` from corpus search; deprioritize if included |
| **Amendment graph (MVP)** | Edges for known pairs: IPC→BNS, CrPC→BNSS, CPA 1986→2019 (+ allowlist `supersedes` fields) |
| **As-of footnote** | Answer footnote: corpus index date + in-force framing (see §7) |
| **Indexing runbook** | [`corpus-indexing-runbook.md`](./corpus-indexing-runbook.md) — add source, reindex, verify, rollback |
| **Licensing checklist** | [`licensing-checklist.md`](./licensing-checklist.md) — attribution, redistribution, takedown; founder sign-off |
| **Eval datasets** | `v1_property`, `v1_tax`, `v1_cyber` (15–20 rows each minimum); extend needle/recall for new corpus |
| **Eval harness** | `--suite v06` (MVP suite + three new datasets); `--compare baseline` regression vs v0.5 |
| **Corpus verify** | Extend `verify_corpus_index` for v0.6 allowlist; chunk-count report |
| **Docs** | Update `datasets.md`, `data-implementation.md`, `roadmap.md`, `README.md` on ship |

### 3.2 Explicitly out of scope (v0.6)

| Item | Target |
|------|--------|
| Supreme Court / case law ingestion | v0.11 |
| State acts (rent control, state GST, etc.) | v0.12 |
| Full central IndiaCode (~8k+ acts) | Deferred — subset quality first |
| Full amendment graph for all central acts | Deferred — MVP edges only |
| User-visible temporal banner/chip UI | v0.7 (if needed) |
| Conflicting-sources side-by-side UI | v0.7 |
| Admin reindex UI | v0.10 |
| Hindi statutory answers | v0.14 |
| Bundled `corpus.zip` for self-hosters | Optional post–v0.6 |
| Counsel-reviewed licensing opinion | v0.21 |
| Automated CI eval gate | Deferred |
| Full LangGraph eval | v0.7 |

### 3.3 Exit criteria

- [ ] **v0.5 operational exit** complete (see §2)
- [x] **v0.6 allowlist** committed; `verify_corpus_index` reports **100%** instruments indexed with `chunk_count > 0` *(allowlist committed; full 62/62 index pending operator run)*
- [ ] **Chunk budget** — total child chunks ≤ **250k** (Tier A guardrail; log actual count in runbook)
- [ ] **Temporal fields** populated for **100%** of allowlist instruments (status + dates where known) *(schema + ingestion implemented; verify after P3 index)*
- [ ] **Supersession policy** — `v1_revised_law` MVP suite still passes; superseded acts excluded from default retrieval *(retrieval filter implemented; live eval pending indexed corpus)*
- [ ] **New domain evals** — `v1_property`, `v1_tax`, `v1_cyber` meet v0.5 metric targets (§6.1) on expanded corpus
- [ ] **No regression** — MVP suite (`--suite mvp`) does not regress > configured delta vs v0.5 baseline
- [x] **As-of footnote** present on statutory answers in manual smoke (3+ domains sampled) *(implemented in answerer/finalizer/eval; manual smoke pending)*
- [ ] **Licensing checklist** signed by founder
- [ ] **Indexing runbook** exercised end-to-end once on staging/dev *(runbook committed; exercise pending)*

---

## 4. Corpus allowlist (Tier A)

Authoritative list: **[`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml)** (to be created in v0.6 P0).

### 4.1 Structure

- **Superset model** — includes all 26 MVP instruments unchanged (`source_id` values stable for eval continuity)
- **Six domains** — `fundamental_rights`, `consumer`, `employment` (MVP + deepen), `property`, `tax`, `cyber`
- **Per-instrument fields** (extends MVP YAML):

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Stable `IN-*` source_id |
| `title` | yes | Display title |
| `doc_type` | yes | `act`, `rule`, `regulation`, `notification` |
| `status` | yes | `in_force`, `superseded`, `repealed` |
| `supersedes` | no | List of `id` this instrument replaces |
| `superseded_by` | no | `id` of replacement (for superseded rows) |
| `enactment_date` | when known | ISO date |
| `enforcement_date` | when known | ISO date (commencement) |
| `india_code_handle` | recommended | For scraper/download |
| `scraper_instrument_id` | recommended | `indian-law-dataset-scraper` row |
| `canonical_url` | recommended | IndiaCode handle URL |
| `eval_topics` | recommended | Tags for eval authoring |
| `include_rules` | no | Parent act `id` if this is subordinate legislation |

### 4.2 Target counts

| Domain | MVP base | v0.6 add (acts + rules) | v0.6 domain total (approx.) |
|--------|----------|-------------------------|-----------------------------|
| Fundamental rights | 10 | +2–4 rules (e.g. BNSS-related central rules if available) | 12–14 |
| Consumer | 7 | +3–5 rules (CPA E-Commerce Rules 2020, CP Rules 2020, etc.) | 10–12 |
| Employment | 9 | +2–4 rules (POSH rules, CLRA rules where central) | 11–13 |
| **Property** | 0 | **+14–18** | 14–18 |
| **Tax** | 0 | **+12–16** | 12–16 |
| **Cyber** | 0 | **+8–12** (DPDP, IT Rules; IT Act already in consumer MVP) | 8–12 |
| **Total** | **26** | **~50–80 new** | **~76–106** |

**Hard cap:** 110 instruments in v0.6 allowlist without PRD amendment.

### 4.3 Candidate instruments (curated starting point)

Engineering + eval owner finalize in P0. **Central only** — no state rent-control or state GST acts.

#### Property (priority acts)

| `id` (proposed) | Instrument |
|-----------------|------------|
| `IN-RERA-2016` | Real Estate (Regulation and Development) Act, 2016 |
| `IN-TPA-1882` | Transfer of Property Act, 1882 |
| `IN-REGISTRATION-1908` | Registration Act, 1908 |
| `IN-STAMP-1899` | Indian Stamp Act, 1899 |
| `IN-LARR-2013` | Right to Fair Compensation and Transparency in Land Acquisition, Rehabilitation and Resettlement Act, 2013 |
| `IN-EASEMENTS-1882` | Indian Easements Act, 1882 |

Plus **2–6 central rules/regulations** under RERA, Registration, or LARR where IndiaCode hosts them.

#### Tax (citizen-facing subset)

| `id` (proposed) | Instrument |
|-----------------|------------|
| `IN-ITA-1961` | Income-tax Act, 1961 |
| `IN-CGST-2017` | Central Goods and Services Tax Act, 2017 |
| `IN-IGST-2017` | Integrated Goods and Services Tax Act, 2017 |
| `IN-GST-COMPENSATION-2017` | GST (Compensation to States) Act, 2017 (optional — lower priority) |

Plus **4–8 GST / income-tax rules** that govern citizen-visible obligations (registration thresholds, returns basics, TDS on salary — eval-scoped, not full rule corpus).

**Explicitly exclude in v0.6:** state GST acts, Finance Act annual amending bundles (reference via ITA/CGST only), deep customs/excise unless a eval question requires it.

#### Cyber / privacy

| `id` (proposed) | Instrument |
|-----------------|------------|
| `IN-DPDP-2023` | Digital Personal Data Protection Act, 2023 |
| `IN-IT-RULES-2021` | Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021 (or current central IT rules) |
| `IN-IT-RULES-SPDI` | Information Technology (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011 (if still cited) |

`IN-IT-2000` remains in MVP consumer domain — **do not duplicate**; cross-link in allowlist `notes`.

### 4.4 MVP deepen (rules)

Promote items from MVP `optional_later` and add essential subordinate law:

- `IN-CPA-RULES-ECOMMERCE-2020` — Consumer Protection (E-Commerce) Rules, 2020
- Consumer Protection (General) Rules, 2020 (or current central CP Rules)
- Other central rules **only** where eval questions or citizen FAQs require them

### 4.5 Sourcing workflow

```bash
# 1. Scraper (separate repo)
cd ~/repos/indian-law-dataset-scraper
indiacode init
indiacode metadata --scope central
indiacode download --scope central --extract-text --resume
indiacode export-csv --out dist/csv

# 2. Dharmiq bridge (v0.6 tooling)
cd dharmiq/backend
uv run python -m dharmiq.eval.tools.import_indiacode_allowlist \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml \
  --scraper-db ~/repos/indian-law-dataset-scraper/data/indiacode.sqlite \
  --corpus-dir ../data/corpus/india_code/raw \
  --write-manifest

# 3. Index
uv run celery -A celery_app call dharmiq.ingestion.sync_india_code_pdfs

# 4. Verify
uv run python -m dharmiq.eval.tools.verify_corpus_index \
  --allowlist ../docs/plans/v0.6/central-corpus-allowlist.yaml
```

**Self-hosters:** same allowlist YAML + scraper or manual PDF download → `sync_india_code_pdfs`.

### 4.6 Allowlist versioning

- Bump `version` in YAML on any add/remove/`source_id` change
- Eval run metadata records `allowlist_version` + `allowlist_sha256` (extend v0.5 metadata path to default v0.6 file when `--suite v06`)
- MVP eval rows **must not** change `required_source_ids` without eval owner review

---

## 5. Temporal metadata & amendment graph

Principles §1.4: *current law > stale law*. v0.6 makes this **machine-enforceable** in retrieval, not just prompt guidance.

### 5.1 Database & manifest

Extend `source_documents` (Alembic migration):

| Column | Type | Notes |
|--------|------|-------|
| `status` | enum | `in_force`, `superseded`, `repealed` — default `in_force` for legacy rows |
| `superseded_by_source_id` | string, nullable | `IN-*` id of replacement act |
| `enforcement_date` | date, nullable | Commencement / enforcement |
| `canonical_url` | string, nullable | IndiaCode link (today manifest-only) |
| `instrument_metadata` | JSONB | Scraper extras: ministry, department, repeal_info |

`enactment_date` and `version` already exist — populate from manifest/scraper on ingest.

**Manifest** (`manifest.json`) carries the same fields; `scanner.py` + `_register_scanned_document` must persist them.

### 5.2 Amendment graph (MVP scope)

New table `statute_relationships` **or** JSONB array on allowlist exported to DB at index time:

| `from_source_id` | `to_source_id` | `relationship` |
|------------------|----------------|----------------|
| `IN-IPC-1860` | `IN-BNS-2023` | `superseded_by` |
| `IN-CRPC-1973` | `IN-BNSS-2023` | `superseded_by` |
| `IN-CPA-1986` | `IN-CPA-2019` | `superseded_by` |

**Not in v0.6:** automated ingestion of all scraper `relationships` rows (table unused in scraper today). Manual/allowlist-driven edges only.

### 5.3 Retrieval policy

| Rule | Behavior |
|------|----------|
| Default corpus search | `WHERE status IS NULL OR status = 'in_force'` |
| Superseded sources | **Excluded** from hybrid search unless config `retrieval.include_superseded=true` (self-host debug only) |
| Reranker tie-break | Boost chunks from `in_force` documents when scores within ε |
| User asks about old law name ("IPC section 302") | Rewriter/clarifier may retrieve BNS; `v1_revised_law` eval enforces correct citation |

**Regression:** all `v1_revised_law` rows must pass after retrieval change.

### 5.4 Validator / answerer hints

- Answerer prompt: prefer in-force instruments when retrieved set includes both sides of a supersession edge
- Validator: flag answer that cites only `superseded` sources when an `in_force` successor was retrieved

(Full validator rules → v0.7; v0.6 ships retrieval filter + prompt + eval gate.)

---

## 6. Eval & benchmarks

### 6.1 Quality metrics (unchanged targets)

From [`v02-eval-baseline.md`](../v02-eval-baseline.md) — apply to **each new dataset** and rolled-up v0.6 suite:

| Metric | Target |
|--------|--------|
| Faithfulness (Ragas) | ≥ 0.85 |
| Answer correctness | ≥ 0.80 |
| LLM citation correctness | ≥ 0.95 |
| Retrieval recall@5 | ≥ 0.77 |
| `blockquote_met` (statutory Qs) | ≥ 0.80 |
| `refusal_correct` | ≥ 0.90 |
| `revised_law_met` | ≥ 0.95 (MVP suite — no regression) |

### 6.2 New gating datasets

| Dataset | Min rows | Focus |
|---------|----------|-------|
| `v1_property` | 15 | RERA disclosure, rent deposit, registration, stamp duty basics, land acquisition compensation |
| `v1_tax` | 15 | ITR filing basics, TDS on salary, GST registration threshold, input tax credit citizen FAQ |
| `v1_cyber` | 15 | DPDP rights, IT Act cybercrime reporting, intermediary complaints, reasonable security |

**Authoring rules:**

- Citizen phrasing; `expected_citations` with `source_id` + section
- `required_source_ids` must be in v0.6 allowlist
- No state-law questions; no case-law citations
- Eval owner sign-off ([`datasets.md` §9](../datasets.md#9-eval-owner-role-transferable))

**Needle/recall:** add ≥10 new `v1_needle_statute` rows targeting property/tax/cyber sections (append to existing file or `v1_needle_statute_v06` — prefer single file with topic tags).

### 6.3 Suites & regression

| Suite | Datasets | When |
|-------|----------|------|
| `mvp` | Existing six v0.5 datasets | Regression guard — must not regress vs v0.5 baseline |
| `v06` | MVP six + `v1_property` + `v1_tax` + `v1_cyber` | v0.6 release gate (advisory manual) |

```bash
cd backend
uv run dharmiq-eval --suite v06 --compare baseline
uv run dharmiq-eval --suite mvp --compare baseline   # regression-only
```

After passing v0.6: `uv run dharmiq-eval --suite v06 --write-baseline --yes` — updates `data/eval/runs/baseline.json` with v0.6 corpus metadata.

### 6.4 Eval path

**`run_eval_rag()` only** (same as v0.5). Document gap vs production LangGraph in run metadata. Full-graph eval remains v0.7.

---

## 7. As-of footnote (user-visible)

**Decision:** footnote only — no banner, chip, or Settings toggle.

### 7.1 Content

Append to every **statutory** answer (not pure refusal):

```text
---
Sources indexed: YYYY-MM-DD (UTC). Citations refer to central law as indexed; confirm critical details with a qualified lawyer.
```

When answer cites a specific act with `enforcement_date` in metadata, optional inline clause:

```text
… cites the <Act title> as in force (commenced YYYY-MM-DD) …
```

### 7.2 Implementation touchpoints

| Layer | Change |
|-------|--------|
| Config | `corpus.indexed_at` — set on successful full-corpus sync (max `source_documents.indexed_at`) |
| Answerer | Prompt instruction + post-processor append footnote (idempotent — don't duplicate if model already added) |
| Validator | Allow footnote block; do not strip |
| Frontend | Render footnote markdown (no new component — existing answer surface) |

**Not in v0.6:** per-answer dynamic "today's law" — we state **corpus index date**, not live IndiaCode sync time.

---

## 8. Licensing & attribution

Internal checklist: [`licensing-checklist.md`](./licensing-checklist.md).

### 8.1 Minimum checklist items

| # | Item | Owner |
|---|------|-------|
| 1 | Document IndiaCode as primary source; link terms of use | Engineering |
| 2 | UI attribution on citation hover/footer — "Text from IndiaCode" + `canonical_url` | Engineering |
| 3 | Redistribution policy for self-hosters (may index same PDFs; no Dharmiq trademark on verbatim law text) | Founder |
| 4 | Takedown / correction contact (GitHub issue + email) | Founder |
| 5 | Confirm no NC/research-only datasets (e.g. ILDC) in corpus | Eval owner |
| 6 | Founder sign-off row in checklist | Founder |

**Not required in v0.6:** external counsel review, DPDP compliance memo (v0.13).

---

## 9. Operator runbooks

[`corpus-indexing-runbook.md`](./corpus-indexing-runbook.md) must cover:

1. **Add instrument** — edit allowlist → import PDF → manifest → sync → verify  
2. **Update instrument** — new PDF hash → version bump → reindex → eval smoke  
3. **Remove instrument** — soft-delete or purge chunks; eval `required_source_ids` audit  
4. **Full reindex** — Celery sync task, expected duration, disk/RAM (16 GB recommended per `data-implementation.md`)  
5. **Rollback** — restore previous PDF + manifest from git or backup; re-sync  
6. **Metrics to log** — `corpus_document_count`, `corpus_chunk_count`, `pg_database_size`, allowlist version  

---

## 10. User stories

### Story 1 — Citizen: property question

As a tenant, I ask whether my landlord must register a rent agreement. Dharmiq answers using Registration Act / state-agnostic central rules where applicable, cites sections, and footnotes the corpus index date.

### Story 2 — Citizen: tax basics

As a salaried employee, I ask what TDS means on my payslip. Dharmiq answers from Income-tax Act provisions with citations, without inventing slab rates not in retrieved text.

### Story 3 — Citizen: digital privacy

As a user, I ask what rights I have when a company leaks my phone number. Dharmiq answers from DPDP Act 2023 with grounded citations.

### Story 4 — Operator: expand corpus safely

As an operator, I add a new central rule to the allowlist, run the import script and verify tool, and see chunk counts before running `dharmiq-eval --suite v06`.

### Story 5 — Eval owner: no regression

As eval owner, I run `--suite mvp --compare baseline` after retrieval changes and block v0.6 release if `v1_revised_law` or faithfulness regresses beyond TRD delta.

### Story 6 — Self-hoster

As a self-hoster, I follow the v0.6 allowlist and scraper bridge docs to index the same ~76–106 instruments without a bundled zip.

---

## 11. Implementation phases (suggested)

| Phase | Focus | Done when |
|-------|-------|-----------|
| **P0** | `central-corpus-allowlist.yaml` draft + `import_indiacode_allowlist` bridge | Allowlist reviewed; bridge copies PDFs + manifest for fixture subset |
| **P1** | DB migration + ingestion reads temporal fields | Manifest dates/status persist; unit tests |
| **P2** | Retrieval supersession filter + MVP graph edges | `v1_revised_law` passes on fixture corpus |
| **P3** | Index Tier A corpus (after v0.5 exit) | `verify_corpus_index` 100%; chunk log |
| **P4** | Eval datasets property/tax/cyber + needle extensions | Owner-approved JSONL committed |
| **P5** | `--suite v06` + baseline update path | Compare works; metadata uses v0.6 allowlist |
| **P6** | As-of footnote in answerer | Manual smoke shows footnote |
| **P7** | Citation `canonical_url` attribution (API + frontend) | UI links to IndiaCode when URL present |
| **P8** | Runbooks, licensing checklist, docs, version `0.6.0` | Founder sign-off; roadmap updated |

TRD: [`trd.md`](./trd.md)

---

## 12. Infrastructure & scale guardrails

From [`data-implementation.md`](../data-implementation.md):

| Resource | v0.5 (MVP) | v0.6 (Tier A) |
|----------|------------|---------------|
| Instruments | 26 | ~76–106 |
| Est. child chunks | 50k–200k | **≤250k** (hard gate) |
| RAM (single node) | 8 GB | **16 GB recommended** |
| Disk | 40 GB | **100 GB recommended** |

If chunk count exceeds 250k after indexing, **stop** and rescope allowlist before tuning chunk sizes or embeddings.

**Embeddings:** stay on local `all-MiniLM-L6-v2` + single Postgres (no vector DB migration in v0.6).

---

## 13. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Scraper mixes state/central rows | Allowlist curation + `jurisdiction: central` filter in bridge; human review |
| Tier A too small for tax/cyber depth | Eval questions scoped to indexed sections; expand in v0.6.1 only with PRD bump |
| Supersession filter hides text needed for revised-law eval | Keep superseded acts indexed but excluded from default retrieval; eval rows test BNS not IPC |
| Indexing 80 PDFs OOMs on 8 GB | Document 16 GB; batch Celery; monitor `record_ingestion_failure` |
| IndiaCode blocks scraper | Resume + conservative RPS; manual PDF drop-in path |
| `run_eval_rag` ≠ production graph | Same gap as v0.5; v0.7 closes; document in eval metadata |
| Licensing ambiguity | Checklist + attribution links; no public redistribution of corpus zip |
| v0.5 exit delayed | Soft gate allows P0–P2; P3 blocked until MVP indexed |

---

## 14. Success metrics

| Metric | Target |
|--------|--------|
| Allowlist instruments indexed | 100% |
| v0.6 suite advisory pass | All gating metrics at targets |
| MVP suite regression | No metric drops > v0.5 TRD delta |
| `v1_revised_law` pass rate | ≥ 95% |
| Licensing checklist | Signed |
| Time to v0.7 kickoff | Within 2 sprints of v0.6 exit |

---

## 15. Resolved decisions

| # | Question | Decision |
|---|----------|----------|
| 1 | Corpus scale? | Tier A — ~50–80 new (~76–106 total) |
| 2 | New domains? | Property, tax, cyber |
| 3 | Subordinate law? | Acts + essential rules per domain |
| 4 | v0.5 gate? | Soft — tooling early; indexing/release after v0.5 exit |
| 5 | As-of UX? | Answer footnote only |
| 6 | Allowlist file? | `docs/plans/v0.6/central-corpus-allowlist.yaml` (superset of MVP) |
| 7 | State rent/GST acts? | **Out** — central only |
| 8 | Case law? | **Out** — v0.11 |

---

## 16. Document history

| Date | Change |
|------|--------|
| 2026-06-23 | Initial draft from roadmap + Round 1 clarifications |

---

*On ship: update [`roadmap.md`](../roadmap.md), [`README.md`](../../../README.md) version badge, [`datasets.md`](../datasets.md), and [`data-implementation.md`](../data-implementation.md).*
