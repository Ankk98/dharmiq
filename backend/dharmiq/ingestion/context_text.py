from __future__ import annotations

from dharmiq.config.settings import Settings, get_settings
from dharmiq.ingestion.tokens import count_tokens, truncate_to_tokens


def build_context_text(
    text: str,
    *,
    section_label: str | None = None,
    max_tokens: int | None = None,
    settings: Settings | None = None,
) -> str:
    """Build tier-2 context text: section label + key sentences, capped at max_tokens."""
    cfg = settings or get_settings()
    limit = max_tokens if max_tokens is not None else cfg.ingestion.context_text_max_tokens

    body = text.strip()
    if not body:
        return section_label.strip() if section_label else ""

    paragraphs = [part.strip() for part in body.split("\n\n") if part.strip()]
    if not paragraphs:
        paragraphs = [body]

    first = paragraphs[0]
    last = paragraphs[-1] if len(paragraphs) > 1 else ""
    summary_parts = [first]
    if last and last != first:
        summary_parts.append(last)
    summary = "\n\n".join(summary_parts)

    label = section_label.strip() if section_label else ""
    if label:
        label_tokens = count_tokens(label)
        body_limit = max(limit - label_tokens - 1, 1)
        summary = truncate_to_tokens(summary, body_limit)
        return f"{label}\n\n{summary}".strip()

    if count_tokens(summary) <= limit:
        return summary
    return truncate_to_tokens(summary, limit)
