from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest


def chat_response_dict(content: str, *, total_tokens: int = 10) -> dict[str, Any]:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"total_tokens": total_tokens},
    }


def embedding_response_dict(vectors: list[list[float]]) -> dict[str, Any]:
    return {
        "data": [
            {"index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
    }


class _ModelResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self, **_kwargs: Any) -> dict[str, Any]:
        return self._payload


def mock_litellm_acompletion(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[str | dict[str, Any] | Exception],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    index = {"value": 0}

    async def _fake_acompletion(**kwargs: Any) -> _ModelResponse:
        calls.append(kwargs)
        if index["value"] >= len(responses):
            raise RuntimeError("No more mocked LiteLLM chat responses configured")
        item = responses[index["value"]]
        index["value"] += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return _ModelResponse(chat_response_dict(item))
        return _ModelResponse(item)

    monkeypatch.setattr("dharmiq.llm.litellm_service.acompletion", _fake_acompletion)
    return calls


def mock_litellm_aembedding(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., Any] | list[list[float]],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def _fake_aembedding(**kwargs: Any) -> _ModelResponse:
        calls.append(kwargs)
        if callable(handler):
            vectors = handler(**kwargs)
        else:
            vectors = handler
        return _ModelResponse(embedding_response_dict(vectors))

    monkeypatch.setattr("dharmiq.llm.litellm_service.aembedding", _fake_aembedding)
    return calls
