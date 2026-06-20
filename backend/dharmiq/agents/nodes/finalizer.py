from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState, chunks_from_state
from dharmiq.db.models.chats import ChatMessage, ChatRequestStatus, MessageRole
from dharmiq.llm.retrieval import chunks_to_citations


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def finalizer_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    retrieved = chunks_from_state(state.get("merged_chunks", []))
    citations = chunks_to_citations(retrieved)

    answer_text = state.get("final_answer") or state.get("draft_answer", "")
    final_warning = state.get("final_warning")
    verdict = state.get("validator_verdict") or {}
    max_retries = runtime.settings.chat.max_validator_retries
    agent_name = "refusal" if state.get("weak_retrieval") else "answerer"

    if verdict.get("must_regenerate") and state.get("regeneration_count", 0) >= max_retries:
        final_warning = (
            verdict.get("final_warning")
            or "This answer may still contain issues. Please consult a qualified lawyer."
        )

    if final_warning and final_warning not in answer_text:
        answer_text = f"{answer_text.rstrip()}\n\n> {final_warning}"

    assistant_msg = ChatMessage(
        session_id=runtime.chat_session.id,
        user_id=runtime.user.id,
        role=MessageRole.ASSISTANT,
        content=answer_text,
        message_metadata={
            "agent": agent_name,
            "topic": state.get("topic"),
            "citations": [citation.model_dump(mode="json") for citation in citations],
            "chat_request_id": str(runtime.chat_request_id),
        },
    )
    runtime.db.add(assistant_msg)
    runtime.new_messages.append(assistant_msg)

    runtime.chat_request.status = ChatRequestStatus.COMPLETED
    runtime.chat_request.total_tokens = state.get("total_tokens", 0)
    runtime.chat_request.finished_at = runtime.utcnow()
    await runtime.db.flush()

    return {
        "final_answer": answer_text,
        "final_warning": final_warning,
        "citations": [citation.model_dump(mode="json") for citation in citations],
    }
