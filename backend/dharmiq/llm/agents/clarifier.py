from __future__ import annotations

from dataclasses import dataclass

from dharmiq.db.models.chats import ChatMessage
from dharmiq.llm.agents.base import call_json_agent, format_chat_history
from dharmiq.llm.openrouter_client import OpenRouterClient
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


def _split_question_and_why(text: str) -> tuple[str, str | None]:
    for separator in (" — ", " – ", " - "):
        if separator in text:
            question, why = text.split(separator, 1)
            question = question.strip()
            why = why.strip() or None
            if question:
                return question, why
    return text.strip(), None


def _parse_followup_items(data: dict) -> list[ClarifierFollowupItem]:
    raw_items = data.get("followup_items")
    if isinstance(raw_items, list) and raw_items:
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
        if items:
            return items

    followups = data.get("followup_questions") or []
    if not isinstance(followups, list):
        followups = []
    items = []
    for raw in followups:
        text = str(raw).strip()
        if not text:
            continue
        question, why = _split_question_and_why(text)
        items.append(ClarifierFollowupItem(question=question, options=[], why=why))
    return items


async def run_clarifier(
    client: OpenRouterClient,
    *,
    user_question: str,
    history: list[ChatMessage],
    history_limit: int = 20,
    attached_documents: str = "None",
) -> ClarifierResult:
    prompt = load_prompt("clarifier")
    user_content = prompt.render_user(
        user_question=user_question,
        history=format_chat_history(history, limit=history_limit),
        attached_documents=attached_documents,
    )
    data, tokens = await call_json_agent(
        client,
        system=prompt.system,
        user_content=user_content,
    )

    followup_items = _parse_followup_items(data)
    followup_questions = [item.question for item in followup_items]

    return ClarifierResult(
        topic=str(data.get("topic") or "general"),
        needs_more_info=bool(data.get("needs_more_info")),
        followup_questions=followup_questions,
        followup_items=followup_items,
        reason=str(data.get("reason") or ""),
        tokens_used=tokens,
    )
