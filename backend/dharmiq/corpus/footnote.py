from __future__ import annotations

from datetime import date

from dharmiq.agents.messages import REFUSAL_MESSAGE, VALIDATION_FAILED_MESSAGE

SOURCES_INDEXED_MARKER = "Sources indexed:"


def _should_skip_footnote(answer: str) -> bool:
    stripped = answer.strip()
    if stripped == REFUSAL_MESSAGE or stripped.startswith(REFUSAL_MESSAGE):
        return True
    if stripped == VALIDATION_FAILED_MESSAGE or stripped.startswith(VALIDATION_FAILED_MESSAGE):
        return True
    return False


def append_corpus_footnote(answer: str, indexed_date: date | None) -> str:
    """Append TRD-90 corpus index footnote when appropriate (idempotent)."""
    if SOURCES_INDEXED_MARKER in answer or _should_skip_footnote(answer):
        return answer

    date_label = indexed_date.isoformat() if indexed_date is not None else "unknown"
    footnote = (
        f"\n\n---\n"
        f"Sources indexed: {date_label} (UTC). "
        "Citations refer to central law as indexed; confirm critical details with a qualified lawyer."
    )
    return answer.rstrip() + footnote
