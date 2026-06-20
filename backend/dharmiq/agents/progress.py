from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import Settings, get_settings
from dharmiq.db.models.chats import ChatRequestEvent, ChatRequestEventType, EventVisibility
from dharmiq.db.models.users import User

ProgressView = Literal["concise", "detailed"]

NODE_PROGRESS_LABELS: dict[str, str] = {
    "input_guard": "Checking your question…",
    "clarifier": "Understanding your question…",
    "query_rewriter": "Preparing search…",
    "retrieve": "Searching laws…",
    "refusal": "Checking sources…",
    "answerer": "Drafting answer…",
    "citation_enricher": "Mapping citations…",
    "validator": "Checking answer…",
    "finalizer": "Finalizing answer…",
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    "input_guard": "InputGuard",
    "clarifier": "Clarifier",
    "query_rewriter": "QueryRewriter",
    "retrieve": "Retrieve",
    "refusal": "Refusal",
    "answerer": "Answerer",
    "citation_enricher": "CitationEnricher",
    "validator": "Validator",
    "finalizer": "Finalizer",
}

DEBUG_FIELD_KEYS = frozenset(
    {
        "rerank_scores",
        "queries",
        "validator_issues",
        "chunk_snippets",
        "token_breakdown",
    }
)


def seq_key(chat_request_id: uuid.UUID) -> str:
    return f"chat:req:{chat_request_id}:seq"


def pubsub_channel(chat_request_id: uuid.UUID) -> str:
    return f"chat:request:{chat_request_id}"


def sse_event_name(db_event_type: ChatRequestEventType) -> str:
    if db_event_type in {ChatRequestEventType.STEP_START, ChatRequestEventType.STEP_END}:
        return "progress"
    if db_event_type == ChatRequestEventType.TOKEN:
        return "answer_token"
    if db_event_type == ChatRequestEventType.CITATION:
        return "citation"
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


def can_view_debug(user: User, settings: Settings | None = None) -> bool:
    cfg = settings or get_settings()
    return bool(user.is_superuser and cfg.agent_graph.debug_progress)


def chunk_preview(chunk: dict[str, Any], *, max_len: int = 120) -> str:
    title = chunk.get("document_title") or "Source"
    text = (chunk.get("text") or "").replace("\n", " ").strip()
    snippet = f"{title} — {text}" if text else title
    if len(snippet) <= max_len:
        return snippet
    return snippet[: max_len - 1] + "…"


def retrieve_step_details(
    state: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    chunks = result.get("merged_chunks") or state.get("merged_chunks") or []
    previews = [chunk_preview(chunk) for chunk in chunks[:5]]
    detailed = {
        "agent": AGENT_DISPLAY_NAMES["retrieve"],
        "chunk_count": len(chunks),
        "preview": previews,
    }
    debug = {
        "rerank_scores": [float(chunk.get("score", 0.0)) for chunk in chunks],
        "queries": state.get("search_queries") or result.get("search_queries") or [],
        "top_rerank_score": result.get("top_rerank_score", state.get("top_rerank_score")),
        "weak_retrieval": result.get("weak_retrieval", state.get("weak_retrieval")),
    }
    return detailed, debug


def query_rewriter_step_details(
    state: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    queries = result.get("search_queries") or state.get("search_queries") or []
    detailed = {
        "agent": AGENT_DISPLAY_NAMES["query_rewriter"],
        "query_count": len(queries),
    }
    debug = {"queries": queries}
    return detailed, debug


def validator_step_details(
    state: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    verdict = result.get("validator_verdict") or state.get("validator_verdict") or {}
    must_regenerate = bool(verdict.get("must_regenerate"))
    detailed = {
        "agent": AGENT_DISPLAY_NAMES["validator"],
        "verdict_summary": "needs_regeneration" if must_regenerate else "approved",
    }
    debug = {"validator_issues": list(verdict.get("issues") or [])}
    return detailed, debug


def default_step_details(
    step_id: str,
    _state: dict[str, Any],
    _result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    return {"agent": AGENT_DISPLAY_NAMES.get(step_id, step_id)}, {}


def strip_debug_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in DEBUG_FIELD_KEYS}


def filter_event_payload_for_view(
    payload: dict[str, Any],
    *,
    view: ProgressView,
    user: User,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    visibility = payload.get("visibility", EventVisibility.CONCISE.value)

    if visibility == EventVisibility.DEBUG.value:
        if not can_view_debug(user, settings):
            return None
        return payload

    if visibility == EventVisibility.DETAILED.value:
        if view != "detailed":
            return None
        return strip_debug_fields(payload)

    cleaned = strip_debug_fields(payload)
    if view == "concise":
        return {
            key: value
            for key, value in cleaned.items()
            if key
            not in {
                "step_id",
                "agent",
                "chunk_count",
                "preview",
                "query_count",
                "verdict_summary",
            }
        }
    return cleaned


class ProgressEmitter:
    def __init__(
        self,
        db: AsyncSession,
        chat_request_id: uuid.UUID,
        *,
        redis_client: aioredis.Redis | None = None,
        settings: Settings | None = None,
        publish: Callable[[StreamEvent], Any] | None = None,
    ) -> None:
        self.db = db
        self.chat_request_id = chat_request_id
        self._redis = redis_client
        self._owns_redis = redis_client is None
        self._settings = settings or get_settings()
        self._publish = publish

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
    ) -> dict[str, Any]:
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
        await self._publish_event(stream_event)
        return payload_with_seq

    async def _publish_event(self, stream_event: StreamEvent) -> None:
        if self._publish is not None:
            await self._publish(stream_event)
            return

        redis_client = await self._redis_client()
        message = json.dumps(
            {
                "seq": stream_event.seq,
                "sse_event": stream_event.sse_event,
                "payload": stream_event.payload,
            }
        )
        await redis_client.publish(pubsub_channel(self.chat_request_id), message)

    def _step_base(self, step_id: str, *, label: str | None = None) -> dict[str, Any]:
        return {
            "step_id": step_id,
            "label": label or NODE_PROGRESS_LABELS.get(step_id, step_id),
        }

    async def emit_step_start(self, step_id: str, *, label: str | None = None) -> dict[str, Any]:
        return await self.emit(
            event_type=ChatRequestEventType.STEP_START,
            payload={**self._step_base(step_id, label=label), "status": "running"},
        )

    async def emit_step_end_tiers(
        self,
        step_id: str,
        *,
        label: str | None = None,
        detailed: dict[str, Any] | None = None,
        debug: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        base = {**self._step_base(step_id, label=label), "status": "completed"}
        emitted = [
            await self.emit(
                event_type=ChatRequestEventType.STEP_END,
                payload=base,
                visibility=EventVisibility.CONCISE,
            )
        ]
        if detailed:
            emitted.append(
                await self.emit(
                    event_type=ChatRequestEventType.STEP_END,
                    payload={**base, **detailed},
                    visibility=EventVisibility.DETAILED,
                )
            )
        if debug:
            emitted.append(
                await self.emit(
                    event_type=ChatRequestEventType.STEP_END,
                    payload={**base, **debug},
                    visibility=EventVisibility.DEBUG,
                )
            )
        return emitted

    async def emit_step_end(self, step_id: str, *, label: str | None = None) -> dict[str, Any]:
        payloads = await self.emit_step_end_tiers(step_id, label=label)
        return payloads[0]

    async def emit_step_failed(self, step_id: str, *, label: str | None = None) -> dict[str, Any]:
        return await self.emit(
            event_type=ChatRequestEventType.STEP_END,
            payload={**self._step_base(step_id, label=label), "status": "failed"},
        )

    async def emit_error(self, *, code: str, message: str) -> dict[str, Any]:
        return await self.emit(
            event_type=ChatRequestEventType.ERROR,
            payload={"code": code, "message": message},
        )

    async def emit_answer_token(
        self,
        token: str,
        *,
        citation_markers: list[int] | None = None,
    ) -> dict[str, Any]:
        return await self.emit(
            event_type=ChatRequestEventType.TOKEN,
            payload={
                "token": token,
                "citation_markers": citation_markers or [],
            },
        )

    async def emit_citation(
        self,
        *,
        marker: int,
        chunk_id: uuid.UUID,
        document_title: str,
        quote_text: str | None = None,
        source_type: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "marker": marker,
            "chunk_id": str(chunk_id),
            "document_title": document_title,
        }
        if quote_text is not None:
            payload["quote_text"] = quote_text
        if source_type is not None:
            payload["source_type"] = source_type
        if document_id is not None:
            payload["document_id"] = str(document_id)
        return await self.emit(
            event_type=ChatRequestEventType.CITATION,
            payload=payload,
        )

    async def emit_done(
        self,
        *,
        message_id: uuid.UUID | None,
        status,
        citations: list[dict[str, Any]] | None = None,
        total_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": status.value if hasattr(status, "value") else status}
        if message_id is not None:
            payload["message_id"] = str(message_id)
        if citations is not None:
            payload["citations"] = citations
        if total_tokens is not None:
            payload["total_tokens"] = total_tokens
        return await self.emit(event_type=ChatRequestEventType.DONE, payload=payload)
