from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from dharmiq.db.models.uploads import UserUploadChunk
from dharmiq.db.models.users import User
from dharmiq.db.session import get_session_factory
from dharmiq.ingestion.parser import PageText
from dharmiq.ingestion.upload_pipeline import create_user_upload, process_user_upload
from dharmiq.llm.embeddings import EmbeddingBackend


class _FixedEmbeddingBackend(EmbeddingBackend):
    def __init__(self, *, dimensions: int = 384) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self._dimensions for _ in texts]


class _StubParser:
    def extract_pages(self, file_path: Path) -> list[PageText]:
        return [
            PageText(
                page_number=1,
                text="Section 1. Notice period.\nThe employee is entitled to thirty days notice.",
            )
        ]


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
async def _clean_uploads() -> None:
    factory = get_session_factory()
    async with factory() as db:
        await db.execute(text("DELETE FROM user_upload_chunks"))
        await db.execute(text("DELETE FROM user_uploads"))
        await db.commit()
    yield


async def _create_user(db: AsyncSession) -> User:
    user = User(
        email=f"upload-{uuid.uuid4()}@example.com",
        hashed_password="test",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_process_user_upload_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))

    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    content = _pdf_bytes()

    factory: async_sessionmaker[AsyncSession] = get_session_factory()
    parser = _StubParser()
    backend = _FixedEmbeddingBackend()

    async with factory() as db:
        user = await _create_user(db)
        upload = await create_user_upload(
            db,
            user_id=user.id,
            filename="contract.pdf",
            mime_type="application/pdf",
            content=content,
            settings=settings,
        )

        first = await process_user_upload(
            db,
            upload.id,
            settings=settings,
            pdf_parser=parser,
            embedding_backend=backend,
        )
        second = await process_user_upload(
            db,
            upload.id,
            settings=settings,
            pdf_parser=parser,
            embedding_backend=backend,
        )

        assert first == second
        assert first >= 1

        chunk_count = (
            await db.execute(
                select(UserUploadChunk).where(UserUploadChunk.upload_id == upload.id)
            )
        ).scalars().all()
        assert len(chunk_count) == first
