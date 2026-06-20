from __future__ import annotations

import re
import uuid
from pathlib import Path

from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import UploadError
from dharmiq.core.logging import get_logger

logger = get_logger(__name__)

ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/tiff",
        "text/markdown",
        "text/x-markdown",
    }
)

ALLOWED_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".md", ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
)

_FILENAME_UNSAFE = re.compile(r"[^\w.\- ]+")


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    cleaned = _FILENAME_UNSAFE.sub("_", name)
    return cleaned or "upload"


def validate_upload_file(
    *,
    filename: str,
    mime_type: str | None,
    size_bytes: int,
    settings: Settings | None = None,
) -> str:
    cfg = settings or get_settings()
    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise UploadError(
            "Unsupported file type",
            details={"filename": safe_name, "extension": extension},
        )

    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        raise UploadError(
            "Unsupported MIME type",
            details={"filename": safe_name, "mime_type": mime_type},
        )

    if size_bytes <= 0:
        raise UploadError("Empty file", details={"filename": safe_name})

    if size_bytes > cfg.uploads.max_size_bytes:
        raise UploadError(
            "File exceeds size limit",
            details={
                "filename": safe_name,
                "size_bytes": size_bytes,
                "max_size_bytes": cfg.uploads.max_size_bytes,
            },
        )

    return safe_name


def user_raw_directory(user_id: uuid.UUID, settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    return cfg.uploads.user_raw_dir(cfg.repo_root, user_id)


def save_user_upload_file(
    user_id: uuid.UUID,
    upload_id: uuid.UUID,
    filename: str,
    content: bytes,
    *,
    settings: Settings | None = None,
) -> Path:
    cfg = settings or get_settings()
    directory = user_raw_directory(user_id, cfg)
    directory.mkdir(parents=True, exist_ok=True)

    destination = directory / f"{upload_id}_{filename}"
    destination.write_bytes(content)
    logger.info(
        "upload_file_saved",
        user_id=str(user_id),
        upload_id=str(upload_id),
        path=str(destination),
        size_bytes=len(content),
    )
    return destination.resolve()


def resolve_upload_path(file_path: str, settings: Settings | None = None) -> Path:
    cfg = settings or get_settings()
    path = Path(file_path)
    if path.is_absolute():
        return path
    return (cfg.repo_root / path).resolve()
