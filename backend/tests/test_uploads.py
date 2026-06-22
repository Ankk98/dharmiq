from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from pypdf import PdfWriter


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


@pytest.mark.asyncio
async def test_upload_pdf(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()

    response = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("employment_contract.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == "employment_contract.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["indexed"] is False
    assert body["processing_stage"] == "uploaded"
    assert body["chunk_count"] == 0
    assert body["processing_enqueued"] is True


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", "/tmp/dharmiq-test")
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.uploads.max_size_bytes = 16

    response = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("large.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_get_upload_returns_stage(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()

    created = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("contract.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert created.status_code == 201
    upload_id = created.json()["id"]

    fetched = await client.get(f"/api/uploads/{upload_id}", headers=auth_headers)
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["id"] == upload_id
    assert body["processing_stage"] == "uploaded"
    assert body["chunk_count"] == 0
    assert body["processing_error"] is None
    assert body["indexed"] is False


@pytest.mark.asyncio
async def test_list_and_delete_upload(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()

    created = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("contract.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert created.status_code == 201
    upload_id = created.json()["id"]

    listed = await client.get("/api/uploads", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == upload_id

    fetched = await client.get(f"/api/uploads/{upload_id}", headers=auth_headers)
    assert fetched.status_code == 200

    deleted = await client.delete(f"/api/uploads/{upload_id}", headers=auth_headers)
    assert deleted.status_code == 204

    listed_after = await client.get("/api/uploads", headers=auth_headers)
    assert listed_after.json() == []


@pytest.mark.asyncio
async def test_upload_limit_enforced(
    client: AsyncClient,
    auth_headers: dict[str, str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DHARMIQ_ROOT", str(tmp_path))
    from dharmiq.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    settings.uploads.max_assets_per_user = 1

    first = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("one.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/uploads",
        headers=auth_headers,
        files={"file": ("two.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert second.status_code == 409
