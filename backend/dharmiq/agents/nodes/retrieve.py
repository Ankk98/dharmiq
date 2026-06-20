from __future__ import annotations

import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState, chunk_to_state
from dharmiq.llm.retrieval import retrieve_multi_query


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


def _attached_upload_ids(state: AgentGraphState) -> list[uuid.UUID]:
    raw = state.get("attached_upload_ids") or []
    return [uuid.UUID(item) if isinstance(item, str) else item for item in raw]


async def retrieve_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    cfg = runtime.settings
    queries = state.get("search_queries") or []

    result = await retrieve_multi_query(
        runtime.db,
        queries,
        runtime.user.id,
        rerank_query=state.get("user_message"),
        attached_upload_ids=_attached_upload_ids(state),
        top_k=cfg.retrieval.rerank_top_k,
    )

    return {
        "merged_chunks": [chunk_to_state(chunk) for chunk in result.chunks],
        "weak_retrieval": result.weak_retrieval,
        "top_rerank_score": result.top_rerank_score,
    }
