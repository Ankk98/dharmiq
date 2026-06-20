from __future__ import annotations

import pytest

from dharmiq.config.settings import load_settings
from dharmiq.retrieval.reranker import RerankOutput, rerank, reset_reranker_cache


@pytest.fixture(autouse=True)
def _reset_reranker() -> None:
    reset_reranker_cache()
    yield
    reset_reranker_cache()


@pytest.mark.asyncio
async def test_local_reranker_reorders(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    settings.llm.rerank.backend = "local"

    def _fake_scores(query: str, documents: list[str], model_name: str) -> list[float]:
        del query, model_name
        return [0.1, 0.95, 0.2]

    monkeypatch.setattr(
        "dharmiq.retrieval.reranker._local_cross_encoder_scores",
        _fake_scores,
    )

    documents = [
        "Unrelated consumer warranty policy",
        "Section 41 CrPC covers arrest without warrant",
        "Another unrelated document",
    ]
    output = await rerank("Section 41 CrPC arrest", documents, settings, top_n=3)

    assert output.indices[0] == 1
    assert output.scores[0] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_litellm_reranker_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    settings.llm.rerank.backend = "litellm"
    calls: list[dict[str, object]] = []

    async def _fake_arerank(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "results": [
                {"index": 2, "relevance_score": 0.91},
                {"index": 0, "relevance_score": 0.55},
            ]
        }

    monkeypatch.setattr("dharmiq.retrieval.reranker.arerank", _fake_arerank)

    output = await rerank("query", ["a", "b", "c"], settings, top_n=2)

    assert output == RerankOutput(indices=[2, 0], scores=[0.91, 0.55])
    assert calls[0]["model"] == settings.llm.rerank.litellm_model
    assert calls[0]["top_n"] == 2
