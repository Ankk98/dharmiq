from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.db.models.chats import ChatMessage, ChatRequest, MessageRole
from dharmiq.db.models.idempotency import IdempotencyKey

IDEMPOTENCY_TTL = timedelta(hours=24)


class IdempotencyOutcome(str, Enum):
    NEW = "new"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class IdempotencyResolution:
    outcome: IdempotencyOutcome
    chat_request_id: uuid.UUID | None = None


def parse_idempotency_key(header: str | None) -> str | None:
    if not header:
        return None
    stripped = header.strip()
    if not stripped:
        return None
    try:
        return str(uuid.UUID(stripped))
    except ValueError:
        return None


def compute_body_hash(*, content: str, force_answer: bool) -> str:
    payload = {
        "content": content.strip(),
        "force_answer": force_answer,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def resolve_idempotency(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    key: str,
    body_hash: str,
) -> IdempotencyResolution:
    now = datetime.now(UTC)
    result = await db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.key == key,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return IdempotencyResolution(outcome=IdempotencyOutcome.NEW)

    if row.expires_at <= now:
        await db.execute(
            delete(IdempotencyKey).where(IdempotencyKey.id == row.id)
        )
        await db.flush()
        return IdempotencyResolution(outcome=IdempotencyOutcome.NEW)

    if row.body_hash == body_hash:
        return IdempotencyResolution(
            outcome=IdempotencyOutcome.REPLAY,
            chat_request_id=row.chat_request_id,
        )

    return IdempotencyResolution(outcome=IdempotencyOutcome.CONFLICT)


async def store_idempotency_key(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    key: str,
    body_hash: str,
    chat_request: ChatRequest,
) -> None:
    now = datetime.now(UTC)
    db.add(
        IdempotencyKey(
            user_id=user_id,
            key=key,
            body_hash=body_hash,
            chat_request_id=chat_request.id,
            expires_at=now + IDEMPOTENCY_TTL,
        )
    )
    chat_request.idempotency_key = key
    await db.flush()


async def user_message_id_for_request(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    chat_request_id: uuid.UUID,
) -> uuid.UUID | None:
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == MessageRole.USER,
        )
    )
    request_id = str(chat_request_id)
    for message in result.scalars().all():
        metadata = message.message_metadata or {}
        if metadata.get("chat_request_id") == request_id:
            return message.id
    return None
