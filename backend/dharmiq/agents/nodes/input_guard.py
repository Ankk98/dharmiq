from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def input_guard_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    _runtime(config)
    return {"blocked": False}
