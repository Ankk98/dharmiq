from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langgraph.graph import END, StateGraph

from dharmiq.agents.nodes.answerer import answerer_node
from dharmiq.agents.nodes.clarifier import clarifier_node
from dharmiq.agents.nodes.finalizer import finalizer_node
from dharmiq.agents.nodes.input_guard import input_guard_node
from dharmiq.agents.nodes.query_rewriter import query_rewriter_node
from dharmiq.agents.nodes.retrieve import retrieve_node
from dharmiq.agents.nodes.validator import validator_node
from dharmiq.agents.state import AgentGraphState

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph


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

    builder.add_node("input_guard", input_guard_node)
    builder.add_node("clarifier", clarifier_node)
    builder.add_node("query_rewriter", query_rewriter_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("answerer", answerer_node)
    builder.add_node("validator", validator_node)
    builder.add_node("finalizer", finalizer_node)

    builder.set_entry_point("input_guard")
    builder.add_conditional_edges("input_guard", _route_after_input_guard)
    builder.add_conditional_edges("clarifier", _route_after_clarifier)
    builder.add_edge("query_rewriter", "retrieve")
    builder.add_edge("retrieve", "answerer")
    builder.add_edge("answerer", "validator")
    builder.add_conditional_edges("validator", _route_after_validator)
    builder.add_edge("finalizer", END)

    return builder.compile(checkpointer=checkpointer)
