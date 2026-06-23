from __future__ import annotations

from datetime import UTC, date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.documents import SourceDocument


async def get_corpus_indexed_date(db: AsyncSession) -> date | None:
    """Return the UTC calendar date of the latest indexed corpus document."""
    latest = await db.scalar(
        select(func.max(SourceDocument.indexed_at)).where(SourceDocument.indexed_at.is_not(None))
    )
    if latest is None:
        return None
    return latest.astimezone(UTC).date()
