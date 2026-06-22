from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.agents.text_utils import normalize_for_comparison
from dharmiq.db.models.chats import MessageRole
from dharmiq.llm.agents.clarifier import run_clarifier
from dharmiq.llm.usage import record_llm_usage
from dharmiq.observability.metrics import record_llm_tokens
from dharmiq.uploads.session_attachments import list_attached_uploads


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


def _format_attached_documents(attached) -> str:
    if not attached:
        return "None"
    lines = [
        (
            f"- {item.original_filename} ({item.mime_type}, indexed={item.indexed}, "
            f"attached_at={item.attached_at.isoformat()})"
        )
        for item in attached
    ]
    return "\n".join(lines)


async def list_attached_uploads_for_session(runtime: GraphRuntime) -> str:
    """Clarifier tool: metadata for uploads explicitly attached to this chat session."""
    attached = await list_attached_uploads(
        runtime.db,
        runtime.chat_session.id,
        as_of=runtime.chat_request.started_at,
    )
    return _format_attached_documents(attached)


def _prior_clarifier_questions(history: list) -> set[str]:
    questions: set[str] = set()
    for message in history:
        if message.role != MessageRole.CLARIFIER:
            continue
        metadata = message.message_metadata or {}
        raw_items = metadata.get("followup_items")
        if isinstance(raw_items, list):
            for entry in raw_items:
                if isinstance(entry, dict):
                    question = str(entry.get("question") or "").strip()
                    if question:
                        questions.add(normalize_for_comparison(question))
    return questions


def _duplicate_clarifier_questions(
    followup_items: list[dict[str, Any]],
    history: list,
) -> bool:
    prior_questions = _prior_clarifier_questions(history)
    if not prior_questions:
        return False
    current_questions = {
        normalize_for_comparison(str(item.get("question") or ""))
        for item in followup_items
        if str(item.get("question") or "").strip()
    }
    return bool(current_questions) and current_questions.issubset(prior_questions)


async def clarifier_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    cfg = runtime.settings

    attached_documents = await list_attached_uploads_for_session(runtime)

    clarifier = await run_clarifier(
        runtime.client,
        user_question=state["user_message"],
        history=runtime.history[:-1],
        history_limit=cfg.chat.history_limit,
        attached_documents=attached_documents,
    )
    await record_llm_usage(
        runtime.db,
        user_id=runtime.user.id,
        chat_request_id=runtime.chat_request.id,
        session_id=runtime.chat_session.id,
        agent_role="clarifier",
        model=runtime.model_name,
        response=clarifier.llm_response,
    )
    record_llm_tokens(
        model=runtime.model_name,
        agent="clarifier",
        tokens=clarifier.tokens_used,
    )

    followup_items = [
        {
            "question": item.question,
            "why": item.why,
            "options": item.options,
        }
        for item in clarifier.followup_items
    ]

    needs_clarification = clarifier.needs_more_info and bool(followup_items)
    force_answer = bool(state.get("force_answer"))

    if needs_clarification and _duplicate_clarifier_questions(followup_items, runtime.history[:-1]):
        needs_clarification = False
        force_answer = True

    return {
        "topic": clarifier.topic,
        "needs_clarification": needs_clarification,
        "followup_questions": clarifier.followup_questions,
        "followup_items": followup_items,
        "clarifier_reason": clarifier.reason,
        "force_answer": force_answer,
        "total_tokens": state.get("total_tokens", 0) + clarifier.tokens_used,
    }
