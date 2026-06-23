# v0.6 — Corpus licensing & attribution checklist

**Parent:** [`prd.md`](./prd.md) §8 · [`trd.md`](./trd.md) P8  
**Audience:** Founder, engineering, eval owner  
**Status:** Internal checklist — **not** counsel-reviewed (full legal review → v0.21)

Dharmiq indexes **central IndiaCode statutory PDFs** for RAG retrieval. This checklist records attribution, redistribution policy, and sign-off before v0.6 release.

---

## 1. Source inventory

| Source | Use in v0.6 | License / terms |
|--------|-------------|-----------------|
| [IndiaCode](https://www.indiacode.nic.in/) | Primary corpus — 62 central acts/regulations | Government of India statutory publication; review [IndiaCode](https://www.indiacode.nic.in/) terms of use |
| User uploads | Per-user documents in chat | User-owned; not redistributed |
| `indian-law-dataset-scraper` | Metadata enrichment only (handles, dates) | Separate repo; no NC datasets in corpus |

**Explicitly excluded from corpus:** ILDC and other research-only / non-commercial datasets; Supreme Court judgments (v0.11); state acts (v0.12).

---

## 2. Checklist items

| # | Item | Owner | Done? | Notes |
|---|------|-------|-------|-------|
| 1 | Document IndiaCode as primary statutory source; link terms of use in this file and README | Engineering | [x] | IndiaCode URL above; README cites corpus path |
| 2 | UI attribution on corpus citations — "View on IndiaCode" + `canonical_url` when present | Engineering | [x] | `frontend/src/lib/citations.ts`; API `CitationRecord.canonical_url` |
| 3 | Redistribution policy for self-hosters documented (may index same PDFs; no Dharmiq trademark on verbatim law text) | Founder | [ ] | See §3 below |
| 4 | Takedown / correction contact published (GitHub issue + email) | Founder | [ ] | See §4 below |
| 5 | Confirm no NC/research-only datasets (e.g. ILDC) in corpus | Eval owner | [x] | Central IndiaCode only per allowlist |
| 6 | Founder sign-off on items 1–5 | Founder | [ ] | Sign-off table §5 |

**Not required in v0.6:** external counsel review, DPDP compliance memo (v0.13).

---

## 3. Self-host redistribution policy (draft)

Self-hosters deploying Dharmiq may:

- Download the same IndiaCode PDFs via `download_indiacode_pdfs` or manual acquisition
- Index them locally using the committed [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml) and ingestion pipeline
- Attribute IndiaCode as the source of statutory text in the UI (same `canonical_url` links)

Self-hosters **must not**:

- Imply Government of India or IndiaCode endorsement of their deployment
- Apply the Dharmiq trademark to verbatim reproductions of statutory text
- Redistribute a Dharmiq-branded corpus zip as official legal publication (no bundled `corpus.zip` in v0.6)

---

## 4. Takedown & corrections

| Channel | Use |
|---------|-----|
| GitHub Issues | [github.com/Ankk98/dharmiq/issues](https://github.com/Ankk98/dharmiq/issues) — corpus errors, stale PDFs, attribution |
| Email | *(founder contact — fill before ship)* |

Corrections: update allowlist → re-download PDF → re-sync per [`corpus-indexing-runbook.md`](./corpus-indexing-runbook.md).

---

## 5. Founder sign-off

| Field | Value |
|-------|-------|
| Release | v0.6.0 |
| Allowlist | 62 instruments — [`central-corpus-allowlist.yaml`](./central-corpus-allowlist.yaml) |
| Checklist completed by | |
| Date | |
| Signature / approval | ☐ Approved for release |

---

## 6. Related docs

- [`corpus-indexing-runbook.md`](./corpus-indexing-runbook.md) — operator indexing workflow
- [`prd.md`](./prd.md) §8 — product requirements
- [`roadmap.md`](../roadmap.md) — v0.21 counsel-reviewed licensing
