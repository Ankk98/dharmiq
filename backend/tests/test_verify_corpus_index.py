from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.eval.tools.verify_corpus_index import verify_corpus_index

FIXTURE_ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "mvp-allowlist-fixture.yaml"


@pytest.fixture(autouse=True)
async def _clean_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


@pytest.mark.timeout(30)
async def test_verify_fails_missing_docs(db: AsyncSession) -> None:
    all_ok, report = await verify_corpus_index(db, allowlist_path=FIXTURE_ALLOWLIST)
    assert all_ok is False
    assert report["indexed_document_count"] == 0
    assert report["expected_document_count"] == 3
    assert len(report["missing_source_ids"]) == 3


@pytest.mark.timeout(30)
async def test_verify_passes_when_seeded(db: AsyncSession) -> None:
    for source_id, title in (
        ("IN-CONSTITUTION-1949", "The Constitution of India"),
        ("IN-RTI-2005", "The Right to Information Act, 2005"),
        ("IN-CPA-2019", "The Consumer Protection Act, 2019"),
    ):
        document = SourceDocument(
            source_id=source_id,
            title=title,
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash=f"hash-{source_id}",
            file_path=f"/tmp/{source_id}.pdf",
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                text=f"Sample text for {title}.",
            )
        )
    await db.commit()

    all_ok, report = await verify_corpus_index(db, allowlist_path=FIXTURE_ALLOWLIST)
    assert all_ok is True
    assert report["indexed_document_count"] == 3
    assert report["corpus_chunk_count"] == 3
    assert report["missing_source_ids"] == []
    assert report["stale_source_ids"] == []


@pytest.mark.timeout(30)
async def test_verify_fails_when_document_has_no_chunks(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id="IN-CONSTITUTION-1949",
        title="The Constitution of India",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-constitution",
        file_path="/tmp/constitution.pdf",
    )
    db.add(document)
    await db.commit()

    all_ok, report = await verify_corpus_index(db, allowlist_path=FIXTURE_ALLOWLIST)
    assert all_ok is False
    assert "IN-CONSTITUTION-1949" in report["stale_source_ids"]
