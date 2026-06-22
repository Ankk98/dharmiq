from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState, chunks_from_state
from dharmiq.llm.agents.answerer import run_answerer
from dharmiq.llm.usage import record_llm_usage
from dharmiq.observability.metrics import record_llm_tokens


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def answerer_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    retrieved = chunks_from_state(state.get("merged_chunks", []))
    regen = state.get("regeneration_instructions")

    draft = await run_answerer(
        runtime.client,
        user_question=state["user_message"],
        facts=state.get("facts", ""),
        retrieved_chunks=retrieved,
        regeneration_instructions=regen or None,
    )
    await record_llm_usage(
        runtime.db,
        user_id=runtime.user.id,
        chat_request_id=runtime.chat_request.id,
        session_id=runtime.chat_session.id,
        agent_role="answerer",
        model=runtime.model_name,
        response=draft.llm_response,
    )
    record_llm_tokens(
        model=runtime.model_name,
        agent="answerer",
        tokens=draft.tokens_used,
    )

    return {
        "draft_answer": draft.answer,
        "total_tokens": state.get("total_tokens", 0) + draft.tokens_used,
    }
