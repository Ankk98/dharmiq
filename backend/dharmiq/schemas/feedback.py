from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MessageFeedbackCreate(BaseModel):
    rating: Literal["up", "down"]
    reason: str | None = Field(default=None, max_length=500)


class MessageFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    message_id: uuid.UUID
    rating: str
    reason: str | None = None
    created_at: datetime
    updated_at: datetime
