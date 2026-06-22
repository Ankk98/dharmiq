"""Tests for document chunk API."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from pgvector import Vector as PgVector
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.documents import DocType, DocumentChunk, SourceDocument
from dharmiq.db.models.uploads import ProcessingStage, UserUpload, UserUploadChunk
from dharmiq.db.session import get_session_factory
from tests.test_session_attachments import _create_other_user_headers
from tests.vector_helpers import unit_vector


async def _seed_corpus_chunk(db: AsyncSession) -> tuple[SourceDocument, DocumentChunk]:
    document = SourceDocument(
        source_id=f"chunks-api-{uuid.uuid4()}",
        title="Sample Act",
        doc_type=DocType.ACT,
        jurisdiction="central",
        content_hash=f"hash-{uuid.uuid4()}",
        file_path="/tmp/sample-act.pdf",
    )
    db.add(document)
    await db.flush()

    parent = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="Parent chunk text that should not appear in the list.",
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(0)),
    )
    db.add(parent)
    await db.flush()

    child = DocumentChunk(
        document_id=document.id,
        chunk_index=0,
        text="The employee may be terminated with 30 days notice.",
        parent_chunk_id=parent.id,
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(1)),
    )
    db.add(child)
    await db.commit()
    await db.refresh(document)
    await db.refresh(child)
    return document, child


async def _seed_upload_chunk(db: AsyncSession, user_id: uuid.UUID) -> tuple[UserUpload, UserUploadChunk]:
    upload = UserUpload(
        user_id=user_id,
        original_filename="contract.pdf",
        file_path="/tmp/contract.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        content_hash=f"hash-{uuid.uuid4()}",
        processing_stage=ProcessingStage.READY.value,
        chunk_count=1,
    )
    db.add(upload)
    await db.flush()

    chunk = UserUploadChunk(
        upload_id=upload.id,
        chunk_index=0,
        text="The employee may be terminated with 30 days notice.",
        page_start=1,
        page_end=1,
        embedding=PgVector(unit_vector(2)),
    )
    db.add(chunk)
    await db.commit()
    await db.refresh(upload)
    await db.refresh(chunk)
    return upload, chunk


async def _current_user_id(auth_headers: dict[str, str], client: AsyncClient) -> uuid.UUID:
    response = await client.get("/api/users/me", headers=auth_headers)
    assert response.status_code == 200, response.text
    return uuid.UUID(response.json()["id"])


@pytest.mark.asyncio
async def test_list_upload_chunks_owned(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    user_id = await _current_user_id(auth_headers, client)
    factory = get_session_factory()
    async with factory() as db:
        upload, chunk = await _seed_upload_chunk(db, user_id)

    response = await client.get(
        f"/api/docs/{upload.id}/chunks?source_type=upload",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_id"] == str(upload.id)
    assert body["source_type"] == "upload"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["chunk_id"] == str(chunk.id)
    assert "terminated" in body["chunks"][0]["preview"]

    other_headers = await _create_other_user_headers(client)
    denied = await client.get(
        f"/api/docs/{upload.id}/chunks?source_type=upload",
        headers=other_headers,
    )
    assert denied.status_code == 404


@pytest.mark.asyncio
async def test_get_chunk_text(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    user_id = await _current_user_id(auth_headers, client)
    factory = get_session_factory()
    async with factory() as db:
        upload, chunk = await _seed_upload_chunk(db, user_id)

    response = await client.get(
        f"/api/docs/{upload.id}/chunks/{chunk.id}?source_type=upload",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "The employee may be terminated with 30 days notice."
    assert body["chunk_id"] == str(chunk.id)


@pytest.mark.asyncio
async def test_corpus_chunks_no_user_filter(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    factory = get_session_factory()
    async with factory() as db:
        document, child = await _seed_corpus_chunk(db)

    owner_response = await client.get(
        f"/api/docs/{document.id}/chunks?source_type=corpus",
        headers=auth_headers,
    )
    assert owner_response.status_code == 200, owner_response.text
    owner_body = owner_response.json()
    assert len(owner_body["chunks"]) == 1
    assert owner_body["chunks"][0]["chunk_id"] == str(child.id)
    assert "Parent chunk" not in owner_body["chunks"][0]["preview"]

    other_headers = await _create_other_user_headers(client)
    other_response = await client.get(
        f"/api/docs/{document.id}/chunks?source_type=corpus",
        headers=other_headers,
    )
    assert other_response.status_code == 200, other_response.text
    assert other_response.json()["chunks"][0]["chunk_id"] == str(child.id)

    chunk_response = await client.get(
        f"/api/docs/{document.id}/chunks/{child.id}?source_type=corpus",
        headers=other_headers,
    )
    assert chunk_response.status_code == 200
    assert chunk_response.json()["text"] == child.text
