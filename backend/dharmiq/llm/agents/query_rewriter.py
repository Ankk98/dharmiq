from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dharmiq.llm.agents.base import call_json_agent
from dharmiq.llm.openrouter_client import OpenRouterClient, extract_token_usage
from dharmiq.llm.prompts.loader import load_prompt


@dataclass(frozen=True)
class QueryRewriterResult:
    queries: list[str]
    tokens_used: int
    llm_response: dict[str, Any]


async def run_query_rewriter(
    client: OpenRouterClient,
    *,
    user_question: str,
    topic: str,
    facts: str,
) -> QueryRewriterResult:
    prompt = load_prompt("query_rewriter")
    user_content = prompt.render_user(
        user_question=user_question,
        topic=topic,
        facts=facts,
    )
    data, response = await call_json_agent(
        client,
        system=prompt.system,
        user_content=user_content,
    )

    queries = data.get("queries") or [user_question]
    if not isinstance(queries, list):
        queries = [user_question]

    cleaned = [str(item).strip() for item in queries if str(item).strip()]
    if not cleaned:
        cleaned = [user_question]

    return QueryRewriterResult(
        queries=cleaned[:4],
        tokens_used=extract_token_usage(response),
        llm_response=response,
    )
