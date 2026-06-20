from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.state import AgentGraphState

REFUSAL_MESSAGE = (
    "I could not find sufficient sources in the corpus or your attached documents "
    "to answer reliably. Try rephrasing your question, attaching a relevant document, "
    "or narrowing the topic."
)


async def refusal_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    del state, config
    return {
        "weak_retrieval": True,
        "draft_answer": REFUSAL_MESSAGE,
        "final_answer": REFUSAL_MESSAGE,
        "final_warning": None,
        "citations": [],
    }
