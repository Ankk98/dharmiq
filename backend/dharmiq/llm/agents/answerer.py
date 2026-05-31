from __future__ import annotations

from dataclasses import dataclass

from dharmiq.llm.agents.base import call_text_agent
from dharmiq.llm.openrouter_client import OpenRouterClient
from dharmiq.llm.prompts.loader import load_prompt
from dharmiq.llm.retrieval import RetrievedChunk, format_retrieved_context


@dataclass(frozen=True)
class AnswererResult:
    answer: str
    tokens_used: int


async def run_answerer(
    client: OpenRouterClient,
    *,
    user_question: str,
    facts: str,
    retrieved_chunks: list[RetrievedChunk],
    regeneration_instructions: str | None = None,
) -> AnswererResult:
    prompt = load_prompt("answerer")
    regeneration_section = prompt.render_regeneration_section(regeneration_instructions)
    user_content = prompt.render_user(
        user_question=user_question,
        facts=facts,
        retrieved_context=format_retrieved_context(retrieved_chunks),
        regeneration_section=regeneration_section,
    )
    system = prompt.system.format(regeneration_section=regeneration_section)
    answer, tokens = await call_text_agent(
        client,
        system=system,
        user_content=user_content,
    )
    return AnswererResult(answer=answer.strip(), tokens_used=tokens)
