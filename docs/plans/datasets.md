# Dharmiq — Data strategy, evals & benchmarks

**Status:** Living document · **Last updated:** 2026-06-22  
**Audience:** Product, eval owners, legal reviewers, engineering (what to build)  
**Owner:** Founder (transferable role — see §10)  
**Companion:** [`data-implementation.md`](./data-implementation.md) (pipelines, storage, Dharmiq code paths)  
**Related:** [`roadmap.md`](./roadmap.md) · [`principles.md`](../principles.md) · [`v02-eval-baseline.md`](./v02-eval-baseline.md)

This document answers **what data Dharmiq needs**, **which external sources matter**, **what eval/benchmark gaps exist**, and **how to create missing datasets**. For ingestion, Postgres sizing, and agent wiring, see [`data-implementation.md`](./data-implementation.md).

---

## 1. First principles

Dharmiq is a **grounded legal information system** ([`principles.md`](../principles.md)): claims trace to sources; repealed law is wrong law; weak retrieval → refusal.

| Role | Question | If missing |
|------|----------|------------|
| **Corpus** | What authoritative text do we retrieve? | Hallucination |
| **Metadata** | Which version, jurisdiction, date? | IPC cited instead of BNS |
| **Eval / benchmark** | Can we prove quality? | “Accurate” is asserted (§1.6) |
| **Operational** | Feedback, usage, cost? | Silent decay |

### 1.1 Corpus vs eval

| | Corpus | Eval dataset |
|---|--------|--------------|
| **Used at** | Runtime RAG | `dharmiq-eval`, CI/nightly |
| **Location** | Indexed PDFs → DB chunks | `data/eval/datasets/*.jsonl` |
| **Updates** | Continuous | Versioned baselines |

Third-party QA (IndicLegalQA, Grahak-Nyay) **adapts into eval**; it does not replace indexing the underlying statutes.

### 1.2 Statute-first, judgment-second

**v0.5–v0.6:** MVP statute quality gate → central IndiaCode expansion.  
**v0.11:** Supreme Court case law.  
**HC:** Not in main product scope — standalone project later ([`data-implementation.md` §5](./data-implementation.md#5-high-court--deferred-standalone-project)).

### 1.3 Complete data vision (product)

Beyond today’s PDF RAG:

- Temporal graph (act ↔ amendment ↔ repeal)
- Jurisdiction (central vs state)
- Citizen eval suites (plain language, clarifier paths, refusal calibration)
- Multilingual statutory text (v0.14)
- Adversarial / off-topic sets
- Feedback → regression candidates

---

## 2. Decided product choices

| Topic | Decision |
|-------|----------|
| **Eval owner** | Founder for now; role may transfer — document review criteria in §10 |
| **Licensing** | Defer formal review until pre-release; note sources in catalog §3 |
| **HC indexing** | Not feasible in main app; future **standalone project** |
| **Consumer eval seed** | Start from **Grahak-Nyay**; add Dharmiq-owned Q&A over time |
| **Scale strategy** | **Small subset first** — prove eval gates, then expand corpus |
| **Self-host corpus** | **Documented MVP allowlist** — no bundled tarball in v0.5; self-hosters fetch PDFs per allowlist / scraper |
| **BhashaBench-Legal** | **Weak indicator** — optional periodic benchmark; never a merge gate (see §5.3) |
| **CI / automation** | **Deferred** post–v0.5 — manual runbook in v0.5 PRD §4.5 |
| **Live eval** | **Advisory** — manual runs; does not block merges |
| **Embeddings / infra** | Keep simple (local embed, single Postgres) until subset gates pass |

**v0.5 PRD defaults** (see [`v0.5/prd.md`](./v0.5/prd.md)): re-baseline on v0.4 stack before enforcing targets; live eval via `run_eval_rag` for v0.5 (full LangGraph eval stretch / v0.7).

---

## 3. External sources catalog

### 3.1 Summary matrix

| Source | Type | Scale | Phase | Priority |
|--------|------|-------|-------|----------|
| [IndiaCode](https://www.indiacode.nic.in/) | Statute | Full national + state | v0.6, v0.12 | High |
| [`indian-law-dataset-scraper`](file:///home/ankk98/repos/indian-law-dataset-scraper) | Statute metadata + PDFs | ~15k metadata rows | v0.5–v0.6 | **High** |
| [AWS SC judgments](https://registry.opendata.aws/indian-supreme-court-judgments/) | Case law | ~35k PDFs, ~52–69 GB | v0.11 | High |
| [AWS HC judgments](https://registry.opendata.aws/indian-high-court-judgments/) | Case law | ~17.8M, ~1.25 TiB | Standalone project | Metadata only for now |
| [KanoonGPT / indian-case-laws](https://huggingface.co/datasets/KanoonGPT/indian-case-laws) | Case metadata | SC + 25 HC; `sample` variant | v0.11 prep | Medium |
| [overthelex/indian-court-decisions](https://huggingface.co/datasets/overthelex/indian-court-decisions) | Case text | ~14.6M rows | v0.11 | Medium |
| [IndicLegalQA](https://data.mendeley.com/datasets/gf8n8cnmvc) | Eval QA | 10k SC judgment QAs | v0.11 eval | Medium |
| [BhashaBench-Legal](https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal) | Eval MCQ | 24,365 Qs | Supplementary | Low–Med |
| [Grahak-Nyay](https://github.com/ShreyGanatra/GrahakNyay) | Consumer QA | ~887 + 52 + 303 chat | **v0.5 seed** | Medium |
| [IL-TUR](https://huggingface.co/datasets/Exploration-Lab/IL-TUR) | Benchmark tasks | Statute ID, CJPE, etc. | v0.7, v0.14 | Low–Med |
| [ILDC](https://github.com/Exploration-Lab/CJPE) | Research | 35k SC | Avoid (CC-BY-NC) | Low |
| District courts / gazettes | Various | Huge / fragmented | Defer | Low |

License details: defer to pre-release; ILDC remains **out** for commercial corpus use.

---

## 4. Source notes

### 4.1 IndiaCode scraper

CLI: `indiacode metadata` → `download` → `export-csv`.  
Captures enactment/enforcement dates, departments, related PDFs.  
**Gaps:** `relationships` table unused; state duplicates; BNS sometimes mis-typed.

**MVP allowlist signals:**

| Domain | Filter hints |
|--------|--------------|
| Fundamental rights | Constitution (central), BNSS, BNS |
| Consumer | Consumer Protection Act 2019 |
| Employment | Industrial Disputes Act, Payment of Wages |

Bridge to Dharmiq: [`data-implementation.md` §3.3](./data-implementation.md#33-indiacode-scraper--dharmiq-v06).

### 4.2 AWS Supreme Court judgments

CC-BY-4.0 · `s3://indian-supreme-court-judgments` · Parquet + PDF tar.  
~35k English judgments — feasible for v0.11 full SC index on a larger single server.

### 4.3 AWS High Court judgments

~17.8M judgments · ~1.25 TiB. **Not** a main-app indexing target. Use Parquet for research/subset selection only until standalone HC project exists.

### 4.4 Grahak-Nyay (consumer eval seed)

ACL 2025 · [repo](https://github.com/ShreyGanatra/GrahakNyay).

| Sub-dataset | Size | Use |
|-------------|------|-----|
| GeneralQA | 52 pairs | CPA 2019 basics → adapt to `v1_consumer` |
| SectoralQA | ~835 pairs | Sector topics (telecom, banking, …) |
| NyayChat | 303 conversations | Clarifier / multi-turn patterns (v0.7) |
| SyntheticQA | RAG eval | Methodology reference |

**Plan:** Import and map to Dharmiq JSONL with `expected_citations` (CPA sections). Strip or rewrite forum-contact / procedural content if out of product scope. Replace/extend with **Dharmiq-authored** citizen questions as quality matures.

### 4.5 Other eval-oriented sources

| Dataset | Use | Caveat |
|---------|-----|--------|
| IndicLegalQA | v0.11 case-law eval adapter | Judgment-centric |
| IL-TUR / ILSI | Retrieval / statute ID | Not citizen chat |
| KanoonGPT `sample` | Integration fixtures | Tiny |

---

## 5. Eval & benchmark strategy

### 5.1 Quality metrics (v0.5 gate)

From [`v02-eval-baseline.md`](./v02-eval-baseline.md):

| Metric | Target |
|--------|--------|
| Faithfulness (Ragas) | ≥ 0.85 |
| Answer correctness | ≥ 0.80 |
| LLM citation correctness | ≥ 0.95 |
| Retrieval recall@5 | ≥ 0.77 |
| Blockquote met (statutory) | ≥ 0.80 |
| Refusal correct | ≥ 0.90 |

Re-baseline on **v0.4 LangGraph stack** before treating targets as binding.

### 5.2 CI vs nightly

| Gate | When | Corpus |
|------|------|--------|
| pytest smoke (mocked LLM) | Every PR | Synthetic / minimal |
| `dharmiq-eval` live | Nightly / manual | MVP indexed subset |
| Regression vs baseline | After harness ships | Same subset, pinned model |

### 5.3 BhashaBench-Legal — weak indicator (not a gate)

[BhashaBench-Legal](https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal): **24,365 multiple-choice** questions from Indian judicial/bar exams (English + Hindi).

| Aspect | Implication for Dharmiq |
|--------|----------------------|
| Format | MCQ / assertion-reason — not open-ended RAG answers |
| Style | Exam precision, not citizen phrasing | 
| Domains | Constitutional (3,609), consumer (75), employment (175), criminal, etc. |
| Grounding | Questions test **memorized legal knowledge**, not citation to retrieved IndiaCode text |

**Why not a merge gate:** Dharmiq gates measure **faithfulness to retrieved sources**, blockquotes, and refusal on weak retrieval. BhashaBench measures **exam-style knowledge** — a model can score well while hallucinating citations in our pipeline.

**How to use it:**

1. **Domain coverage audit** — “Do we have corpus for areas where we score low?”  
2. **Hindi smoke (v0.14)** — Hindi subset for locale readiness, not statutory grounding.  
3. **Optional quarterly report** — track trends; never block PRs.  
4. **If adapted to JSONL** — rewrite MCQs as descriptive citizen questions + add `expected_citations` from indexed acts; labor-intensive; low priority.

**Recommendation:** Track as **weak indicator** in optional quarterly reports — domain coverage sanity check, not grounding quality. Invest in **`v1_*` citizen JSONL** for all gating.

**Dharmiq tool (v0.5 P7):** `backend/dharmiq/eval/tools/bhashabench_sample.py` — dry-run offline plan or live HF sample IDs; append-only log at `data/eval/runs/bhashabench_log.md`. See [`manual-test-runbook.md`](./v0.5/manual-test-runbook.md) §6.

---

## 6. Gap analysis

### 6.1 What does not exist (must build)

| Gap | Phase | Create how |
|-----|-------|------------|
| Citizen statutory Q&A (employment, police) | v0.5 | Manual + templates; scraper section hints |
| `v1_consumer` (grounded CPA) | v0.5 | **Grahak seed** → refine citations |
| Refusal / adversarial | v0.5 | Auto weak-retrieval + human labels |
| Revised-law (IPC→BNS) | v0.5 | Scraper pairs + human review |
| Needle-in-haystack (statute) | v0.5 | Auto from indexed sections + audit |
| Clarifier multi-turn | v0.7 | Scripted `facts` + expected followups |
| Upload + statute joint | v0.7 | Synthetic contracts |
| Conflicting sources | v0.7 | Manual real conflicts |
| Case law eval | v0.11 | IndicLegalQA adapter + own SC set |
| Hindi statutory eval | v0.14 | Parallel corpus required |
| Feedback → eval | v0.10 | Export 👎 to review queue |
| Amendment graph | v0.6 | Scraper + manual MVP acts |
| HC at scale | Standalone | Separate project |

### 6.2 Automated vs human

| Work | Code can | Human must |
|------|----------|------------|
| Section-targeted questions | Generate from chunk index | Approve answers & citations |
| Grahak import | Convert to JSONL schema | Fix CPA section mapping |
| Needle-in-haystack | Insert target section, emit Q | ~10% audit |
| Refusal set | Empty corpus / wrong domain queries | Confirm `expect_refusal` |
| Revised-law | Pair metadata from scraper | Label “must cite BNS” |
| Gating datasets | — | **Owner sign-off** (§10) |

**Rule:** Automation proposes; **eval owner approves** anything that blocks release.

### 6.3 Dharmiq-owned dataset inventory

| ID | ~Size | Phase | Gate? |
|----|-------|-------|-------|
| `v1_fundamental_rights` | 30–80 | v0.5 | Yes |
| `v1_consumer` | 40–100 | v0.5 | Yes |
| `v1_employment` | 40–100 | v0.5 | Yes |
| `v1_refusal_adversarial` | 20–40 | v0.5 | Yes |
| `v1_revised_law` | 15–30 | v0.5 | Yes |
| `v1_needle_statute` | 20–50 | v0.5 (+ v0.6 extensions) | Yes |
| `v1_property` | 15–20+ | v0.6 | Yes |
| `v1_tax` | 15–20+ | v0.6 | Yes |
| `v1_cyber` | 15–20+ | v0.6 | Yes |
| `v1_clarifier_multi` | 15–25 | v0.7 | Soft |
| `v1_upload_attach` | 15–25 | v0.7 | Soft |
| `v1_case_law_sc` | 50–100 | v0.11 | Yes |
| `v1_hindi_statute` | 30–50 | v0.14 | Yes |
| `v1_general_citizen` | 200+ | v0.12 | Yes |

**Planned schema extensions** (see [`dataset_format.md`](../../backend/dharmiq/eval/dataset_format.md)):

`source_type`, `jurisdiction`, `as_of_date`, `clarifier_turns`, `locale`, `difficulty`.

---

## 7. Roadmap — data & eval focus

| Version | Data / eval work |
|---------|------------------|
| **v0.5** | MVP subset + all `v1_*` gating sets; harness; smoke CI |
| **v0.6** | Central allowlist expansion; per-domain recall |
| **v0.7** | Clarifier, upload, ambiguity sets |
| **v0.10** | Feedback → eval queue |
| **v0.11** | SC corpus + `v1_case_law_sc` |
| **v0.12** | State statute + `v1_general_citizen` |
| **v0.14** | Hindi eval |

Do not expand corpus breadth (v0.6+) until v0.5 statute gates pass.

---

## 8. References

| Resource | Link |
|----------|------|
| Implementation / pipelines | [`data-implementation.md`](./data-implementation.md) |
| IndiaCode scraper | `~/repos/indian-law-dataset-scraper` |
| AWS SC / HC | [SC](https://registry.opendata.aws/indian-supreme-court-judgments/) · [HC](https://registry.opendata.aws/indian-high-court-judgments/) |
| Grahak-Nyay | https://github.com/ShreyGanatra/GrahakNyay |
| BhashaBench-Legal | https://huggingface.co/datasets/bharatgenai/BhashaBench-Legal |
| IndicLegalQA | https://data.mendeley.com/datasets/gf8n8cnmvc |
| Eval format | `backend/dharmiq/eval/dataset_format.md` |

---

## 9. Eval owner role (transferable)

**Current owner:** Founder.

**Responsibilities:**

- Approve new/edited rows in gating JSONL datasets  
- Sign off on baseline updates in `v02-eval-baseline.md`  
- Triage 👎 feedback candidates for promotion to eval  
- Decide when third-party seeds (Grahak) are “good enough” vs rewritten  

**Handoff checklist for a future owner:**

1. Read [`principles.md`](../principles.md) §1 (trustworthiness)  
2. Run `dharmiq-eval` on MVP subset; understand metric definitions  
3. Review schema in `dataset_format.md`  
4. Maintain separation: supplementary benchmarks (BhashaBench) vs gating sets (`v1_*`)

---

## 10. Maintenance

- Update §3 when new public datasets appear.  
- After each v0.5+ baseline run, update `v02-eval-baseline.md`.  
- Link version PRDs to this doc (eval) and `data-implementation.md` (pipelines).

---

*New gating eval rows or external source adoption → update this doc in the same PR.*
