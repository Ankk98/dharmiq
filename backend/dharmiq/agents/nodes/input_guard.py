from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.guardrails.input_validator import validate_message


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def input_guard_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    result = validate_message(
        state.get("user_message", ""),
        max_length=runtime.settings.guardrails.max_message_length,
    )
    if not result.allowed:
        return {
            "blocked": True,
            "block_reason": result.reason,
        }
    return {"blocked": False}
