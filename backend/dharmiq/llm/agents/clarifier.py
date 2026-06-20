from __future__ import annotations

from dataclasses import dataclass

from dharmiq.db.models.chats import ChatMessage
from dharmiq.llm.agents.base import call_json_agent, format_chat_history
from dharmiq.llm.openrouter_client import OpenRouterClient
from dharmiq.llm.prompts.loader import load_prompt


@dataclass(frozen=True)
class ClarifierResult:
    topic: str
    needs_more_info: bool
    followup_questions: list[str]
    reason: str
    tokens_used: int


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

    followups = data.get("followup_questions") or []
    if not isinstance(followups, list):
        followups = []

    return ClarifierResult(
        topic=str(data.get("topic") or "general"),
        needs_more_info=bool(data.get("needs_more_info")),
        followup_questions=[str(item).strip() for item in followups if str(item).strip()],
        reason=str(data.get("reason") or ""),
        tokens_used=tokens,
    )
