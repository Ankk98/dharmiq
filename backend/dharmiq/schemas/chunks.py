from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChunkListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    chunk_index: int
    preview: str
    page_start: int | None = None
    page_end: int | None = None
    section_label: str | None = None


class ChunkListResponse(BaseModel):
    document_id: uuid.UUID
    source_type: Literal["corpus", "upload"]
    chunks: list[ChunkListItem]


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    source_type: Literal["corpus", "upload"]
    text: str
    context_text: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_label: str | None = None
