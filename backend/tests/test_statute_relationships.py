from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from dharmiq.db.models.statute_relationships import StatuteRelationship
from dharmiq.db.session import get_session_factory
from dharmiq.ingestion.relationships import collect_relationship_edges, sync_statute_relationships
from dharmiq.eval.tools.allowlist import load_allowlist

FIXTURE_ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "v06-allowlist-fixture.yaml"


@pytest.fixture(autouse=True)
async def _clean_relationships() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM statute_relationships"))
        await db.commit()
    yield


def test_collect_relationship_edges_from_fixture() -> None:
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    edges = collect_relationship_edges(instruments)
    assert ("IN-CPA-1986", "IN-CPA-2019", "superseded_by") in edges


@pytest.mark.asyncio
async def test_sync_statute_relationships_idempotent() -> None:
    factory = get_session_factory()
    async with factory() as db:
        first = await sync_statute_relationships(db, FIXTURE_ALLOWLIST)
        await db.commit()
        count_after_first = (
            await db.execute(select(func.count()).select_from(StatuteRelationship))
        ).scalar_one()

        second = await sync_statute_relationships(db, FIXTURE_ALLOWLIST)
        await db.commit()
        count_after_second = (
            await db.execute(select(func.count()).select_from(StatuteRelationship))
        ).scalar_one()

        assert first >= 1
        assert count_after_first == count_after_second
        assert second >= 1

        edge = (
            await db.execute(
                select(StatuteRelationship).where(
                    StatuteRelationship.from_source_id == "IN-CPA-1986",
                    StatuteRelationship.to_source_id == "IN-CPA-2019",
                )
            )
        ).scalar_one()
        assert edge.relationship == "superseded_by"
