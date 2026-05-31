from __future__ import annotations

import json
import re
from typing import Any

from dharmiq.db.models.chats import ChatMessage, MessageRole
from dharmiq.llm.openrouter_client import OpenRouterClient, extract_assistant_content, extract_token_usage


def format_chat_history(messages: list[ChatMessage], *, limit: int = 20) -> str:
    """Format recent messages for agent prompts."""
    recent = messages[-limit:]
    lines: list[str] = []
    for message in recent:
        role = message.role.value
        lines.append(f"{role}: {message.content.strip()}")
    return "\n".join(lines) if lines else "(no prior messages)"


def extract_user_facts(messages: list[ChatMessage]) -> str:
    """Collect user messages and clarifier follow-ups into a fact pattern."""
    parts: list[str] = []
    for message in messages:
        if message.role == MessageRole.USER:
            parts.append(message.content.strip())
        elif message.role == MessageRole.CLARIFIER:
            parts.append(f"[Clarifier asked]: {message.content.strip()}")
    return "\n".join(parts) if parts else "(none)"


def parse_json_response(content: str) -> dict[str, Any]:
    """Parse JSON from an LLM response, tolerating fenced code blocks."""
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return json.loads(stripped)


async def call_json_agent(
    client: OpenRouterClient,
    *,
    system: str,
    user_content: str,
    model: str | None = None,
) -> tuple[dict[str, Any], int]:
    response = await client.chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = extract_assistant_content(response)
    tokens = extract_token_usage(response)
    return parse_json_response(content), tokens


async def call_text_agent(
    client: OpenRouterClient,
    *,
    system: str,
    user_content: str,
    model: str | None = None,
    temperature: float = 0.2,
) -> tuple[str, int]:
    response = await client.chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        model=model,
        temperature=temperature,
    )
    return extract_assistant_content(response), extract_token_usage(response)
