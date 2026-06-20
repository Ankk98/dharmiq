from __future__ import annotations

import os
import re
from typing import Any

from litellm import acompletion, aembedding, arerank

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.core.logging import get_logger

logger = get_logger(__name__)


def resolve_litellm_model(model: str) -> str:
    """Normalize provider-prefixed LiteLLM model strings."""
    if model.startswith(("openrouter/", "cohere/", "together_ai/")):
        return model
    if "/" in model:
        return f"openrouter/{model}"
    return model


def _response_to_dict(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return response.model_dump()
    raise OpenRouterError("Unexpected LiteLLM response type", details={"type": type(response).__name__})


def _local_rerank_scores(query: str, documents: list[str]) -> list[float]:
    """Lightweight lexical reranker used when rerank.backend=local (P5 adds CrossEncoder)."""
    query_terms = {term for term in re.findall(r"[a-z0-9]+", query.lower()) if term}
    scores: list[float] = []
    for document in documents:
        doc_terms = {term for term in re.findall(r"[a-z0-9]+", document.lower()) if term}
        if not query_terms:
            scores.append(0.0)
            continue
        overlap = len(query_terms & doc_terms)
        scores.append(overlap / len(query_terms))
    return scores


class LiteLLMService:
    """Unified LiteLLM gateway for chat, remote embeddings, and reranking."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._configure_provider_env()

    def _configure_provider_env(self) -> None:
        api_key = self._settings.openrouter.api_key.get_secret_value()
        if api_key:
            os.environ.setdefault("OPENROUTER_API_KEY", api_key)

    def _completion_kwargs(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, str] | None,
        reasoning_enabled: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": resolve_litellm_model(model),
            "messages": messages,
            "temperature": temperature,
            "timeout": self._settings.openrouter.timeout_seconds,
            "num_retries": self._settings.openrouter.max_retries,
            "api_base": self._settings.openrouter.base_url,
        }
        api_key = self._settings.openrouter.api_key.get_secret_value()
        if api_key:
            kwargs["api_key"] = api_key
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        if reasoning_enabled:
            kwargs["reasoning_effort"] = "high"
        return kwargs

    async def acompletion(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: dict[str, str] | None = None,
        reasoning_enabled: bool = False,
    ) -> dict[str, Any]:
        resolved_model = model or self._settings.llm.roles.primary
        kwargs = self._completion_kwargs(
            model=resolved_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            reasoning_enabled=reasoning_enabled,
        )
        try:
            response = await acompletion(**kwargs)
        except Exception as exc:
            logger.warning("litellm_acompletion_failed", model=resolved_model, error=str(exc))
            raise OpenRouterError(
                "LiteLLM chat completion failed",
                details={"model": resolved_model, "error": str(exc)},
            ) from exc
        return _response_to_dict(response)

    async def aembedding(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        resolved_model = resolve_litellm_model(
            model or self._settings.embeddings.remote_model_id,
        )
        try:
            response = await aembedding(
                model=resolved_model,
                input=texts,
                timeout=self._settings.openrouter.timeout_seconds,
                num_retries=self._settings.openrouter.max_retries,
                api_base=self._settings.openrouter.base_url,
                api_key=self._settings.openrouter.api_key.get_secret_value() or None,
            )
        except Exception as exc:
            logger.warning("litellm_aembedding_failed", model=resolved_model, error=str(exc))
            raise OpenRouterError(
                "LiteLLM embedding failed",
                details={"model": resolved_model, "error": str(exc)},
            ) from exc

        data = _response_to_dict(response).get("data") or []
        items = sorted(data, key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in items]

    async def arerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
    ) -> list[int]:
        if not documents:
            return []

        limit = top_n or len(documents)
        rerank_cfg = self._settings.llm.rerank

        if rerank_cfg.backend == "local":
            scores = _local_rerank_scores(query, documents)
            ranked = sorted(range(len(documents)), key=lambda idx: scores[idx], reverse=True)
            return ranked[:limit]

        api_key = os.environ.get(rerank_cfg.api_key_env)
        try:
            response = await arerank(
                model=rerank_cfg.litellm_model,
                query=query,
                documents=documents,
                top_n=limit,
                api_key=api_key,
            )
        except Exception as exc:
            logger.warning(
                "litellm_arerank_failed",
                model=rerank_cfg.litellm_model,
                error=str(exc),
            )
            raise OpenRouterError(
                "LiteLLM rerank failed",
                details={"model": rerank_cfg.litellm_model, "error": str(exc)},
            ) from exc

        payload = _response_to_dict(response)
        results = payload.get("results") or []
        return [int(item["index"]) for item in results]


_service: LiteLLMService | None = None


def get_litellm_service() -> LiteLLMService:
    global _service
    if _service is None:
        _service = LiteLLMService()
    return _service


def reset_litellm_service() -> None:
    global _service
    _service = None
