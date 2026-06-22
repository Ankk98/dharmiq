from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.llm.agents.base import extract_user_facts
from dharmiq.llm.agents.query_rewriter import run_query_rewriter
from dharmiq.llm.usage import record_llm_usage
from dharmiq.observability.metrics import record_llm_tokens


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def query_rewriter_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    facts = extract_user_facts(runtime.history + [runtime.user_msg])

    rewriter = await run_query_rewriter(
        runtime.client,
        user_question=state["user_message"],
        topic=state.get("topic", "general"),
        facts=facts,
    )
    await record_llm_usage(
        runtime.db,
        user_id=runtime.user.id,
        chat_request_id=runtime.chat_request.id,
        session_id=runtime.chat_session.id,
        agent_role="query_rewriter",
        model=runtime.model_name,
        response=rewriter.llm_response,
    )
    record_llm_tokens(
        model=runtime.model_name,
        agent="query_rewriter",
        tokens=rewriter.tokens_used,
    )

    return {
        "facts": facts,
        "search_queries": rewriter.queries,
        "total_tokens": state.get("total_tokens", 0) + rewriter.tokens_used,
    }
