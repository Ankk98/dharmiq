from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.messages import REFUSAL_MESSAGE
from dharmiq.agents.state import AgentGraphState


async def refusal_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    del state, config
    return {
        "weak_retrieval": True,
        "draft_answer": REFUSAL_MESSAGE,
        "final_answer": REFUSAL_MESSAGE,
        "final_warning": None,
        "citations": [],
    }
