"""Tests for document access API."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_corpus_document_metadata_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    missing_id = uuid.uuid4()
    response = await client.get(f"/api/docs/{missing_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_download_corpus_document_file(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    from pgvector import Vector as PgVector

    from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
    from dharmiq.db.session import get_session_factory
    from tests.vector_helpers import unit_vector

    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test content")

    factory = get_session_factory()
    async with factory() as db:
        document = SourceDocument(
            source_id=f"docs-api-{uuid.uuid4()}",
            title="Sample Act",
            doc_type=DocType.ACT,
            jurisdiction="central",
            content_hash="hash-docs-api",
            file_path=str(pdf_path),
        )
        db.add(document)
        await db.flush()
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=0,
                text="Sample section text",
                page_start=1,
                page_end=1,
                embedding=PgVector(unit_vector(0)),
            )
        )
        await db.commit()
        document_id = document.id

    meta = await client.get(f"/api/docs/{document_id}", headers=auth_headers)
    assert meta.status_code == 200
    assert meta.json()["title"] == "Sample Act"

    file_response = await client.get(
        f"/api/docs/{document_id}/file",
        headers=auth_headers,
    )
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "application/pdf"
    assert b"%PDF" in file_response.content
