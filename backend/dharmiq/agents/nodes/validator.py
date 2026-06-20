from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState, ValidatorVerdictState, chunks_from_state
from dharmiq.llm.agents.validator import run_validator
from dharmiq.observability.metrics import record_llm_tokens


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


async def validator_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    retrieved = chunks_from_state(state.get("merged_chunks", []))
    answer_text = state.get("draft_answer", "")

    validator = await run_validator(
        runtime.client,
        user_question=state["user_message"],
        retrieved_chunks=retrieved,
        draft_answer=answer_text,
    )
    record_llm_tokens(
        model=runtime.model_name,
        agent="validator",
        tokens=validator.tokens_used,
    )

    verdict: ValidatorVerdictState = {
        "must_regenerate": validator.must_regenerate,
        "issues": validator.issues,
        "regeneration_instructions": validator.regeneration_instructions,
        "final_warning": validator.final_warning,
    }

    updates: dict[str, Any] = {
        "validator_verdict": verdict,
        "total_tokens": state.get("total_tokens", 0) + validator.tokens_used,
    }

    if validator.must_regenerate:
        updates["regeneration_count"] = state.get("regeneration_count", 0) + 1
        updates["regeneration_instructions"] = validator.regeneration_instructions

    if not validator.must_regenerate:
        updates["final_warning"] = validator.final_warning or None

    return updates
