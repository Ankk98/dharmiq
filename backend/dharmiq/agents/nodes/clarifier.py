from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.llm.agents.clarifier import run_clarifier
from dharmiq.observability.metrics import record_llm_tokens


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def clarifier_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    cfg = runtime.settings

    clarifier = await run_clarifier(
        runtime.client,
        user_question=state["user_message"],
        history=runtime.history[:-1],
        history_limit=cfg.chat.history_limit,
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
        "clarifier_reason": clarifier.reason,
        "total_tokens": state.get("total_tokens", 0) + clarifier.tokens_used,
    }
