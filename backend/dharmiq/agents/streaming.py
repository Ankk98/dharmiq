from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.db.models.chats import (
    ChatRequest,
    ChatRequestEvent,
    ChatRequestEventType,
    ChatRequestStatus,
    EventVisibility,
)
from dharmiq.db.models.users import User

NODE_PROGRESS_LABELS: dict[str, str] = {
    "input_guard": "Checking your question…",
    "clarifier": "Understanding your question…",
    "query_rewriter": "Preparing search…",
    "retrieve": "Searching laws…",
    "answerer": "Drafting answer…",
    "validator": "Checking answer…",
    "finalizer": "Finalizing answer…",
}


def seq_key(chat_request_id: uuid.UUID) -> str:
    return f"chat:req:{chat_request_id}:seq"


def pubsub_channel(chat_request_id: uuid.UUID) -> str:
    return f"chat:request:{chat_request_id}"


def sse_event_name(db_event_type: ChatRequestEventType) -> str:
    if db_event_type in {ChatRequestEventType.STEP_START, ChatRequestEventType.STEP_END}:
        return "progress"
    if db_event_type == ChatRequestEventType.ERROR:
        return "error"
    if db_event_type == ChatRequestEventType.DONE:
        return "done"
    return db_event_type.value


@dataclass(frozen=True)
class StreamEvent:
    seq: int
    sse_event: str
    payload: dict[str, Any]

    def to_sse(self) -> str:
        return f"event: {self.sse_event}\ndata: {json.dumps(self.payload)}\n\n"


class ProgressEmitter:
    def __init__(
        self,
        db: AsyncSession,
        chat_request_id: uuid.UUID,
        *,
        redis_client: aioredis.Redis | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.db = db
        self.chat_request_id = chat_request_id
        self._redis = redis_client
        self._owns_redis = redis_client is None
        self._settings = settings or get_settings()

    async def _redis_client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._settings.redis.url,
                decode_responses=True,
                single_connection_client=True,
            )
        return self._redis

    async def close(self) -> None:
        if self._owns_redis and self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def next_seq(self) -> int:
        redis_client = await self._redis_client()
        return int(await redis_client.incr(seq_key(self.chat_request_id)))

    async def emit(
        self,
        *,
        event_type: ChatRequestEventType,
        payload: dict[str, Any],
        visibility: EventVisibility = EventVisibility.CONCISE,
    ) -> StreamEvent:
        seq = await self.next_seq()
        payload_with_seq = {"seq": seq, "visibility": visibility.value, **payload}

        event = ChatRequestEvent(
            chat_request_id=self.chat_request_id,
            seq=seq,
            visibility=visibility.value,
            event_type=event_type,
            payload=payload_with_seq,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.commit()

        stream_event = StreamEvent(
            seq=seq,
            sse_event=sse_event_name(event_type),
            payload=payload_with_seq,
        )
        await self._publish(stream_event)
        return stream_event

    async def emit_step_start(self, step_id: str, *, label: str | None = None) -> StreamEvent:
        return await self.emit(
            event_type=ChatRequestEventType.STEP_START,
            payload={
                "step_id": step_id,
                "label": label or NODE_PROGRESS_LABELS.get(step_id, step_id),
                "status": "running",
            },
        )

    async def emit_step_end(self, step_id: str, *, label: str | None = None) -> StreamEvent:
        return await self.emit(
            event_type=ChatRequestEventType.STEP_END,
            payload={
                "step_id": step_id,
                "label": label or NODE_PROGRESS_LABELS.get(step_id, step_id),
                "status": "completed",
            },
        )

    async def emit_error(self, *, code: str, message: str) -> StreamEvent:
        return await self.emit(
            event_type=ChatRequestEventType.ERROR,
            payload={"code": code, "message": message},
        )

    async def emit_done(
        self,
        *,
        message_id: uuid.UUID | None,
        status: ChatRequestStatus,
    ) -> StreamEvent:
        payload: dict[str, Any] = {"status": status.value}
        if message_id is not None:
            payload["message_id"] = str(message_id)
        return await self.emit(event_type=ChatRequestEventType.DONE, payload=payload)

    async def _publish(self, stream_event: StreamEvent) -> None:
        redis_client = await self._redis_client()
        message = json.dumps(
            {
                "seq": stream_event.seq,
                "sse_event": stream_event.sse_event,
                "payload": stream_event.payload,
            }
        )
        await redis_client.publish(pubsub_channel(self.chat_request_id), message)


def event_to_stream(event: ChatRequestEvent) -> StreamEvent:
    return StreamEvent(
        seq=event.seq,
        sse_event=sse_event_name(event.event_type),
        payload=event.payload,
    )


def filter_event_for_user(
    stream_event: StreamEvent,
    user: User,
    settings: Settings | None = None,
) -> StreamEvent | None:
    visibility = stream_event.payload.get("visibility")
    if visibility != EventVisibility.DEBUG.value:
        return stream_event

    cfg = settings or get_settings()
    if user.is_superuser and cfg.agent_graph.debug_progress:
        return stream_event
    return None


async def load_events_after_seq(
    db: AsyncSession,
    chat_request_id: uuid.UUID,
    after_seq: int,
) -> list[ChatRequestEvent]:
    result = await db.execute(
        select(ChatRequestEvent)
        .where(
            ChatRequestEvent.chat_request_id == chat_request_id,
            ChatRequestEvent.seq > after_seq,
        )
        .order_by(ChatRequestEvent.seq.asc())
    )
    return list(result.scalars().all())


async def stream_chat_request_events(
    db: AsyncSession,
    chat_request: ChatRequest,
    user: User,
    *,
    after_seq: int = 0,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    cfg = settings or get_settings()
    redis_client = aioredis.from_url(
        cfg.redis.url,
        decode_responses=True,
        single_connection_client=True,
    )
    channel = pubsub_channel(chat_request.id)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)

    live_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    stop_event = asyncio.Event()

    async def _listen() -> None:
        try:
            async for message in pubsub.listen():
                if stop_event.is_set():
                    break
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if not data:
                    continue
                await live_queue.put(json.loads(data))
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    listener = asyncio.create_task(_listen())

    seen_seqs: set[int] = set()
    terminal_received = False

    def _yield_if_visible(stream_event: StreamEvent) -> str | None:
        filtered = filter_event_for_user(stream_event, user, cfg)
        if filtered is None:
            return None
        seen_seqs.add(filtered.seq)
        return filtered.to_sse()

    try:
        for db_event in await load_events_after_seq(db, chat_request.id, after_seq):
            stream_event = event_to_stream(db_event)
            if sse := _yield_if_visible(stream_event):
                yield sse
            if stream_event.sse_event in {"done", "error"}:
                terminal_received = True

        if terminal_received:
            return

        refreshed = await db.get(ChatRequest, chat_request.id)
        if refreshed and refreshed.status in {
            ChatRequestStatus.COMPLETED,
            ChatRequestStatus.FAILED,
        }:
            return

        while not terminal_received:
            try:
                live_message = await asyncio.wait_for(live_queue.get(), timeout=1.0)
            except TimeoutError:
                refreshed = await db.get(ChatRequest, chat_request.id)
                if refreshed and refreshed.status in {
                    ChatRequestStatus.COMPLETED,
                    ChatRequestStatus.FAILED,
                }:
                    for db_event in await load_events_after_seq(db, chat_request.id, after_seq):
                        if db_event.seq in seen_seqs:
                            continue
                        stream_event = event_to_stream(db_event)
                        if sse := _yield_if_visible(stream_event):
                            yield sse
                        if stream_event.sse_event in {"done", "error"}:
                            terminal_received = True
                            break
                continue

            seq = int(live_message["seq"])
            if seq in seen_seqs:
                continue

            stream_event = StreamEvent(
                seq=seq,
                sse_event=live_message["sse_event"],
                payload=live_message["payload"],
            )
            if sse := _yield_if_visible(stream_event):
                yield sse
            if stream_event.sse_event in {"done", "error"}:
                terminal_received = True
    finally:
        stop_event.set()
        listener.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener
        await redis_client.aclose()
