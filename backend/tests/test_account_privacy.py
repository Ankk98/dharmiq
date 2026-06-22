from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import ChatMessage, ChatSession
from dharmiq.db.models.users import User


@pytest.fixture(autouse=True)
def _no_celery_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = MagicMock()
    monkeypatch.setattr("dharmiq.api.routes.uploads.celery_app.send_task", mock)


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


async def _register_and_login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    register = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    assert register.status_code == 201, register.text

    login = await client.post(
        "/api/auth/jwt/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_export_contains_sessions_messages(
    client: AsyncClient,
    unique_email: str,
) -> None:
    password = "securepassword123"
    headers = await _register_and_login(client, unique_email, password)

    create = await client.post("/api/chat/sessions", json={"title": "Rights chat"}, headers=headers)
    assert create.status_code == 201
    session_id = create.json()["id"]

    append = await client.post(
        f"/api/chat/sessions/{session_id}/messages",
        json={"role": "user", "content": "What are my rights?"},
        headers=headers,
    )
    assert append.status_code == 201
    message_id = append.json()["id"]

    response = await client.get("/api/account/export", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment" in response.headers.get("content-disposition", "")

    payload = response.json()
    assert "exported_at" in payload
    assert payload["user"]["email"] == unique_email
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["id"] == session_id
    assert payload["sessions"][0]["title"] == "Rights chat"
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["id"] == message_id
    assert payload["messages"][0]["session_id"] == session_id
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "What are my rights?"
    assert "uploads" in payload


@pytest.mark.asyncio
async def test_export_no_file_bytes(
    client: AsyncClient,
    unique_email: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "securepassword123"
    headers = await _register_and_login(client, unique_email, password)

    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()

    upload = await client.post(
        "/api/uploads",
        headers=headers,
        files={"file": ("contract.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text

    response = await client.get("/api/account/export", headers=headers)
    assert response.status_code == 200
    raw = response.text
    assert "file_path" not in raw
    assert "file_bytes" not in raw
    assert "embedding" not in raw

    payload = response.json()
    assert len(payload["uploads"]) == 1
    upload_row = payload["uploads"][0]
    assert set(upload_row.keys()) == {
        "id",
        "original_filename",
        "mime_type",
        "size_bytes",
        "content_hash",
        "processing_stage",
        "chunk_count",
        "created_at",
    }


@pytest.mark.asyncio
async def test_delete_wrong_email_409(client: AsyncClient, unique_email: str) -> None:
    password = "securepassword123"
    headers = await _register_and_login(client, unique_email, password)

    response = await client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"email": f"other-{uuid.uuid4()}@example.com", "password": password},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Email does not match"


@pytest.mark.asyncio
async def test_delete_cascades(
    client: AsyncClient,
    db: AsyncSession,
    unique_email: str,
) -> None:
    password = "securepassword123"
    headers = await _register_and_login(client, unique_email, password)

    me = await client.get("/api/users/me", headers=headers)
    user_id = uuid.UUID(me.json()["id"])

    create = await client.post("/api/chat/sessions", json={"title": "To delete"}, headers=headers)
    session_id = uuid.UUID(create.json()["id"])

    await client.post(
        f"/api/chat/sessions/{create.json()['id']}/messages",
        json={"role": "user", "content": "Delete me"},
        headers=headers,
    )

    delete = await client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"email": unique_email, "password": password},
    )
    assert delete.status_code == 204, delete.text

    user_count = await db.scalar(select(func.count()).select_from(User).where(User.id == user_id))
    session_count = await db.scalar(
        select(func.count()).select_from(ChatSession).where(ChatSession.id == session_id)
    )
    message_count = await db.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.user_id == user_id)
    )
    assert user_count == 0
    assert session_count == 0
    assert message_count == 0

    login = await client.post(
        "/api/auth/jwt/login",
        data={"username": unique_email, "password": password},
    )
    assert login.status_code == 400


@pytest.mark.asyncio
async def test_delete_removes_upload_dir(
    client: AsyncClient,
    unique_email: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password = "securepassword123"
    headers = await _register_and_login(client, unique_email, password)

    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    upload = await client.post(
        "/api/uploads",
        headers=headers,
        files={"file": ("contract.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    upload_id = uuid.UUID(upload.json()["id"])

    me = await client.get("/api/users/me", headers=headers)
    user_id = uuid.UUID(me.json()["id"])
    uploads_dir = settings.uploads.resolve_uploads_dir(settings.repo_root) / str(user_id)
    assert uploads_dir.exists()

    delete = await client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"email": unique_email, "password": password},
    )
    assert delete.status_code == 204, delete.text
    assert not uploads_dir.exists()

    listing = await client.get("/api/uploads", headers=headers)
    assert listing.status_code == 401

    uploads_left = await client.get(
        f"/api/uploads/{upload_id}",
        headers=headers,
    )
    assert uploads_left.status_code == 401
