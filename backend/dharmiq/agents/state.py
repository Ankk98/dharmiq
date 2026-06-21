from __future__ import annotations

import uuid
from typing import Any, Literal, TypedDict

from dharmiq.llm.retrieval import RetrievedChunk

ProgressView = Literal["concise", "detailed"]
EventVisibilityTier = Literal["concise", "detailed", "debug"]


class ValidatorVerdictState(TypedDict, total=False):
    must_regenerate: bool
    issues: list[str]
    regeneration_instructions: str
    final_warning: str | None
    unsupported_claims: list[str]
    statutory_claims_checked: int


class AgentGraphState(TypedDict, total=False):
    chat_request_id: str
    session_id: str
    user_id: str

    user_message: str
    attached_upload_ids: list[str]

    topic: str
    needs_clarification: bool
    followup_questions: list[str]
    followup_items: list[dict[str, Any]]
    clarifier_round: int
    force_answer: bool
    stated_assumptions: list[str]
    clarifier_reason: str | None

    search_queries: list[str]
    merged_chunks: list[dict[str, Any]]
    weak_retrieval: bool
    top_rerank_score: float
    facts: str

    draft_answer: str
    citation_map: list[dict[str, Any]]
    regeneration_instructions: str | None
    regeneration_count: int
    max_validator_retries: int
    validator_verdict: ValidatorVerdictState
    validation_blocked: bool
    final_answer: str
    final_warning: str | None
    citations: list[dict[str, Any]]

    total_tokens: int
    blocked: bool
    block_reason: str | None
    error_message: str | None


def chunk_to_state(chunk: RetrievedChunk) -> dict[str, Any]:
    return {
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


def chunk_from_state(data: dict[str, Any]) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.UUID(data["chunk_id"]),
        source_type=data["source_type"],
        document_id=uuid.UUID(data["document_id"]),
        document_title=data["document_title"],
        text=data["text"],
        score=float(data["score"]),
        chunk_index=int(data["chunk_index"]),
        page_start=data.get("page_start"),
        page_end=data.get("page_end"),
    )


def chunks_from_state(items: list[dict[str, Any]]) -> list[RetrievedChunk]:
    return [chunk_from_state(item) for item in items]
