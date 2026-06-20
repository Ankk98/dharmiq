from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from litellm import arerank

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.core.logging import get_logger

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

logger = get_logger(__name__)

_cross_encoder: CrossEncoder | None = None
_cross_encoder_model: str | None = None


@dataclass(frozen=True)
class RerankOutput:
    indices: list[int]
    scores: list[float]


def reset_reranker_cache() -> None:
    global _cross_encoder, _cross_encoder_model
    _cross_encoder = None
    _cross_encoder_model = None


def _get_cross_encoder(model_name: str) -> CrossEncoder:
    global _cross_encoder, _cross_encoder_model
    if _cross_encoder is None or _cross_encoder_model != model_name:
        from sentence_transformers import CrossEncoder

        _cross_encoder = CrossEncoder(model_name)
        _cross_encoder_model = model_name
    return _cross_encoder


def _local_cross_encoder_scores(
    query: str,
    documents: list[str],
    model_name: str,
) -> list[float]:
    if not documents:
        return []
    encoder = _get_cross_encoder(model_name)
    pairs = [[query, document] for document in documents]
    raw_scores = encoder.predict(pairs)
    return [float(score) for score in raw_scores]


async def _litellm_rerank(
    query: str,
    documents: list[str],
    *,
    model: str,
    top_n: int,
    api_key: str | None,
) -> RerankOutput:
    try:
        response = await arerank(
            model=model,
            query=query,
            documents=documents,
            top_n=top_n,
            api_key=api_key,
        )
    except Exception as exc:
        logger.warning("litellm_arerank_failed", model=model, error=str(exc))
        raise OpenRouterError(
            "LiteLLM rerank failed",
            details={"model": model, "error": str(exc)},
        ) from exc

    payload: dict[str, Any]
    if isinstance(response, dict):
        payload = response
    elif hasattr(response, "model_dump"):
        payload = response.model_dump()
    else:
        raise OpenRouterError(
            "Unexpected LiteLLM rerank response type",
            details={"type": type(response).__name__},
        )

    results = payload.get("results") or []
    indices = [int(item["index"]) for item in results]
    scores = [float(item.get("relevance_score", 0.0)) for item in results]
    return RerankOutput(indices=indices, scores=scores)


async def rerank(
    query: str,
    documents: list[str],
    settings: Settings | None = None,
    *,
    top_n: int | None = None,
) -> RerankOutput:
    if not documents:
        return RerankOutput(indices=[], scores=[])

    cfg = settings or get_settings()
    limit = top_n or len(documents)
    rerank_cfg = cfg.llm.rerank

    if rerank_cfg.backend == "local":
        scores = _local_cross_encoder_scores(query, documents, rerank_cfg.local_model)
        ranked = sorted(range(len(documents)), key=lambda idx: scores[idx], reverse=True)
        selected = ranked[:limit]
        return RerankOutput(
            indices=selected,
            scores=[scores[idx] for idx in selected],
        )

    import os

    api_key = os.environ.get(rerank_cfg.api_key_env)
    return await _litellm_rerank(
        query,
        documents,
        model=rerank_cfg.litellm_model,
        top_n=limit,
        api_key=api_key,
    )
