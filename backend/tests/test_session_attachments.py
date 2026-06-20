from __future__ import annotations

import uuid
from io import BytesIO
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from pgvector import Vector as PgVector
from pypdf import PdfWriter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import ChatSessionUpload
from dharmiq.db.models.uploads import UserUpload, UserUploadChunk
from dharmiq.db.session import get_session_factory
from dharmiq.llm.retrieval import retrieve_user_upload_chunks
from dharmiq.llm.embeddings import EmbeddingBackend


class _FixedEmbeddingBackend(EmbeddingBackend):
    @property
    def dimensions(self) -> int:
        return 384

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 384 for _ in texts]


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _unit_vector(seed: int) -> list[float]:
    vector = [0.0] * 384
    vector[seed % 384] = 1.0
    return vector


@pytest.fixture(autouse=True)
def _no_celery_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MagicMock()
    monkeypatch.setattr("dharmiq.api.routes.uploads.celery_app.send_task", mock)


@pytest.fixture(autouse=True)
async def _clean_tables() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM chat_session_uploads"))
        await db.execute(text("DELETE FROM user_upload_chunks"))
        await db.execute(text("DELETE FROM user_uploads"))
        await db.execute(text("DELETE FROM chat_sessions"))
        await db.commit()
    yield


async def _create_other_user_headers(client: AsyncClient) -> dict[str, str]:
    email = f"other-{uuid.uuid4()}@example.com"
    password = "securepassword123"
    await client.post("/api/auth/register", json={"email": email, "password": password})
    login = await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": password},
    )
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _seed_indexed_upload(db: AsyncSession, user_id: uuid.UUID) -> UserUpload:
    upload = UserUpload(
        user_id=user_id,
        original_filename="contract.pdf",
        file_path="/tmp/contract.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        content_hash=f"hash-{uuid.uuid4()}",
    )
    db.add(upload)
    await db.flush()
    db.add(
        UserUploadChunk(
            upload_id=upload.id,
            chunk_index=0,
            text="The employee may be terminated with 30 days notice.",
            page_start=1,
            page_end=1,
            embedding=PgVector(_unit_vector(0)),
        )
    )
    await db.commit()
    await db.refresh(upload)
    return upload


@pytest.mark.asyncio
async def test_upload_not_auto_attached(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()

    session_resp = await client.post(
        "/api/chat/sessions",
        headers=auth_headers,
        json={"title": "Contract review"},
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    upload_resp = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("contract.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert upload_resp.status_code == 201

    factory = get_session_factory()
    async with factory() as db:
        count = (
            await db.execute(
                select(func.count())
                .select_from(ChatSessionUpload)
                .where(ChatSessionUpload.session_id == uuid.UUID(session_id))
            )
        ).scalar_one()
        assert count == 0


@pytest.mark.asyncio
async def test_attach_enables_retrieval(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    session_resp = await client.post(
        "/api/chat/sessions",
        headers=auth_headers,
        json={"title": "Attach test"},
    )
    session_id = uuid.UUID(session_resp.json()["id"])
    user_id = uuid.UUID(session_resp.json()["user_id"])

    factory = get_session_factory()
    async with factory() as db:
        upload = await _seed_indexed_upload(db, user_id)

        unattached = await retrieve_user_upload_chunks(
            db,
            "termination notice period",
            user_id,
            attached_upload_ids=[],
            backend=_FixedEmbeddingBackend(),
        )
        assert unattached == []

        attach_resp = await client.post(
            f"/api/chat/sessions/{session_id}/attachments",
            headers=auth_headers,
            json={"upload_ids": [str(upload.id)]},
        )
        assert attach_resp.status_code == 200, attach_resp.text
        body = attach_resp.json()
        assert len(body) == 1
        assert body[0]["upload_id"] == str(upload.id)

        attached = await retrieve_user_upload_chunks(
            db,
            "termination notice period",
            user_id,
            attached_upload_ids=[upload.id],
            backend=_FixedEmbeddingBackend(),
        )
        assert len(attached) == 1


@pytest.mark.asyncio
async def test_detach_disables_retrieval(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    session_resp = await client.post(
        "/api/chat/sessions",
        headers=auth_headers,
        json={"title": "Detach test"},
    )
    session_id = uuid.UUID(session_resp.json()["id"])
    user_id = uuid.UUID(session_resp.json()["user_id"])

    factory = get_session_factory()
    async with factory() as db:
        upload = await _seed_indexed_upload(db, user_id)

    attach_resp = await client.post(
        f"/api/chat/sessions/{session_id}/attachments",
        headers=auth_headers,
        json={"upload_ids": [str(upload.id)]},
    )
    assert attach_resp.status_code == 200

    detach_resp = await client.delete(
        f"/api/chat/sessions/{session_id}/attachments/{upload.id}",
        headers=auth_headers,
    )
    assert detach_resp.status_code == 204

    async with factory() as db:
        attached = await retrieve_user_upload_chunks(
            db,
            "termination notice period",
            user_id,
            attached_upload_ids=[],
            backend=_FixedEmbeddingBackend(),
        )
        assert attached == []

        link_count = (
            await db.execute(
                select(func.count())
                .select_from(ChatSessionUpload)
                .where(
                    ChatSessionUpload.session_id == session_id,
                    ChatSessionUpload.upload_id == upload.id,
                )
            )
        ).scalar_one()
        assert link_count == 0


@pytest.mark.asyncio
async def test_attach_other_user_upload_403(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    other_headers = await _create_other_user_headers(client)

    session_resp = await client.post(
        "/api/chat/sessions",
        headers=auth_headers,
        json={"title": "Cross-user attach"},
    )
    session_id = session_resp.json()["id"]

    other_upload_resp = await client.post(
        "/api/uploads",
        headers=other_headers,
        files={"file": ("secret.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert other_upload_resp.status_code == 201
    other_upload_id = other_upload_resp.json()["id"]

    factory = get_session_factory()
    async with factory() as db:
        chunk = UserUploadChunk(
            upload_id=uuid.UUID(other_upload_id),
            chunk_index=0,
            text="Confidential clause.",
            page_start=1,
            page_end=1,
            embedding=PgVector(_unit_vector(1)),
        )
        db.add(chunk)
        await db.commit()

    attach_resp = await client.post(
        f"/api/chat/sessions/{session_id}/attachments",
        headers=auth_headers,
        json={"upload_ids": [other_upload_id]},
    )
    assert attach_resp.status_code == 403
