from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.db.models.documents import InstrumentStatus, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.ingestion.parser import PageText
from dharmiq.ingestion.pipeline import _register_scanned_document, process_document, sync_corpus_documents
from dharmiq.ingestion.scanner import scan_corpus_directory
from dharmiq.llm.embeddings import EmbeddingBackend


class _FixedEmbeddingBackend(EmbeddingBackend):
    def __init__(self, *, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text) % 7) / 7.0] * self._dimensions for text in texts]


class _StubParser:
    def extract_pages(self, file_path: Path) -> list[PageText]:
        return [
            PageText(
                page_number=1,
                text=(
                    "Section 1. Short title.\n"
                    "This Act may be called the Sample Act.\n\n"
                    "Section 2. Rights.\n"
                    "Every person has the right to fair treatment."
                ),
            )
        ]


def _write_pdf(path: Path, *, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


@pytest.fixture(autouse=True)
async def _clean_corpus_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.execute(text("DELETE FROM statute_relationships"))
        await db.commit()
    yield


def test_scanner_reads_manifest_status_and_dates(tmp_path: Path) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    pdf_path = corpus_dir / "cpa_1986.pdf"
    _write_pdf(pdf_path)

    manifest = [
        {
            "file": "cpa_1986.pdf",
            "source_id": "IN-CPA-1986",
            "title": "The Consumer Protection Act, 1986",
            "doc_type": "act",
            "jurisdiction": "central",
            "status": "superseded",
            "superseded_by": "IN-CPA-2019",
            "enactment_date": "1986-12-24",
            "enforcement_date": "1987-04-15",
            "canonical_url": "https://www.indiacode.nic.in/handle/123456789/9463",
            "scraper_instrument_id": "123",
        }
    ]
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    scanned = scan_corpus_directory(corpus_dir)
    assert len(scanned) == 1
    doc = scanned[0]
    assert doc.source_id == "IN-CPA-1986"
    assert doc.status == InstrumentStatus.SUPERSEDED
    assert doc.superseded_by_source_id == "IN-CPA-2019"
    assert doc.enactment_date == date(1986, 12, 24)
    assert doc.enforcement_date == date(1987, 4, 15)
    assert doc.canonical_url.endswith("/9463")
    assert doc.instrument_metadata["scraper_instrument_id"] == "123"


@pytest.mark.asyncio
async def test_register_document_persists_temporal_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    pdf_path = corpus_dir / "cpa_1986.pdf"
    _write_pdf(pdf_path)

    manifest = [
        {
            "file": "cpa_1986.pdf",
            "source_id": "IN-CPA-1986",
            "title": "The Consumer Protection Act, 1986",
            "doc_type": "act",
            "status": "superseded",
            "superseded_by": "IN-CPA-2019",
            "enactment_date": "1986-12-24",
            "enforcement_date": "1987-04-15",
            "canonical_url": "https://www.indiacode.nic.in/handle/123456789/9463",
        }
    ]
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.ingestion.corpus_dir = "corpus"

    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    scanned = scan_corpus_directory(corpus_dir)

    async with factory() as db:
        document_id, action = await _register_scanned_document(db, scanned[0])
        await db.commit()

        document = await db.get(SourceDocument, document_id)
        assert action == "created"
        assert document is not None
        assert document.status == InstrumentStatus.SUPERSEDED
        assert document.superseded_by_source_id == "IN-CPA-2019"
        assert document.enactment_date == date(1986, 12, 24)
        assert document.enforcement_date == date(1987, 4, 15)
        assert document.canonical_url is not None
        assert document.canonical_url.endswith("/9463")


@pytest.mark.asyncio
async def test_new_version_purges_old_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    pdf_path = corpus_dir / "sample_act.pdf"
    _write_pdf(pdf_path)

    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.ingestion.corpus_dir = "corpus"

    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    parser = _StubParser()
    backend = _FixedEmbeddingBackend()

    async with factory() as db:
        await sync_corpus_documents(db, settings=settings, enqueue=False)
        v1_id = (
            await db.execute(select(SourceDocument.id).where(SourceDocument.source_id == "sample_act"))
        ).scalar_one()
        await process_document(
            db,
            v1_id,
            settings=settings,
            parser=parser,
            embedding_backend=backend,
        )

        v1_chunks = (
            await db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
                {"id": v1_id},
            )
        ).scalar_one()
        assert v1_chunks > 0

        _write_pdf(pdf_path, pages=2)
        await sync_corpus_documents(db, settings=settings, enqueue=False)

        rows = (
            await db.execute(
                select(SourceDocument)
                .where(SourceDocument.source_id == "sample_act")
                .order_by(SourceDocument.version)
            )
        ).scalars().all()
        assert len(rows) == 2
        v2_id = rows[1].id

        v1_chunks_after = (
            await db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
                {"id": v1_id},
            )
        ).scalar_one()
        assert v1_chunks_after == 0

        v2_chunks = (
            await db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
                {"id": v2_id},
            )
        ).scalar_one()
        assert v2_chunks == 0

        await process_document(
            db,
            v2_id,
            settings=settings,
            parser=parser,
            embedding_backend=backend,
        )
        v2_chunks_after = (
            await db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
                {"id": v2_id},
            )
        ).scalar_one()
        assert v2_chunks_after > 0

        v1_chunks_final = (
            await db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
                {"id": v1_id},
            )
        ).scalar_one()
        assert v1_chunks_final == 0
