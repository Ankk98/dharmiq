from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from dharmiq.db.models.chats import ChatRequestStatus, MessageRole
from dharmiq.llm.retrieval import CitationRead


class ChatSessionCreate(BaseModel):
    title: str | None = None


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessageCreate(BaseModel):
    role: MessageRole = MessageRole.USER
    content: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    role: MessageRole
    content: str
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="message_metadata")
    created_at: datetime


class ChatPipelineRequest(BaseModel):
    session_id: uuid.UUID
    message: str = Field(min_length=1)


class ChatRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    status: ChatRequestStatus
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    llm_model: str | None
    total_tokens: int | None


class ChatPipelineResponse(BaseModel):
    chat_request_id: uuid.UUID
    status: ChatRequestStatus
    needs_clarification: bool
    followup_questions: list[str] = Field(default_factory=list)
    answer: str | None = None
    citations: list[CitationRead] = Field(default_factory=list)
    final_warning: str | None = None
    taking_longer_than_expected: bool = False
    messages: list[ChatMessageRead] = Field(default_factory=list)
    error_message: str | None = None
