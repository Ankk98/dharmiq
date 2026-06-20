from __future__ import annotations

from dataclasses import dataclass

from dharmiq.llm.agents.base import call_json_agent
from dharmiq.llm.openrouter_client import OpenRouterClient
from dharmiq.llm.prompts.loader import load_prompt
from dharmiq.llm.retrieval import RetrievedChunk, format_retrieved_context
from dharmiq.schemas.citations import CitationRecord


@dataclass(frozen=True)
class ValidatorResult:
    must_regenerate: bool
    issues: list[str]
    regeneration_instructions: str
    final_warning: str
    unsupported_claims: list[str]
    statutory_claims_checked: int
    tokens_used: int


def _format_citation_map(citations: list[CitationRecord]) -> str:
    if not citations:
        return "(no inline citation markers mapped)"

    lines: list[str] = []
    for record in citations:
        quote = f' quote="{record.quote_text}"' if record.quote_text else ""
        lines.append(
            f"[{record.marker}] {record.source_type} {record.document_title} "
            f"chunk_id={record.chunk_id}{quote}"
        )
    return "\n".join(lines)


async def run_validator(
    client: OpenRouterClient,
    *,
    user_question: str,
    retrieved_chunks: list[RetrievedChunk],
    draft_answer: str,
    citation_map: list[CitationRecord] | None = None,
) -> ValidatorResult:
    prompt = load_prompt("validator")
    citations = citation_map or []
    user_content = prompt.render_user(
        user_question=user_question,
        retrieved_context=format_retrieved_context(retrieved_chunks),
        citation_map=_format_citation_map(citations),
        draft_answer=draft_answer,
    )
    data, tokens = await call_json_agent(
        client,
        system=prompt.system,
        user_content=user_content,
    )

    issues = data.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    unsupported = data.get("unsupported_claims") or []
    if not isinstance(unsupported, list):
        unsupported = []

    return ValidatorResult(
        must_regenerate=bool(data.get("must_regenerate")),
        issues=[str(item).strip() for item in issues if str(item).strip()],
        regeneration_instructions=str(data.get("regeneration_instructions") or "").strip(),
        final_warning=str(data.get("final_warning") or "").strip(),
        unsupported_claims=[str(item).strip() for item in unsupported if str(item).strip()],
        statutory_claims_checked=int(data.get("statutory_claims_checked") or 0),
        tokens_used=tokens,
    )


def format_citation_map_for_prompt(citations: list[CitationRecord]) -> str:
    return _format_citation_map(citations)
