from __future__ import annotations

import re

from dharmiq.agents.nodes.refusal import REFUSAL_MESSAGE

_CITATION_MARKER_RE = re.compile(r"\[\d+\]")
_BLOCKQUOTE_RE = re.compile(r"^>\s+", re.MULTILINE)
_REFUSAL_PHRASES = (
    "could not find sufficient sources",
    "insufficient sources",
    REFUSAL_MESSAGE[:40].lower(),
)


def count_citation_markers(answer: str) -> int:
    return len(_CITATION_MARKER_RE.findall(answer))


def has_blockquote(answer: str) -> bool:
    return bool(_BLOCKQUOTE_RE.search(answer))


def is_refusal_answer(answer: str) -> bool:
    lowered = answer.lower()
    return any(phrase in lowered for phrase in _REFUSAL_PHRASES)


def evaluate_answer_expectations(
    *,
    answer: str,
    expect_refusal: bool | None,
    min_citation_count: int | None,
    expect_blockquote: bool | None,
) -> dict[str, float | int | bool]:
    metrics: dict[str, float | int | bool] = {
        "citation_count": count_citation_markers(answer),
        "has_blockquote": has_blockquote(answer),
        "is_refusal": is_refusal_answer(answer),
    }

    if min_citation_count is not None:
        metrics["citation_count_met"] = float(metrics["citation_count"] >= min_citation_count)

    if expect_blockquote is not None:
        metrics["blockquote_met"] = float(metrics["has_blockquote"] == expect_blockquote)

    if expect_refusal is not None:
        metrics["refusal_correct"] = float(metrics["is_refusal"] == expect_refusal)

    return metrics
