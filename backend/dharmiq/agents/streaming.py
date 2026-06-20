from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.progress import (
    NODE_PROGRESS_LABELS,
    ProgressEmitter,
    ProgressView,
    StreamEvent,
    filter_event_payload_for_view,
    pubsub_channel,
    seq_key,
    sse_event_name,
)
from dharmiq.config.settings import Settings, get_settings
from dharmiq.db.models.chats import (
    ChatRequest,
    ChatRequestEvent,
    ChatRequestStatus,
)
from dharmiq.db.models.users import User

__all__ = [
    "NODE_PROGRESS_LABELS",
    "ProgressEmitter",
    "ProgressView",
    "StreamEvent",
    "event_to_stream",
    "filter_event_for_user",
    "load_events_after_seq",
    "pubsub_channel",
    "seq_key",
    "sse_event_name",
    "stream_chat_request_events",
]


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
    *,
    view: ProgressView = "concise",
) -> StreamEvent | None:
    filtered_payload = filter_event_payload_for_view(
        stream_event.payload,
        view=view,
        user=user,
        settings=settings,
    )
    if filtered_payload is None:
        return None
    return StreamEvent(
        seq=stream_event.seq,
        sse_event=stream_event.sse_event,
        payload=filtered_payload,
    )


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
    view: ProgressView = "concise",
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Stream chat request SSE events with tiered visibility filtering.

    View tiers (R4-9):
    - concise (default): user-friendly step labels and status only
    - detailed (?view=detailed): agent names, chunk previews, validator summary
    - debug: rerank scores, queries, validator JSON — superuser + DHARMIQ_DEBUG_PROGRESS only
    """
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
        filtered = filter_event_for_user(stream_event, user, cfg, view=view)
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
