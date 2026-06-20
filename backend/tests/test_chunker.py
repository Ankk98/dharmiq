from __future__ import annotations

import uuid

import pytest
from pgvector import Vector as PgVector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.config.settings import get_settings
from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.session import get_session_factory
from dharmiq.ingestion.chunker import (
    CHUNK_SCHEMA_V02,
    DetectedSection,
    chunk_section,
    detect_sections,
    split_section_into_chunks,
)
from dharmiq.ingestion.context_text import build_context_text
from dharmiq.ingestion.tokens import count_tokens
from dharmiq.ingestion.parser import PageText
from dharmiq.llm.embeddings import EmbeddingBackend
from dharmiq.llm.retrieval import retrieve_multi_query
from dharmiq.retrieval.hybrid import hydrate_parent_texts


def test_detect_sections_finds_statute_headings() -> None:
    pages = [
        PageText(
            page_number=1,
            text=(
                "Section 1. Short title.\n"
                "This Act may be called the Test Act.\n\n"
                "Section 2. Definitions.\n"
                "In this Act, unless the context otherwise requires."
            ),
        )
    ]

    sections = detect_sections(pages)

    assert len(sections) == 2
    assert sections[0].label.startswith("Section 1")
    assert sections[0].number == "1"
    assert sections[1].label.startswith("Section 2")
    assert sections[1].number == "2"


def test_split_section_into_chunks_respects_max_size() -> None:
    section = DetectedSection(
        label="Section 10. Long section",
        number="10",
        start_page=1,
        end_page=2,
        text="word " * 1200,
    )

    chunks = split_section_into_chunks(
        section,
        min_chars=200,
        max_chars=500,
        overlap_chars=50,
        start_index=0,
    )

    assert len(chunks) > 1
    assert all(len(chunk.text) <= 500 for chunk in chunks)
    assert chunks[0].section_number == "10"


def test_section_yields_parent_and_children() -> None:
    section = DetectedSection(
        label="Section 41. Arrest without warrant",
        number="41",
        start_page=41,
        end_page=41,
        text=(
            "Section 41. Arrest without warrant.\n\n"
            "Any police officer may arrest without an order from a Magistrate and without a warrant.\n\n"
            "The officer must have reason to believe the person committed a cognizable offence."
        ),
    )

    group = chunk_section(section)

    assert group.parent.chunk_type == "parent"
    assert len(group.children) >= 1
    assert all(child.chunk_type == "child" for child in group.children)
    assert group.parent.text.startswith("Section 41")


def test_child_chunk_target_uses_token_counts() -> None:
    settings = get_settings()
    target = settings.ingestion.child_chunk_target_tokens
    long_paragraph = "statute " * 400
    section = DetectedSection(
        label="Section 99. Token split",
        number="99",
        start_page=1,
        end_page=1,
        text=f"Section 99. Token split.\n\n{long_paragraph}",
    )

    group = chunk_section(section, settings=settings)

    assert len(group.children) > 1
    assert all(count_tokens(child.text) <= target * 2 for child in group.children)


def test_context_text_shorter_than_full() -> None:
    settings = get_settings()
    long_body = "Detailed statutory language. " * 500
    section = DetectedSection(
        label="Section 5. Example",
        number="5",
        start_page=1,
        end_page=1,
        text=f"Section 5. Example.\n\n{long_body}",
    )

    context = build_context_text(section.text, section_label=section.label, settings=settings)

    assert count_tokens(context) <= settings.ingestion.context_text_max_tokens
    assert count_tokens(context) < count_tokens(section.text)
    assert context.startswith("Section 5")


class _FixedEmbeddingBackend(EmbeddingBackend):
    def __init__(self, *, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self._dimensions for _ in texts]


@pytest.fixture(autouse=True)
async def _clean_chunk_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM document_chunks"))
        await db.execute(text("DELETE FROM document_sections"))
        await db.execute(text("DELETE FROM source_documents"))
        await db.commit()
    yield


async def _seed_parent_child_document(db: AsyncSession) -> tuple[DocumentChunk, DocumentChunk]:
    document = SourceDocument(
        source_id=f"parent-child-{uuid.uuid4()}",
        title="Code of Criminal Procedure, 1973",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash="hash-parent-child",
        file_path="/tmp/crpc.pdf",
    )
    db.add(document)
    await db.flush()

    parent_text = (
        "Section 41 CrPC — When police may arrest without warrant.\n\n"
        "Any police officer may without an order from a Magistrate and without a warrant, "
        "arrest any person who has been concerned in any cognizable offence."
    )
    child_text = "Any police officer may without an order from a Magistrate arrest any person."

    parent = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text=parent_text,
        context_text=build_context_text(parent_text, section_label="Section 41 CrPC"),
        chunk_metadata={
            "schema_version": CHUNK_SCHEMA_V02,
            "chunk_type": "parent",
            "section_number": "41",
        },
        page_start=41,
        page_end=41,
        embedding=None,
    )
    db.add(parent)
    await db.flush()

    child = DocumentChunk(
        document_id=document.id,
        chunk_index=1,
        text=child_text,
        context_text=build_context_text(child_text, section_label="Section 41 CrPC"),
        parent_chunk_id=parent.id,
        chunk_metadata={
            "schema_version": CHUNK_SCHEMA_V02,
            "chunk_type": "child",
            "section_number": "41",
        },
        page_start=41,
        page_end=41,
        embedding=PgVector([0.1] * 384),
    )
    db.add(child)
    await db.commit()
    await db.refresh(parent)
    await db.refresh(child)
    return parent, child


@pytest.mark.asyncio
async def test_child_points_to_parent() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()

    async with factory() as db:
        parent, child = await _seed_parent_child_document(db)
        row = await db.get(DocumentChunk, child.id)

    assert row is not None
    assert row.parent_chunk_id == parent.id


@pytest.mark.asyncio
async def test_search_vector_populated() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()

    async with factory() as db:
        _, child = await _seed_parent_child_document(db)
        result = (
            await db.execute(
                text("SELECT search_vector IS NOT NULL AS populated FROM document_chunks WHERE id = :id"),
                {"id": child.id},
            )
        ).scalar_one()

    assert result is True


@pytest.mark.asyncio
async def test_retrieval_returns_parent_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.rerank_helpers import mock_rerank

    mock_rerank(monkeypatch)
    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    backend = _FixedEmbeddingBackend()

    async with factory() as db:
        parent, child = await _seed_parent_child_document(db)
        monkeypatch.setattr("dharmiq.llm.retrieval.get_embedding_backend", lambda: backend)

        result = await retrieve_multi_query(
            db,
            ["Section 41 CrPC arrest without warrant"],
            uuid.uuid4(),
            rerank_query="Section 41 CrPC arrest without warrant",
            backend=backend,
        )

    assert result.chunks
    assert result.chunks[0].chunk_id == child.id
    assert result.chunks[0].text == parent.text


@pytest.mark.asyncio
async def test_hydrate_parent_texts_swaps_body() -> None:
    factory: async_sessionmaker[AsyncSession] = get_session_factory()

    async with factory() as db:
        parent, child = await _seed_parent_child_document(db)
        from dharmiq.llm.retrieval import RetrievedChunk

        chunks = [
            RetrievedChunk(
                chunk_id=child.id,
                source_type="corpus",
                document_id=child.document_id,
                document_title="Code of Criminal Procedure, 1973",
                text=child.text,
                score=0.9,
                chunk_index=child.chunk_index,
                page_start=child.page_start,
                page_end=child.page_end,
            )
        ]
        hydrated = await hydrate_parent_texts(db, chunks)

    assert hydrated[0].text == parent.text
    assert hydrated[0].chunk_id == child.id
