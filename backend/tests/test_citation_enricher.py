from __future__ import annotations

import uuid

import pytest

from dharmiq.agents.citation_validation import (
    enrich_citations,
    find_uncited_statutory_claims,
    validate_draft_grounding,
)
from dharmiq.agents.nodes.citation_enricher import citation_enricher_node
from dharmiq.llm.prompts.loader import load_prompt
from dharmiq.llm.retrieval import RetrievedChunk
from dharmiq.uploads.quote_extractor import find_quote_span, quotes_match


def _sample_chunk(*, text: str, chunk_index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_type="corpus",
        document_id=uuid.uuid4(),
        document_title="Code of Criminal Procedure, 1973",
        text=text,
        score=0.91,
        chunk_index=chunk_index,
        page_start=1,
        page_end=1,
    )


def test_answerer_prompt_requires_blockquote() -> None:
    prompt = load_prompt("answerer")
    assert "blockquote" in prompt.system.lower()
    assert "[1]" in prompt.system


def test_citation_enricher_maps_markers() -> None:
    chunk = _sample_chunk(text="Section 41 allows arrest without warrant in listed cases.")
    draft = "Police may arrest without warrant in listed cases [1]."
    records = enrich_citations(draft, [chunk])

    assert len(records) == 1
    assert records[0].marker == 1
    assert records[0].chunk_id == chunk.chunk_id
    assert records[0].document_title == chunk.document_title


@pytest.mark.asyncio
async def test_citation_enricher_node_writes_state() -> None:
    chunk = _sample_chunk(text="Article 22 protects against arbitrary arrest.")
    state = {
        "draft_answer": "Rights apply under Article 22 [1].",
        "merged_chunks": [
            {
                "chunk_id": str(chunk.chunk_id),
                "source_type": chunk.source_type,
                "document_id": str(chunk.document_id),
                "document_title": chunk.document_title,
                "text": chunk.text,
                "score": chunk.score,
                "chunk_index": chunk.chunk_index,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            }
        ],
    }
    result = await citation_enricher_node(state, {"configurable": {}})
    assert len(result["citation_map"]) == 1
    assert result["citation_map"][0]["marker"] == 1


def test_quote_fuzzy_match_tolerates_whitespace_and_section_symbol() -> None:
    source = "Section 41 CrPC — When police may arrest without warrant."
    quote = "Section  41   CrPC - When police may arrest without warrant."
    assert quotes_match(quote, source)

    symbol_quote = "§ 41 When police may arrest without warrant."
    match = find_quote_span(symbol_quote, source)
    assert match is not None
    assert match.similarity >= 0.95


def test_quote_rejects_genuine_misquote() -> None:
    source = "Section 41 allows arrest without warrant in listed cases."
    misquote = "Section 41 requires a magistrate order before any arrest."
    assert find_quote_span(misquote, source) is None
    assert not quotes_match(misquote, source)


def test_validator_blocks_unsupported() -> None:
    chunk = _sample_chunk(text="Section 12 covers deficiency in service.")
    draft = "Section 99 creates a blanket arrest power without any conditions."
    records = enrich_citations("General consumer rights [1].", [chunk])
    issues = validate_draft_grounding(draft, records, [chunk])
    assert issues
    assert find_uncited_statutory_claims(draft)


def test_enricher_attaches_blockquote_span() -> None:
    chunk = _sample_chunk(
        text="Article 22 protects against arbitrary arrest and detention.",
    )
    draft = (
        "The law protects you [1].\n\n"
        "> Article 22 protects against arbitrary arrest and detention."
    )
    records = enrich_citations(draft, [chunk])
    assert records[0].quote_text is not None
    assert "Article 22" in records[0].quote_text
