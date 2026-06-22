# v0.5 — Flow coverage matrix

**Parent:** [`trd.md`](./trd.md) · [`prd.md`](./prd.md)  
**Last updated:** 2026-06-22

Every critical path must map to an automated test (mocked where noted) or a **manual** step in [`manual-test-runbook.md`](./manual-test-runbook.md).

| # | Critical path | Automated test | Manual only |
|---|---------------|----------------|-------------|
| 1 | Auth register + login | `tests/conftest.py` (`auth_headers`) | |
| 2 | Create chat session | `test_v02_e2e_smoke.py` | |
| 3 | Upload file → processing stages → ready | `tests/test_upload_pipeline.py`, smoke | |
| 4 | Attach upload to session | `test_v02_e2e_smoke.py` | |
| 5 | POST message → 202 + chat_request_id | `test_v02_e2e_smoke.py` | |
| 6 | SSE stream → done completed | `test_v02_e2e_smoke.py` | |
| 7 | Assistant message has citations + disclaimer | `test_v02_e2e_smoke.py` | |
| 8 | Citation → chunk list API | `tests/test_document_chunks.py` | |
| 9 | Export account JSON | `tests/test_account_privacy.py`, `test_v05_export_delete_smoke` | |
| 10 | Delete account (email+password) | `tests/test_account_privacy.py`, `test_v05_export_delete_smoke` | |
| 11 | Idempotency key replay | `tests/test_idempotency.py` (or v0.4) | |
| 12 | Cost cap refusal | unit tests (mocked) | |
| 13 | Feedback upsert | `tests/test_feedback.py` | |
| 14 | Corpus sync + index | | `verify_corpus_index.py` + manual |
| 15 | Live eval single dataset | | `dharmiq-eval` (advisory) |
| 16 | Live eval MVP suite + compare | | `dharmiq-eval --suite mvp --compare` |
| 17 | Docker compose full stack | | manual-test-runbook §4 |

**v0.5 smoke extension (P6):** rows 9–10 exercised in `test_v05_export_delete_smoke` (`test_v02_e2e_smoke.py`) using a disposable user (export then delete).
