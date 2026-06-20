from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings
from dharmiq.db.models.chats import ChatMessage, ChatRequest, ChatSession
from dharmiq.db.models.users import User
from dharmiq.llm.openrouter_client import OpenRouterClient


@dataclass
class GraphRuntime:
    db: AsyncSession
    settings: Settings
    client: OpenRouterClient
    user: User
    chat_session: ChatSession
    chat_request: ChatRequest
    history: list[ChatMessage]
    user_msg: ChatMessage
    new_messages: list[ChatMessage] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)

    @property
    def chat_request_id(self) -> uuid.UUID:
        return self.chat_request.id

    @property
    def model_name(self) -> str:
        return self.settings.openrouter.default_model

    def utcnow(self) -> datetime:
        return datetime.now(UTC)
