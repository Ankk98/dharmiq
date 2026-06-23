from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from dharmiq.db.models.documents import DocType, InstrumentStatus
from dharmiq.llm.retrieval import SourceType


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: SourceType
    title: str
    doc_type: DocType | None = None
    jurisdiction: str | None = None
    enactment_date: date | None = None
    enforcement_date: date | None = None
    status: InstrumentStatus | None = None
    superseded_by_source_id: str | None = None
    canonical_url: str | None = None
    mime_type: str
    file_path: str
    created_at: datetime | None = None
