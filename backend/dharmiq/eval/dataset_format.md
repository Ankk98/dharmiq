# Eval dataset format

Dharmiq evaluation datasets are stored as **JSONL** files (one JSON object per line) under
`data/eval/datasets/` (configurable via `eval.datasets_dir` in `config/*.yaml`).

## File naming

Use a descriptive slug, e.g. `v1_fundamental_rights.jsonl`. The filename stem (without
extension) is used as the dataset name when importing into the database.

## Record schema

Each line must be a JSON object with these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Stable question identifier within the dataset (e.g. `q1`) |
| `question` | string | yes | User question to send through the RAG pipeline |
| `expected_answer` | string | yes | Reference answer for correctness metrics |
| `expected_citations` | array | no | Expected citation hints (section labels, document IDs) |
| `topic` | string | no | Hint for query rewriter (defaults to `general`) |
| `facts` | string | no | Pre-supplied fact pattern (skips clarifier in eval runs) |
| `min_citation_count` | integer | no | Minimum `[n]` citation markers expected in the generated answer |
| `expect_blockquote` | boolean | no | Whether a Markdown blockquote (`> …`) is required |
| `expect_refusal` | boolean | no | Whether the pipeline should refuse (insufficient sources) |
| `required_source_ids` | string[] | no | Allowlist `source_id` values that should be indexed before eval (preflight warning) |
| `must_not_cite_sections` | string[] | no | Section labels that must **not** appear in the answer (revised-law checks; see `v1_revised_law`) |
| `source_type` | string | no | Corpus source kind (default `statute`) |
| `locale` | string | no | Question locale (default `en`) |

### `expected_citations` entries

Each citation object may include:

```json
{"document_id": "uuid-or-source-id", "section": "Article 22"}
```

Only `section` is required for the LLM citation judge; `document_id` is optional when the
corpus is not yet indexed.

## Example

```json
{
  "id": "q1",
  "question": "What are my rights if police arrest me without a warrant?",
  "expected_answer": "Article 22 of the Constitution protects against arbitrary arrest and detention. An arrested person must be informed of grounds, allowed to consult a lawyer, and produced before a magistrate within 24 hours.",
  "expected_citations": [
    {"section": "Article 22"}
  ],
  "topic": "police_arrest",
  "facts": "I was arrested without a warrant."
}
```

## Validation

Lint a committed dataset before review or eval:

```bash
cd backend
uv run python -m dharmiq.eval.tools.validate_dataset --dataset v1_fundamental_rights
```

Checks include unique `id` values, required fields, citation sections on statutory rows,
and gating minimum row counts for MVP datasets.

## Running evals

```bash
cd backend
uv run dharmiq-eval --dataset v1_fundamental_rights
```

Results are written to `eval_runs` / `eval_results` tables and a JSON summary under
`data/eval/runs/`.
