from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.messages import VALIDATION_FAILED_MESSAGE
from dharmiq.agents.citation_validation import citations_from_state
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.agents.streaming import citation_markers_in_chunk, split_answer_token_chunks
from dharmiq.corpus.footnote import append_corpus_footnote
from dharmiq.corpus.indexed_at import get_corpus_indexed_date
from dharmiq.db.models.chats import ChatMessage, ChatRequestStatus, MessageRole
from dharmiq.schemas.citations import CitationRecord


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def _replay_validated_answer(
    runtime: GraphRuntime,
    answer_text: str,
    citations: list[CitationRecord],
) -> None:
    """Replay the validated answer as SSE token chunks — no LLM call (R4-4)."""
    emitter = runtime.emitter
    if emitter is None:
        return

    for citation in citations:
        await emitter.emit_citation(
            marker=citation.marker,
            chunk_id=citation.chunk_id,
            document_title=citation.document_title,
            quote_text=citation.quote_text,
            source_type=citation.source_type,
            document_id=citation.document_id,
        )

    for chunk in split_answer_token_chunks(answer_text):
        await emitter.emit_answer_token(
            chunk,
            citation_markers=citation_markers_in_chunk(chunk),
        )


async def finalizer_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    citations = citations_from_state(state.get("citations") or state.get("citation_map"))
    verdict = state.get("validator_verdict") or {}
    validation_blocked = bool(state.get("validation_blocked"))

    final_warning = state.get("final_warning")

    if validation_blocked:
        if runtime.emitter is not None:
            await runtime.emitter.emit_error(
                code="VALIDATION_FAILED",
                message=VALIDATION_FAILED_MESSAGE,
            )
        answer_text = VALIDATION_FAILED_MESSAGE
        agent_name = "validator"
    elif state.get("weak_retrieval"):
        answer_text = state.get("final_answer") or state.get("draft_answer", "")
        agent_name = "refusal"
    else:
        answer_text = state.get("final_answer") or state.get("draft_answer", "")
        agent_name = "answerer"
        if (
            verdict.get("must_regenerate")
            and final_warning
            and final_warning not in answer_text
        ):
            answer_text = f"{answer_text.rstrip()}\n\n> {final_warning}"

    indexed_date = await get_corpus_indexed_date(runtime.db)
    answer_text = append_corpus_footnote(answer_text, indexed_date)

    if not validation_blocked:
        await _replay_validated_answer(runtime, answer_text, citations)

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
    await runtime.db.commit()

    for message in runtime.new_messages:
        await runtime.db.refresh(message)

    return {
        "final_answer": answer_text,
        "final_warning": final_warning,
        "citations": [citation.model_dump(mode="json") for citation in citations],
        "validation_blocked": validation_blocked,
    }
