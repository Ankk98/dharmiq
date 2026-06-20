from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.citation_validation import (
    citations_from_state,
    validate_draft_grounding,
)
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState, ValidatorVerdictState, chunks_from_state
from dharmiq.llm.agents.validator import run_validator
from dharmiq.observability.metrics import record_llm_tokens


def _runtime(config: RunnableConfig) -> GraphRuntime:
    return config["configurable"]["runtime"]


def _merge_issues(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for issue in group:
            if issue not in seen:
                seen.add(issue)
                merged.append(issue)
    return merged


def _build_regeneration_instructions(issues: list[str], llm_instructions: str) -> str:
    if llm_instructions:
        return llm_instructions
    if not issues:
        return ""
    return "Fix the following validation issues:\n- " + "\n- ".join(issues)


async def validator_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    runtime = _runtime(config)
    retrieved = chunks_from_state(state.get("merged_chunks", []))
    answer_text = state.get("draft_answer", "")
    citations = citations_from_state(state.get("citation_map") or state.get("citations"))
    max_retries = state.get("max_validator_retries", runtime.settings.chat.max_validator_retries)
    regeneration_count = state.get("regeneration_count", 0)

    programmatic_issues = validate_draft_grounding(answer_text, citations, retrieved)

    validator = await run_validator(
        runtime.client,
        user_question=state["user_message"],
        retrieved_chunks=retrieved,
        draft_answer=answer_text,
        citation_map=citations,
    )
    record_llm_tokens(
        model=runtime.model_name,
        agent="validator",
        tokens=validator.tokens_used,
    )

    issues = _merge_issues(programmatic_issues, validator.issues)
    must_regenerate = bool(programmatic_issues) or validator.must_regenerate
    regeneration_instructions = _build_regeneration_instructions(
        issues,
        validator.regeneration_instructions,
    )

    verdict: ValidatorVerdictState = {
        "must_regenerate": must_regenerate,
        "issues": issues,
        "regeneration_instructions": regeneration_instructions,
        "final_warning": validator.final_warning,
        "unsupported_claims": validator.unsupported_claims,
        "statutory_claims_checked": validator.statutory_claims_checked,
    }

    updates: dict[str, Any] = {
        "validator_verdict": verdict,
        "total_tokens": state.get("total_tokens", 0) + validator.tokens_used,
    }

    if must_regenerate:
        updates["regeneration_count"] = regeneration_count + 1
        updates["regeneration_instructions"] = regeneration_instructions
        if regeneration_count + 1 >= max_retries:
            updates["validation_blocked"] = True
            updates["final_answer"] = None
    else:
        updates["validation_blocked"] = False
        updates["final_answer"] = answer_text
        updates["final_warning"] = validator.final_warning or None

    return updates
