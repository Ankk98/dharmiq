from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from dharmiq.db.models.documents import DocType
from dharmiq.llm.retrieval import SourceType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    title: str
    doc_type: DocType | None = None
    jurisdiction: str | None = None
    enactment_date: date | None = None
    mime_type: str
    file_path: str
    created_at: datetime | None = None
