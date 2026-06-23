from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.documents import SourceDocument
from dharmiq.schemas.citations import CitationRecord


async def load_canonical_urls(
    db: AsyncSession,
    document_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not document_ids:
        return {}

    result = await db.execute(
        select(SourceDocument.id, SourceDocument.canonical_url).where(
            SourceDocument.id.in_(document_ids)
        )
    )
    return {
        row.id: row.canonical_url
        for row in result.all()
        if row.canonical_url
    }


async def attach_canonical_urls(
    db: AsyncSession,
    records: list[CitationRecord],
) -> list[CitationRecord]:
    corpus_doc_ids = {
        record.document_id for record in records if record.source_type == "corpus"
    }
    if not corpus_doc_ids:
        return records

    url_by_id = await load_canonical_urls(db, corpus_doc_ids)
    if not url_by_id:
        return records

    return [
        record.model_copy(
            update={"canonical_url": url_by_id.get(record.document_id)}
        )
        if record.source_type == "corpus"
        else record
        for record in records
    ]
