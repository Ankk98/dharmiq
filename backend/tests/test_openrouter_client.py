from __future__ import annotations

import pytest

from dharmiq.llm.openrouter_client import OpenRouterClient
from tests.litellm_helpers import mock_litellm_aembedding, mock_litellm_acompletion


@pytest.mark.asyncio
async def test_chat_completion_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_litellm_acompletion(monkeypatch, ["Hello"])

    client = OpenRouterClient()
    result = await client.chat_completion([{"role": "user", "content": "Hi"}])

    assert result["choices"][0]["message"]["content"] == "Hello"


@pytest.mark.asyncio
async def test_create_embeddings_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_litellm_aembedding(monkeypatch, [[0.1, 0.2], [0.3, 0.4]])

    client = OpenRouterClient()
    vectors = await client.create_embeddings(["a", "b"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.asyncio
async def test_acompletion_passes_retry_config(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = mock_litellm_acompletion(monkeypatch, ["Hello"])

    client = OpenRouterClient()
    await client.chat_completion([{"role": "user", "content": "Hi"}])

    assert calls[0]["num_retries"] == client._settings.openrouter.max_retries
