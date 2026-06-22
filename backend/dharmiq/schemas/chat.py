from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from dharmiq.db.models.chats import ChatRequestEventType, ChatRequestStatus, MessageRole
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


class SessionMessageCreate(BaseModel):
    content: str = Field(min_length=1)
    force_answer: bool = False
    role: MessageRole = MessageRole.USER
    metadata: dict[str, Any] | None = None


class SessionMessageEdit(BaseModel):
    content: str = Field(min_length=1)


class ChatRequestPendingResponse(BaseModel):
    chat_request_id: uuid.UUID
    user_message_id: uuid.UUID
    status: Literal["pending", "completed", "failed"] = "pending"


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    role: MessageRole
    content: str
    content_compressed: str | None = None
    compression_version: int | None = None
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
    clarifier_round: int = 0
    force_answer: bool = False
    stated_assumptions: list[str] | None = None
    progress_view: str | None = None


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


class ChatSessionUploadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    upload_id: uuid.UUID
    attached_at: datetime


class ChatSessionUploadAttachRequest(BaseModel):
    upload_ids: list[uuid.UUID] = Field(min_length=1)


class ChatRequestEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chat_request_id: uuid.UUID
    seq: int
    visibility: str
    event_type: ChatRequestEventType
    payload: dict[str, Any]
    created_at: datetime


class ContextSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    covers_message_ids: list[uuid.UUID]
    summary_text: str
    facts_json: dict[str, Any] | None = None
    created_at: datetime
