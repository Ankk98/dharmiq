from __future__ import annotations

from collections.abc import Callable

import pytest

from dharmiq.retrieval.reranker import RerankOutput


async def deterministic_rerank(
    query: str,
    documents: list[str],
    settings=None,
    *,
    top_n: int | None = None,
) -> RerankOutput:
    del query, settings
    limit = top_n or len(documents)
    indices = list(range(min(limit, len(documents))))
    scores = [max(0.95 - (0.05 * index), 0.5) for index in indices]
    return RerankOutput(indices=indices, scores=scores)


async def weak_rerank(
    query: str,
    documents: list[str],
    settings=None,
    *,
    top_n: int | None = None,
) -> RerankOutput:
    del query, settings
    limit = top_n or len(documents)
    indices = list(range(min(limit, len(documents))))
    return RerankOutput(indices=indices, scores=[0.1] * len(indices))


def mock_rerank(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., RerankOutput] | None = None,
) -> None:
    async def _wrapper(
        query: str,
        documents: list[str],
        settings=None,
        *,
        top_n: int | None = None,
    ) -> RerankOutput:
        fn = handler or deterministic_rerank
        return await fn(query, documents, settings, top_n=top_n)

    monkeypatch.setattr("dharmiq.retrieval.reranker.rerank", _wrapper)
