from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState, chunk_to_state
from dharmiq.llm.retrieval import retrieve_multi_query


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def retrieve_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    cfg = runtime.settings

    retrieved = await retrieve_multi_query(
        runtime.db,
        state.get("search_queries", []),
        runtime.user.id,
        top_k=cfg.retrieval.multi_query_top_k,
    )

    return {
        "merged_chunks": [chunk_to_state(chunk) for chunk in retrieved],
    }
