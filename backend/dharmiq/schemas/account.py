from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AccountDeleteRequest(BaseModel):
    email: str
    password: str


class AccountExportUser(BaseModel):
    id: uuid.UUID
    email: str
    created_at: datetime


class AccountExportSession(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class AccountExportMessage(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    metadata: dict[str, Any] | None = None
    created_at: datetime


class AccountExportUpload(BaseModel):
    id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    processing_stage: str
    chunk_count: int
    created_at: datetime


class AccountExportPayload(BaseModel):
    exported_at: datetime
    user: AccountExportUser
    sessions: list[AccountExportSession]
    messages: list[AccountExportMessage]
    uploads: list[AccountExportUpload]
