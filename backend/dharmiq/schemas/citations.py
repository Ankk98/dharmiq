from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal["corpus", "upload"]


class CitationRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    marker: int
    chunk_id: uuid.UUID
    source_type: SourceType
    document_id: uuid.UUID
    document_title: str
    section_label: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    quote_text: str | None = None
    quote_start_char: int | None = None
    quote_end_char: int | None = None
    canonical_url: str | None = None
