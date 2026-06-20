from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig

from dharmiq.agents.citation_validation import citation_records_to_state, enrich_citations
from dharmiq.agents.state import AgentGraphState, chunks_from_state


async def citation_enricher_node(state: AgentGraphState, config: RunnableConfig) -> dict[str, Any]:
    del config
    draft = state.get("draft_answer", "")
    chunks = chunks_from_state(state.get("merged_chunks", []))
    records = enrich_citations(draft, chunks)
    return {
        "citation_map": citation_records_to_state(records),
        "citations": citation_records_to_state(records),
    }
