# v0.2 Eval Baseline (R4-11)

This document records the **v0.1 pipeline baseline** measured before enforcing v0.2 quality targets in manual/nightly eval runs. CI does **not** gate on these numbers — only the deterministic mocked smoke suite (`test_v02_e2e_smoke.py`) blocks PRs.

## Baseline metrics (v0.1 linear RAG pipeline)

| Metric | v0.1 baseline | v0.2 target | Notes |
|--------|---------------|-------------|-------|
| Faithfulness (Ragas) | **0.74** | ≥ 0.85 | Measured on `v1_fundamental_rights` with indexed IndiaCode subset |
| Answer correctness (Ragas) | **0.71** | ≥ 0.80 | Same dataset |
| LLM citation correctness | **0.82** | ≥ 0.95 | Judge score on statutory claims |
| Retrieval recall@5 | **0.62** | ≥ 0.77 (+15%) | Section-specific questions on chunking eval subset |
| Answers with ≥1 blockquote (statutory Qs) | **0.40** | ≥ 0.80 | Manual sample on q1, q2, q6 |
| Refusal rate on weak-retrieval questions | **0.25** | tracked; false-refusal < 10% | q8-style questions; v0.1 often hallucinates |

> **How to re-measure:** Index the corpus locally, set `OPENROUTER_API_KEY`, then run:
>
> ```bash
> cd backend
> uv run dharmiq-eval --dataset v1_fundamental_rights
> ```
>
> Compare aggregate metrics in the JSON summary under `data/eval/runs/`. Update this table when re-baselining.

## v0.2 eval extensions

The committed dataset (`data/eval/datasets/v1_fundamental_rights.jsonl`) adds per-question fields:

| Field | Purpose |
|-------|---------|
| `min_citation_count` | Minimum `[n]` markers expected in the answer |
| `expect_blockquote` | Whether a Markdown blockquote is required |
| `expect_refusal` | Whether the pipeline should refuse (weak retrieval / no sources) |

The eval runner aggregates `citation_count_met`, `blockquote_met`, and `refusal_correct` alongside Ragas and LLM-judge scores.

## CI vs nightly gates

| Gate | Command | When |
|------|---------|------|
| **CI (hard)** | `uv run pytest -m "not slow" -q` | Every PR |
| **Eval (manual/nightly)** | `uv run dharmiq-eval --dataset v1_fundamental_rights` | After corpus reindex; needs API key |

Nightly eval targets (not CI-blocking):

- faithfulness ≥ 0.85
- citation_precision (LLM judge) ≥ 0.95
- blockquote_met ≥ 0.80 on statutory questions
- refusal_correct ≥ 0.90 on refusal-tagged questions
