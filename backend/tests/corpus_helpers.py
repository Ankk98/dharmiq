from __future__ import annotations

from datetime import UTC, datetime

from dharmiq.db.models.documents import SourceDocument


def with_indexed_at(document: SourceDocument) -> SourceDocument:
    """Mark a source document as indexed so corpus retrieval includes it."""
    if document.indexed_at is None:
        document.indexed_at = datetime.now(UTC)
    return document
