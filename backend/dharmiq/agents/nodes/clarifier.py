from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
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

    return {
        "topic": clarifier.topic,
        "needs_clarification": clarifier.needs_more_info and bool(clarifier.followup_questions),
        "followup_questions": clarifier.followup_questions,
        "followup_items": [
            {
                "question": item.question,
                "why": item.why,
                "options": item.options,
            }
            for item in clarifier.followup_items
        ],
        "clarifier_reason": clarifier.reason,
        "total_tokens": state.get("total_tokens", 0) + clarifier.tokens_used,
    }
