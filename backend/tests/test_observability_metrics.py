from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from dharmiq.eval.judge import run_llm_judge
from dharmiq.llm.openrouter_client import OpenRouterClient
from dharmiq.observability.metrics import (
    get_ingestion_metrics,
    record_eval_run,
    record_http_request,
    record_ingestion_failure,
    record_ingestion_success,
    record_llm_tokens,
    reset_ingestion_metrics,
)
from tests.litellm_helpers import chat_response_dict, mock_litellm_acompletion


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_ingestion_metrics()
    yield
    reset_ingestion_metrics()


def test_ingestion_metrics_snapshot() -> None:
    record_ingestion_success(chunk_count=3, page_count=10)
    record_ingestion_failure(reason="parse error")
    snapshot = get_ingestion_metrics()
    assert snapshot["documents_processed"] == 1
    assert snapshot["documents_failed"] == 1
    assert snapshot["chunks_indexed"] == 3
    assert snapshot["pages_processed"] == 10
    assert snapshot["last_failure_reason"] == "parse error"


def test_record_http_and_llm_metrics() -> None:
    record_http_request(method="GET", path="/api/health", status_code=200, duration_seconds=0.05)
    record_http_request(method="POST", path="/api/chat", status_code=500, duration_seconds=1.2)
    record_llm_tokens(model="test-model", agent="answerer", tokens=150)
    record_eval_run(
        dataset="v1_fundamental_rights",
        question_count=8,
        metrics={"faithfulness": 0.8, "llm_answer_correctness": 0.75},
    )


async def test_llm_judge_parses_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "answer_correctness": 0.85,
        "citation_correctness": 0.7,
        "reason": "Covers Article 22 adequately.",
    }
    mock_litellm_acompletion(
        monkeypatch,
        [chat_response_dict(json.dumps(payload), total_tokens=42)],
    )

    client = OpenRouterClient()
    scores, tokens = await run_llm_judge(
        client,
        question="What are my arrest rights?",
        generated_answer="Article 22 protects you.",
        reference_answer="Article 22 protects against arbitrary arrest.",
        expected_citations=[{"section": "Article 22"}],
    )

    assert scores.answer_correctness == 0.85
    assert scores.citation_correctness == 0.7
    assert tokens == 42


async def test_metrics_endpoint(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "dharmiq_http_requests_total" in response.text
