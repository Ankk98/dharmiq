from __future__ import annotations

from typing import Any

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.llm.litellm_service import LiteLLMService, get_litellm_service


class OpenRouterClient:
    """Backward-compatible adapter over LiteLLM for chat and remote embeddings."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        litellm_service: LiteLLMService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._litellm = litellm_service or get_litellm_service()

    async def close(self) -> None:
        return None

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        resolved_model = model or self._settings.openrouter.default_model
        return await self._litellm.acompletion(
            messages,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    async def create_embeddings(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        return await self._litellm.aembedding(
            texts,
            model=model or self._settings.embeddings.remote_model_id,
        )


_client: OpenRouterClient | None = None


def get_openrouter_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


async def close_openrouter_client() -> None:
    global _client
    _client = None


def extract_assistant_content(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise OpenRouterError("OpenRouter response missing choices", details={"response": response})
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        raise OpenRouterError("OpenRouter response missing assistant content", details={"response": response})
    return str(content)


def extract_token_usage(response: dict[str, Any]) -> int:
    usage = response.get("usage") or {}
    total = usage.get("total_tokens")
    if isinstance(total, int):
        return total
    prompt = usage.get("prompt_tokens") or 0
    completion = usage.get("completion_tokens") or 0
    if isinstance(prompt, int) and isinstance(completion, int):
        return prompt + completion
    return 0
