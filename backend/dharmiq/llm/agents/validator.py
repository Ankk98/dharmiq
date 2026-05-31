from __future__ import annotations

from dataclasses import dataclass

from dharmiq.llm.agents.base import call_json_agent
from dharmiq.llm.openrouter_client import OpenRouterClient
from dharmiq.llm.prompts.loader import load_prompt
from dharmiq.llm.retrieval import RetrievedChunk, format_retrieved_context


@dataclass(frozen=True)
class ValidatorResult:
    must_regenerate: bool
    issues: list[str]
    regeneration_instructions: str
    final_warning: str
    tokens_used: int


async def run_validator(
    client: OpenRouterClient,
    *,
    user_question: str,
    retrieved_chunks: list[RetrievedChunk],
    draft_answer: str,
) -> ValidatorResult:
    prompt = load_prompt("validator")
    user_content = prompt.render_user(
        user_question=user_question,
        retrieved_context=format_retrieved_context(retrieved_chunks),
        draft_answer=draft_answer,
    )
    data, tokens = await call_json_agent(
        client,
        system=prompt.system,
        user_content=user_content,
    )

    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = []

    return ValidatorResult(
        must_regenerate=bool(data.get("must_regenerate")),
        issues=[str(item).strip() for item in issues if str(item).strip()],
        regeneration_instructions=str(data.get("regeneration_instructions") or "").strip(),
        final_warning=str(data.get("final_warning") or "").strip(),
        tokens_used=tokens,
    )
