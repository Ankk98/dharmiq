from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from dharmiq.llm.agents.base import call_json_agent
from dharmiq.llm.openrouter_client import OpenRouterClient, extract_token_usage

_JUDGE_SYSTEM = """You are a senior legal reviewer evaluating a RAG assistant's answer.
Score the answer on semantic correctness against the reference answer and citation quality.

Respond with JSON only:
{
  "answer_correctness": 0.0 to 1.0,
  "citation_correctness": 0.0 to 1.0,
  "reason": "brief explanation"
}

answer_correctness: how well the generated answer matches the reference in substance (not wording).
citation_correctness: whether key legal sections cited in the reference appear in the generated answer.
Ignore disclaimers about not being legal advice when scoring correctness."""


@dataclass(frozen=True)
class JudgeScores:
    answer_correctness: float
    citation_correctness: float
    reason: str


async def run_llm_judge(
    client: OpenRouterClient,
    *,
    question: str,
    generated_answer: str,
    reference_answer: str,
    expected_citations: list[dict[str, Any]],
    model: str | None = None,
) -> tuple[JudgeScores, int]:
    citations_text = json.dumps(expected_citations, indent=2) if expected_citations else "(none specified)"
    user_content = "\n".join(
        [
            f"Question: {question}",
            f"Reference answer: {reference_answer}",
            f"Expected citation hints: {citations_text}",
            f"Generated answer: {generated_answer}",
        ]
    )
    data, response = await call_json_agent(
        client,
        system=_JUDGE_SYSTEM,
        user_content=user_content,
        model=model,
    )
    tokens = extract_token_usage(response)

    answer_score = _clamp_score(data.get("answer_correctness"))
    citation_score = _clamp_score(data.get("citation_correctness"))
    reason = str(data.get("reason") or "").strip()

    return (
        JudgeScores(
            answer_correctness=answer_score,
            citation_correctness=citation_score,
            reason=reason,
        ),
        tokens,
    )


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))
