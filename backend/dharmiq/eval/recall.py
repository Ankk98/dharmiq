from __future__ import annotations

from typing import Any, Sequence


def _expected_section_strings(expected_citations: list[dict[str, Any]]) -> list[str]:
    sections: list[str] = []
    for citation in expected_citations:
        if not isinstance(citation, dict):
            continue
        section = str(citation.get("section", "")).strip()
        if section:
            sections.append(section)
    return sections


def _chunk_section_label(chunk: Any) -> str | None:
    label = getattr(chunk, "section_label", None)
    if isinstance(label, str) and label.strip():
        return label.strip()

    metadata = getattr(chunk, "metadata", None) or getattr(chunk, "chunk_metadata", None)
    if isinstance(metadata, dict):
        raw = metadata.get("section_label")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _chunk_search_text(chunk: Any) -> str:
    text = str(getattr(chunk, "text", "") or "")
    label = _chunk_section_label(chunk)
    if label:
        return f"{label}\n{text}"
    return text


def _section_hit(search_text: str, section: str) -> bool:
    if not section:
        return False
    return section.casefold() in search_text.casefold()


def compute_recall_at_k(
    chunks: Sequence[Any],
    expected_citations: list[dict[str, Any]],
    *,
    k: int = 5,
) -> float:
    """Return 1.0 if any expected section appears in the top-k post-rerank chunks."""
    sections = _expected_section_strings(expected_citations)
    if not sections or k <= 0:
        return 0.0

    top_chunks = list(chunks)[:k]
    if not top_chunks:
        return 0.0

    for section in sections:
        for chunk in top_chunks:
            if _section_hit(_chunk_search_text(chunk), section):
                return 1.0
    return 0.0
