from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dharmiq.core.errors import ClarifierStructureError
from dharmiq.db.models.chats import ChatMessage
from dharmiq.llm.agents.base import call_json_agent, format_chat_history
from dharmiq.llm.openrouter_client import OpenRouterClient, extract_token_usage
from dharmiq.llm.prompts.loader import load_prompt


@dataclass(frozen=True)
class ClarifierFollowupItem:
    question: str
    options: list[str]
    why: str | None = None


@dataclass(frozen=True)
class ClarifierResult:
    topic: str
    needs_more_info: bool
    followup_questions: list[str]
    followup_items: list[ClarifierFollowupItem]
    reason: str
    tokens_used: int
    llm_response: dict[str, Any]


def _parse_followup_items(data: dict) -> list[ClarifierFollowupItem]:
    raw_items = data.get("followup_items")
    if not isinstance(raw_items, list) or not raw_items:
        return []

    items: list[ClarifierFollowupItem] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        question = str(entry.get("question") or "").strip()
        if not question:
            continue
        raw_options = entry.get("options") or []
        options: list[str] = []
        if isinstance(raw_options, list):
            options = [str(option).strip() for option in raw_options if str(option).strip()]
        why_raw = entry.get("why")
        why = str(why_raw).strip() if why_raw else None
        items.append(
            ClarifierFollowupItem(
                question=question,
                options=options,
                why=why or None,
            )
        )
    return items


async def _call_clarifier_once(
    client: OpenRouterClient,
    *,
    user_question: str,
    history: list[ChatMessage],
    history_limit: int,
    attached_documents: str,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    prompt = load_prompt("clarifier")
    user_content = prompt.render_user(
        user_question=user_question,
        history=format_chat_history(history, limit=history_limit),
        attached_documents=attached_documents,
    )
    data, response = await call_json_agent(
        client,
        system=prompt.system,
        user_content=user_content,
    )
    return data, response, extract_token_usage(response)


async def run_clarifier(
    client: OpenRouterClient,
    *,
    user_question: str,
    history: list[ChatMessage],
    history_limit: int = 20,
    attached_documents: str = "None",
) -> ClarifierResult:
    data, response, tokens_used = await _call_clarifier_once(
        client,
        user_question=user_question,
        history=history,
        history_limit=history_limit,
        attached_documents=attached_documents,
    )

    followup_items = _parse_followup_items(data)
    needs_more_info = bool(data.get("needs_more_info"))

    if needs_more_info and not followup_items:
        retry_data, retry_response, retry_tokens = await _call_clarifier_once(
            client,
            user_question=user_question,
            history=history,
            history_limit=history_limit,
            attached_documents=attached_documents,
        )
        data = retry_data
        response = retry_response
        tokens_used += retry_tokens
        followup_items = _parse_followup_items(data)
        needs_more_info = bool(data.get("needs_more_info"))

    if needs_more_info and not followup_items:
        raise ClarifierStructureError(
            "Clarifier returned needs_more_info without structured followup_items"
        )

    followup_questions = [item.question for item in followup_items]

    return ClarifierResult(
        topic=str(data.get("topic") or "general"),
        needs_more_info=needs_more_info,
        followup_questions=followup_questions,
        followup_items=followup_items,
        reason=str(data.get("reason") or ""),
        tokens_used=tokens_used,
        llm_response=response,
    )
