from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from dharmiq.agents.nodes.answerer import answerer_node
from dharmiq.agents.nodes.clarifier import clarifier_node
from dharmiq.agents.nodes.finalizer import finalizer_node
from dharmiq.agents.nodes.input_guard import input_guard_node
from dharmiq.agents.nodes.query_rewriter import query_rewriter_node
from dharmiq.agents.nodes.retrieve import retrieve_node
from dharmiq.agents.nodes.validator import validator_node
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.agents.progress import (
    NODE_PROGRESS_LABELS,
    default_step_details,
    query_rewriter_step_details,
    retrieve_step_details,
    validator_step_details,
)

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


StepDetailFn = Callable[[AgentGraphState, dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]]

STEP_DETAIL_FNS: dict[str, StepDetailFn] = {
    "query_rewriter": query_rewriter_step_details,
    "retrieve": retrieve_step_details,
    "validator": validator_step_details,
}


def _resolve_detail_fn(step_id: str, detail_fn: StepDetailFn | None) -> StepDetailFn:
    if detail_fn is not None:
        return detail_fn
    if step_id in STEP_DETAIL_FNS:
        return STEP_DETAIL_FNS[step_id]

    def _default(state: AgentGraphState, result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return default_step_details(step_id, state, result)

    return _default


def with_progress(
    step_id: str,
    node_fn: Callable[..., Awaitable[dict[str, Any]]],
    *,
    detail_fn: StepDetailFn | None = None,
) -> Callable[..., Awaitable[dict[str, Any]]]:
    resolved_detail_fn = _resolve_detail_fn(step_id, detail_fn)

    @wraps(node_fn)
    async def wrapped(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
        runtime: GraphRuntime = config["configurable"]["runtime"]
        emitter = runtime.emitter
        if emitter is not None:
            await emitter.emit_step_start(step_id)
        try:
            result = await node_fn(state, config)
            if emitter is not None:
                detailed, debug = resolved_detail_fn(state, result)
                await emitter.emit_step_end_tiers(step_id, detailed=detailed, debug=debug)
            return result
        except Exception:
            if emitter is not None:
                await emitter.emit_step_failed(
                    step_id,
                    label=NODE_PROGRESS_LABELS.get(step_id, step_id),
                )
            raise

    return wrapped


def _route_after_input_guard(state: AgentGraphState) -> Literal["clarifier", "__end__"]:
    if state.get("blocked"):
        return END
    return "clarifier"


def _route_after_clarifier(state: AgentGraphState) -> Literal["query_rewriter", "__end__"]:
    if (
        state.get("needs_clarification")
        and state.get("clarifier_round", 0) < 3
        and not state.get("force_answer")
    ):
        return END
    return "query_rewriter"


def _route_after_validator(state: AgentGraphState) -> Literal["answerer", "finalizer"]:
    verdict = state.get("validator_verdict") or {}
    max_retries = state.get("max_validator_retries", 3)
    if verdict.get("must_regenerate") and state.get("regeneration_count", 0) < max_retries:
        return "answerer"
    return "finalizer"


def build_agent_graph(
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    builder = StateGraph(AgentGraphState)

    builder.add_node("input_guard", with_progress("input_guard", input_guard_node))
    builder.add_node("clarifier", with_progress("clarifier", clarifier_node))
    builder.add_node("query_rewriter", with_progress("query_rewriter", query_rewriter_node))
    builder.add_node("retrieve", with_progress("retrieve", retrieve_node))
    builder.add_node("answerer", with_progress("answerer", answerer_node))
    builder.add_node("validator", with_progress("validator", validator_node))
    builder.add_node("finalizer", with_progress("finalizer", finalizer_node))

    builder.set_entry_point("input_guard")
    builder.add_conditional_edges("input_guard", _route_after_input_guard)
    builder.add_conditional_edges("clarifier", _route_after_clarifier)
    builder.add_edge("query_rewriter", "retrieve")
    builder.add_edge("retrieve", "answerer")
    builder.add_edge("answerer", "validator")
    builder.add_conditional_edges("validator", _route_after_validator)
    builder.add_edge("finalizer", END)

    return builder.compile(checkpointer=checkpointer)
