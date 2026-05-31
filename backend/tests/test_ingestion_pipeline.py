from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.db.models.documents import SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.ingestion.parser import PageText
from dharmiq.ingestion.pipeline import process_document, sync_corpus_documents
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


def _write_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


@pytest.fixture(autouse=True)
async def _clean_corpus() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


@pytest.mark.asyncio
async def test_sync_skips_unchanged_documents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    async with factory() as db:
        first = await sync_corpus_documents(db, settings=settings, enqueue=False)
        assert first.created == 1
        assert first.skipped == 0

        document = (
            await db.execute(select(SourceDocument).where(SourceDocument.source_id == "sample_act"))
        ).scalar_one()
        document.indexed_at = datetime.now(UTC)
        await db.commit()

        second = await sync_corpus_documents(db, settings=settings, enqueue=False)
        assert second.created == 0
        assert second.skipped == 1


@pytest.mark.asyncio
async def test_sync_creates_new_version_when_hash_changes(
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

    async with factory() as db:
        await sync_corpus_documents(db, settings=settings, enqueue=False)

        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        with pdf_path.open("wb") as handle:
            writer.write(handle)

        result = await sync_corpus_documents(db, settings=settings, enqueue=False)
        assert result.updated == 1

        rows = (
            await db.execute(
                select(SourceDocument)
                .where(SourceDocument.source_id == "sample_act")
                .order_by(SourceDocument.version)
            )
        ).scalars().all()
        assert len(rows) == 2
        assert rows[0].version == 1
        assert rows[1].version == 2
        assert rows[0].content_hash != rows[1].content_hash


@pytest.mark.asyncio
async def test_process_document_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        document_id = (
            await db.execute(select(SourceDocument.id).where(SourceDocument.source_id == "sample_act"))
        ).scalar_one()

        first_count = await process_document(
            db,
            document_id,
            settings=settings,
            parser=parser,
            embedding_backend=backend,
        )
        second_count = await process_document(
            db,
            document_id,
            settings=settings,
            parser=parser,
            embedding_backend=backend,
        )

        assert first_count == second_count
        assert first_count >= 2

        document = await db.get(SourceDocument, document_id)
        assert document is not None
        assert document.indexed_at is not None

        chunk_rows = (
            await db.execute(
                text("SELECT COUNT(*) FROM document_chunks WHERE document_id = :id"),
                {"id": document_id},
            )
        ).scalar_one()
        assert chunk_rows == first_count
