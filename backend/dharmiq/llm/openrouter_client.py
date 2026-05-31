from __future__ import annotations

import asyncio
from typing import Any

import httpx

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.core.logging import get_logger

logger = get_logger(__name__)

_RETRYABLE_STATUS = {429, 502, 503, 504}


class OpenRouterClient:
    """Async HTTP client for OpenRouter chat and embedding APIs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        api_key = self._settings.openrouter.api_key.get_secret_value()
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.openrouter.base_url.rstrip("/"),
                headers=self._headers(),
                timeout=self._settings.openrouter.timeout_seconds,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()
        max_retries = self._settings.openrouter.max_retries
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await client.request(method, path, json=json)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "openrouter_timeout",
                    path=path,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "openrouter_http_error",
                    path=path,
                    attempt=attempt + 1,
                    error=str(exc),
                )
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = OpenRouterError(
                        f"OpenRouter returned {response.status_code}",
                        details={"body": response.text},
                    )
                    logger.warning(
                        "openrouter_retryable_status",
                        path=path,
                        status_code=response.status_code,
                        attempt=attempt + 1,
                    )
                else:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise OpenRouterError(
                            f"OpenRouter request failed: {response.status_code}",
                            details={"body": response.text},
                        ) from exc
                    return response.json()

            if attempt < max_retries:
                await asyncio.sleep(2**attempt)

        raise OpenRouterError(
            "OpenRouter request failed after retries",
            details={"path": path, "error": str(last_error)},
        ) from last_error

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model or self._settings.openrouter.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return await self._request("POST", "/chat/completions", json=payload)

    async def create_embeddings(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        payload = {
            "model": model or self._settings.embeddings.remote_model_id,
            "input": texts,
        }
        data = await self._request("POST", "/embeddings", json=payload)
        items = sorted(data["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]


_client: OpenRouterClient | None = None


def get_openrouter_client() -> OpenRouterClient:
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


async def close_openrouter_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
