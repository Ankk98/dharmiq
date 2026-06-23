from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.core.logging import get_logger
from dharmiq.db.models.statute_relationships import StatuteRelationship
from dharmiq.eval.tools.allowlist import AllowlistInstrument, load_allowlist

logger = get_logger(__name__)

RELATIONSHIP_SUPERSEDED_BY = "superseded_by"


def _edges_from_instrument(instrument: AllowlistInstrument) -> list[tuple[str, str, str]]:
    edges: list[tuple[str, str, str]] = []
    if instrument.superseded_by:
        edges.append((instrument.id, instrument.superseded_by, RELATIONSHIP_SUPERSEDED_BY))
    for replaced_id in instrument.supersedes:
        edges.append((replaced_id, instrument.id, RELATIONSHIP_SUPERSEDED_BY))
    return edges


def collect_relationship_edges(
    instruments: list[AllowlistInstrument],
) -> list[tuple[str, str, str]]:
    """Return deduplicated (from_source_id, to_source_id, relationship) tuples."""
    seen: set[tuple[str, str, str]] = set()
    edges: list[tuple[str, str, str]] = []
    for instrument in instruments:
        for edge in _edges_from_instrument(instrument):
            if edge in seen:
                continue
            seen.add(edge)
            edges.append(edge)
    return edges


async def sync_statute_relationships(
    db: AsyncSession,
    allowlist_path: Path,
) -> int:
    """Upsert supersession edges from allowlist YAML (idempotent)."""
    instruments = load_allowlist(allowlist_path)
    edges = collect_relationship_edges(instruments)
    if not edges:
        return 0

    for from_source_id, to_source_id, relationship in edges:
        stmt = (
            insert(StatuteRelationship)
            .values(
                id=uuid.uuid4(),
                from_source_id=from_source_id,
                to_source_id=to_source_id,
                relationship=relationship,
            )
            .on_conflict_do_nothing(
                index_elements=["from_source_id", "to_source_id", "relationship"],
            )
        )
        await db.execute(stmt)

    await db.flush()

    count = (
        await db.execute(select(StatuteRelationship.id))
    ).scalars().all()
    logger.info(
        "statute_relationships_synced",
        allowlist=str(allowlist_path),
        edges_upserted=len(edges),
        total_rows=len(count),
    )
    return len(edges)
