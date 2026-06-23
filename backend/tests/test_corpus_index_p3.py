from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.config.settings import get_settings
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.models.statute_relationships import StatuteRelationship
from dharmiq.db.session import get_session_factory
from dharmiq.eval.tools.allowlist import (
    load_allowlist,
    resolve_allowlist_cli_arg,
    source_id_to_filename,
)
from dharmiq.eval.tools.build_manifest import build_manifest
from dharmiq.eval.tools.verify_corpus_index import (
    verify_corpus_index,
    write_corpus_index_report,
)
from dharmiq.ingestion.parser import PageText
from dharmiq.ingestion.pipeline import process_document, sync_corpus_documents
from dharmiq.ingestion.relationships import collect_relationship_edges, sync_statute_relationships
from dharmiq.llm.embeddings import EmbeddingBackend

CENTRAL_ALLOWLIST = (
    Path(__file__).resolve().parents[2] / "docs" / "plans" / "v0.6" / "central-corpus-allowlist.yaml"
)
FIXTURE_ALLOWLIST = Path(__file__).resolve().parent / "fixtures" / "mvp-allowlist-fixture.yaml"


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
async def _clean_corpus_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.execute(text("DELETE FROM statute_relationships"))
        await db.commit()
    yield


@pytest.mark.timeout(30)
def test_resolve_allowlist_central_alias() -> None:
    settings = get_settings()
    resolved = resolve_allowlist_cli_arg(
        "central",
        repo_root=settings.repo_root,
        default_allowlist_path=settings.corpus.default_allowlist_path,
    )
    assert resolved == CENTRAL_ALLOWLIST
    assert resolved.is_file()


@pytest.mark.timeout(30)
def test_central_allowlist_has_62_instruments_and_three_supersession_edges() -> None:
    instruments = load_allowlist(CENTRAL_ALLOWLIST)
    edges = collect_relationship_edges(instruments)
    assert len(instruments) == 62
    assert len(edges) >= 3
    assert ("IN-IPC-1860", "IN-BNS-2023", "superseded_by") in edges
    assert ("IN-CRPC-1973", "IN-BNSS-2023", "superseded_by") in edges
    assert ("IN-CPA-1986", "IN-CPA-2019", "superseded_by") in edges


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_verify_chunk_budget_exceeded(db: AsyncSession) -> None:
    document = SourceDocument(
        source_id="IN-CONSTITUTION-1949",
        title="The Constitution of India",
        doc_type="act",
        jurisdiction="central",
        content_hash="hash-constitution",
        file_path="/tmp/constitution.pdf",
    )
    db.add(document)
    await db.flush()
    for index in range(5):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                text=f"Chunk {index} about constitutional rights.",
            )
        )
    await db.commit()

    all_ok, report = await verify_corpus_index(
        db,
        allowlist_path=FIXTURE_ALLOWLIST,
        max_chunk_count=3,
    )
    assert all_ok is False
    assert report["chunk_budget_ok"] is False
    assert report["corpus_chunk_count"] == 5
    assert report["max_chunk_count"] == 3


@pytest.mark.asyncio
@pytest.mark.timeout(60)
async def test_verify_reports_missing_pdfs_when_corpus_dir_set(
    db: AsyncSession,
    tmp_path: Path,
) -> None:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    constitution_pdf = corpus_dir / source_id_to_filename("IN-CONSTITUTION-1949")
    _write_pdf(constitution_pdf)

    document = SourceDocument(
        source_id="IN-CONSTITUTION-1949",
        title="The Constitution of India",
        doc_type="act",
        jurisdiction="central",
        content_hash="hash-constitution",
        file_path=str(constitution_pdf),
    )
    db.add(document)
    await db.flush()
    db.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            text="Constitutional rights sample text.",
        )
    )
    await db.commit()

    all_ok, report = await verify_corpus_index(
        db,
        allowlist_path=FIXTURE_ALLOWLIST,
        corpus_dir=corpus_dir,
    )
    assert all_ok is False
    assert "IN-RTI-2005" in report["missing_pdf_source_ids"]
    assert "IN-CPA-2019" in report["missing_pdf_source_ids"]
    assert report["documents"][0]["pdf_on_disk"] is True


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_p3_manifest_sync_verify_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fixture-scale P3 flow: PDFs → manifest → sync → index → verify."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    instruments = load_allowlist(FIXTURE_ALLOWLIST)
    for instrument in instruments:
        _write_pdf(corpus_dir / source_id_to_filename(instrument.id))

    build_manifest(
        allowlist_path=FIXTURE_ALLOWLIST,
        corpus_dir=corpus_dir,
        write=True,
    )
    manifest_path = corpus_dir / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest) == 3

    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    settings.ingestion.corpus_dir = "corpus"

    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    parser = _StubParser()
    backend = _FixedEmbeddingBackend()

    async with factory() as db:
        sync_result = await sync_corpus_documents(db, settings=settings, enqueue=False)
        assert sync_result.created == 3

        documents = (
            await db.execute(select(SourceDocument).order_by(SourceDocument.source_id))
        ).scalars().all()
        for document in documents:
            await process_document(
                db,
                document.id,
                settings=settings,
                parser=parser,
                embedding_backend=backend,
            )

        relationship_count = await sync_statute_relationships(db, CENTRAL_ALLOWLIST)
        await db.commit()
        assert relationship_count >= 3

        total_edges = (
            await db.execute(select(func.count()).select_from(StatuteRelationship))
        ).scalar_one()
        assert total_edges >= 3

        all_ok, report = await verify_corpus_index(
            db,
            allowlist_path=FIXTURE_ALLOWLIST,
            corpus_dir=corpus_dir,
            max_chunk_count=settings.corpus.max_chunk_count,
        )
        assert all_ok is True
        assert report["indexed_document_count"] == 3
        assert report["corpus_chunk_count"] > 0
        assert report["chunk_budget_ok"] is True
        assert report["missing_pdf_source_ids"] == []

        for row in report["documents"]:
            assert row["pdf_on_disk"] is True

        indexed_docs = (
            await db.execute(
                select(SourceDocument).where(SourceDocument.source_id.in_(
                    [instrument.id for instrument in instruments]
                ))
            )
        ).scalars().all()
        assert len(indexed_docs) == 3
        for document in indexed_docs:
            assert document.indexed_at is not None
            assert document.doc_type == DocType.ACT


@pytest.mark.timeout(30)
def test_write_corpus_index_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    settings.eval.runs_dir = "data/eval/runs"

    report = {
        "indexed_document_count": 3,
        "corpus_chunk_count": 42,
        "chunk_budget_ok": True,
        "max_chunk_count": 250_000,
    }
    output_path = write_corpus_index_report(report, settings=settings)
    assert output_path.is_file()
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["corpus_chunk_count"] == 42
