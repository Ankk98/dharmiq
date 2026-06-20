from __future__ import annotations

import json

import pytest

from dharmiq.config.settings import load_settings
from dharmiq.llm.litellm_service import LiteLLMService, resolve_litellm_model
from tests.litellm_helpers import _ModelResponse, mock_litellm_acompletion


def test_resolve_litellm_model_adds_openrouter_prefix() -> None:
    assert resolve_litellm_model("deepseek/deepseek-v4-pro") == "openrouter/deepseek/deepseek-v4-pro"
    assert (
        resolve_litellm_model("openrouter/deepseek/deepseek-v4-pro")
        == "openrouter/deepseek/deepseek-v4-pro"
    )


@pytest.mark.asyncio
async def test_litellm_service_complete_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    calls = mock_litellm_acompletion(monkeypatch, ["Hello"])

    service = LiteLLMService(settings)
    result = await service.acompletion(
        [{"role": "user", "content": "Hi"}],
        model=settings.llm.roles.primary,
    )

    assert calls[0]["model"] == settings.llm.roles.primary
    assert result["choices"][0]["message"]["content"] == "Hello"


@pytest.mark.asyncio
async def test_litellm_service_passes_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    calls = mock_litellm_acompletion(monkeypatch, [json.dumps({"ok": True})])

    service = LiteLLMService(settings)
    await service.acompletion(
        [{"role": "user", "content": "Validate this"}],
        model=settings.llm.agents.validator.model,
        reasoning_enabled=True,
    )

    assert calls[0]["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_litellm_service_rerank_local_backend() -> None:
    settings = load_settings()
    service = LiteLLMService(settings)

    documents = [
        "Unrelated consumer warranty policy",
        "Section 41 CrPC covers arrest without warrant",
        "Another unrelated document",
    ]
    ranked = await service.arerank("Section 41 CrPC arrest", documents, top_n=2)

    assert ranked == [1, 0]
    assert ranked[0] == 1


@pytest.mark.asyncio
async def test_litellm_service_rerank_litellm_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = load_settings()
    settings.llm.rerank.backend = "litellm"
    calls: list[dict[str, object]] = []

    async def _fake_arerank(**kwargs: object) -> _ModelResponse:
        calls.append(kwargs)
        return _ModelResponse({"results": [{"index": 2}, {"index": 0}]})

    monkeypatch.setattr("dharmiq.llm.litellm_service.arerank", _fake_arerank)

    service = LiteLLMService(settings)
    ranked = await service.arerank("query", ["a", "b", "c"], top_n=2)

    assert ranked == [2, 0]
    assert calls[0]["model"] == settings.llm.rerank.litellm_model


@pytest.mark.asyncio
async def test_agent_graph_flag_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_AGENT_GRAPH_V2", "true")
    settings = load_settings()
    assert settings.agent_graph.enabled is True
