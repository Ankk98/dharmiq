from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserUploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    mime_type: str
    size_bytes: int
    content_hash: str
    created_at: datetime
    deleted_at: datetime | None = None
    processing_stage: str = "uploaded"
    chunk_count: int = 0
    processing_error: str | None = None
    indexed: bool = Field(default=False)


class UserUploadCreateResponse(UserUploadRead):
    processing_enqueued: bool = True
