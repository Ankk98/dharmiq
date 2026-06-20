from __future__ import annotations

import re
import uuid
from typing import Any

from dharmiq.llm.retrieval import RetrievedChunk
from dharmiq.schemas.citations import CitationRecord
from dharmiq.uploads.quote_extractor import extract_blockquotes, find_quote_span

MARKER_PATTERN = re.compile(r"\[(\d+)\]")
LEGACY_CITATION_PATTERN = re.compile(
    r"\[doc:([0-9a-f-]+)\|chunk:([0-9a-f-]+)\]",
    re.IGNORECASE,
)

STATUTORY_CLAIM_PATTERN = re.compile(
    r"\b(Article|Section|Rule|Clause|Sub-section|Sub section)\s+[0-9A-Za-z().-]+",
    re.IGNORECASE,
)


def _chunk_lookup(chunks: list[RetrievedChunk]) -> dict[uuid.UUID, RetrievedChunk]:
    return {chunk.chunk_id: chunk for chunk in chunks}


def _marker_numbers(text: str) -> list[int]:
    seen: set[int] = set()
    ordered: list[int] = []
    for match in MARKER_PATTERN.finditer(text):
        marker = int(match.group(1))
        if marker not in seen:
            seen.add(marker)
            ordered.append(marker)
    return ordered


def _chunk_for_marker(marker: int, chunks: list[RetrievedChunk]) -> RetrievedChunk | None:
    if marker < 1 or marker > len(chunks):
        return None
    return chunks[marker - 1]


def _record_from_chunk(marker: int, chunk: RetrievedChunk) -> CitationRecord:
    section_label = None
    if chunk.source_type == "corpus":
        section_label = f"chunk {chunk.chunk_index + 1}"
    return CitationRecord(
        marker=marker,
        chunk_id=chunk.chunk_id,
        source_type=chunk.source_type,
        document_id=chunk.document_id,
        document_title=chunk.document_title,
        section_label=section_label,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
    )


def _attach_quote(record: CitationRecord, chunk: RetrievedChunk, quote: str) -> CitationRecord:
    match = find_quote_span(quote, chunk.text)
    if match is None:
        return record
    return record.model_copy(
        update={
            "quote_text": match.quote_text,
            "quote_start_char": match.start_char,
            "quote_end_char": match.end_char,
        }
    )


def enrich_citations(
    draft_answer: str,
    chunks: list[RetrievedChunk],
) -> list[CitationRecord]:
    """Map inline [n] markers (and legacy doc/chunk tags) to citation records."""
    if not draft_answer.strip() or not chunks:
        return []

    by_chunk_id = _chunk_lookup(chunks)
    records: dict[int, CitationRecord] = {}

    for marker in _marker_numbers(draft_answer):
        chunk = _chunk_for_marker(marker, chunks)
        if chunk is not None:
            records[marker] = _record_from_chunk(marker, chunk)

    for match in LEGACY_CITATION_PATTERN.finditer(draft_answer):
        document_id = uuid.UUID(match.group(1))
        chunk_id = uuid.UUID(match.group(2))
        chunk = by_chunk_id.get(chunk_id)
        if chunk is None or chunk.document_id != document_id:
            continue
        marker = len(records) + 1
        while marker in records:
            marker += 1
        records[marker] = _record_from_chunk(marker, chunk)

    blockquotes = extract_blockquotes(draft_answer)
    if blockquotes:
        for marker, record in list(records.items()):
            chunk = by_chunk_id.get(record.chunk_id)
            if chunk is None:
                continue
            for quote in blockquotes:
                updated = _attach_quote(record, chunk, quote)
                if updated.quote_text:
                    records[marker] = updated
                    break

    return [records[marker] for marker in sorted(records)]


def citation_records_to_state(records: list[CitationRecord]) -> list[dict[str, Any]]:
    return [record.model_dump(mode="json") for record in records]


def citations_from_state(raw: list[dict[str, Any]] | None) -> list[CitationRecord]:
    if not raw:
        return []
    return [CitationRecord.model_validate(item) for item in raw]


def _text_outside_blockquotes(text: str) -> str:
    kept_lines: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith(">"):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def find_uncited_statutory_claims(draft_answer: str) -> list[str]:
    """Return statutory-style claims that are not followed by an inline [n] marker."""
    issues: list[str] = []
    searchable = _text_outside_blockquotes(draft_answer)
    for match in STATUTORY_CLAIM_PATTERN.finditer(searchable):
        claim = match.group(0).strip()
        tail = draft_answer[match.end() : match.end() + 80]
        if MARKER_PATTERN.search(tail):
            continue
        issues.append(f"Statutory claim lacks citation marker: {claim}")
    return issues


def find_invalid_quotes(
    draft_answer: str,
    citations: list[CitationRecord],
    chunks: list[RetrievedChunk],
) -> list[str]:
    by_chunk_id = _chunk_lookup(chunks)
    issues: list[str] = []

    for quote in extract_blockquotes(draft_answer):
        validated = False
        for record in citations:
            chunk = by_chunk_id.get(record.chunk_id)
            if chunk is None:
                continue
            if find_quote_span(quote, chunk.text) is not None:
                validated = True
                break
        if not validated:
            issues.append(f"Block quote does not match any retrieved source: {quote[:120]}")

    for record in citations:
        if not record.quote_text:
            continue
        chunk = by_chunk_id.get(record.chunk_id)
        if chunk is None:
            issues.append(f"Citation [{record.marker}] references missing chunk")
            continue
        if find_quote_span(record.quote_text, chunk.text) is None:
            issues.append(f"Citation [{record.marker}] quote does not align with source text")

    return issues


def validate_draft_grounding(
    draft_answer: str,
    citations: list[CitationRecord],
    chunks: list[RetrievedChunk],
) -> list[str]:
    issues = find_uncited_statutory_claims(draft_answer)
    issues.extend(find_invalid_quotes(draft_answer, citations, chunks))
    return issues
