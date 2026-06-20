from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.citation_validation import citations_from_state
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.db.models.chats import ChatMessage, ChatRequestStatus, MessageRole


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


VALIDATION_FAILED_MESSAGE = (
    "I could not verify this answer against the retrieved sources after multiple review passes. "
    "Please rephrase your question, attach relevant documents, or consult a qualified lawyer."
)


async def finalizer_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    citations = citations_from_state(state.get("citations") or state.get("citation_map"))
    verdict = state.get("validator_verdict") or {}
    validation_blocked = bool(state.get("validation_blocked"))

    if validation_blocked:
        answer_text = VALIDATION_FAILED_MESSAGE
        if runtime.emitter is not None:
            await runtime.emitter.emit_error(
                code="VALIDATION_FAILED",
                message=VALIDATION_FAILED_MESSAGE,
            )
    elif state.get("weak_retrieval"):
        answer_text = state.get("final_answer") or state.get("draft_answer", "")
    else:
        answer_text = state.get("final_answer") or state.get("draft_answer", "")

    final_warning = state.get("final_warning")
    agent_name = "refusal" if state.get("weak_retrieval") else "answerer"
    if validation_blocked:
        agent_name = "validator"

    if (
        not validation_blocked
        and verdict.get("must_regenerate")
        and final_warning
        and final_warning not in answer_text
    ):
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
            "validation_blocked": validation_blocked,
        },
    )
    runtime.db.add(assistant_msg)
    runtime.new_messages.append(assistant_msg)

    runtime.chat_request.status = (
        ChatRequestStatus.FAILED if validation_blocked else ChatRequestStatus.COMPLETED
    )
    runtime.chat_request.total_tokens = state.get("total_tokens", 0)
    runtime.chat_request.finished_at = runtime.utcnow()
    await runtime.db.flush()

    return {
        "final_answer": answer_text,
        "final_warning": final_warning,
        "citations": [citation.model_dump(mode="json") for citation in citations],
        "validation_blocked": validation_blocked,
    }
