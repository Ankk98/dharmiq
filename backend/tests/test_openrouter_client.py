from __future__ import annotations

import pytest
import respx
from httpx import Response

from dharmiq.llm.openrouter_client import OpenRouterClient


@pytest.mark.asyncio
@respx.mock
async def test_chat_completion_success() -> None:
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "Hello"}}],
            },
        )
    )

    client = OpenRouterClient()
    try:
        result = await client.chat_completion([{"role": "user", "content": "Hi"}])
    finally:
        await client.close()

    assert route.called
    assert result["choices"][0]["message"]["content"] == "Hello"


@pytest.mark.asyncio
@respx.mock
async def test_create_embeddings_success() -> None:
    route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1, 0.2]},
                    {"index": 1, "embedding": [0.3, 0.4]},
                ],
            },
        )
    )

    client = OpenRouterClient()
    try:
        vectors = await client.create_embeddings(["a", "b"])
    finally:
        await client.close()

    assert route.called
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.asyncio
@respx.mock
async def test_request_retries_on_503() -> None:
    route = respx.post("https://openrouter.ai/api/v1/embeddings").mock(
        side_effect=[
            Response(503, json={"error": "unavailable"}),
            Response(
                200,
                json={"data": [{"index": 0, "embedding": [0.5]}]},
            ),
        ]
    )

    client = OpenRouterClient()
    try:
        vectors = await client.create_embeddings(["retry me"])
    finally:
        await client.close()

    assert route.call_count == 2
    assert vectors == [[0.5]]
