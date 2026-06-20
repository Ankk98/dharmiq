from __future__ import annotations

import time
import uuid

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.agents.checkpoint import get_checkpointer
from dharmiq.agents.graph import build_agent_graph
from dharmiq.agents.runtime import GraphRuntime
from dharmiq.agents.state import AgentGraphState
from dharmiq.agents.streaming import ProgressEmitter
from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.chats import (
    ChatMessage,
    ChatRequest,
    ChatRequestStatus,
    ChatSession,
    ChatSessionUpload,
    MessageRole,
)
from dharmiq.db.models.users import User
from dharmiq.llm.openrouter_client import OpenRouterClient, get_openrouter_client
from dharmiq.llm.pipeline import (
    ChatPipelineResult,
    _elapsed_over_threshold,
    _load_history,
    _mark_request_failed,
)
from dharmiq.llm.retrieval import CitationRead
from dharmiq.schemas.chat import ChatMessageRead

logger = get_logger(__name__)


async def _load_attached_upload_ids(db: AsyncSession, session_id: uuid.UUID) -> list[str]:
    result = await db.execute(
        select(ChatSessionUpload.upload_id).where(ChatSessionUpload.session_id == session_id)
    )
    return [str(upload_id) for upload_id in result.scalars().all()]


async def _seed_clarifier_round(db: AsyncSession, session_id: uuid.UUID) -> int:
    result = await db.execute(
        select(ChatRequest.clarifier_round)
        .where(ChatRequest.session_id == session_id)
        .order_by(ChatRequest.started_at.desc())
        .limit(1)
    )
    prior_round = result.scalar_one_or_none()
    return prior_round or 0


async def _persist_clarifier_return(
    runtime: GraphRuntime,
    state: AgentGraphState,
) -> ChatMessage:
    followups = state.get("followup_questions") or []
    clarifier_content = "\n".join(f"- {question}" for question in followups)
    clarifier_msg = ChatMessage(
        session_id=runtime.chat_session.id,
        user_id=runtime.user.id,
        role=MessageRole.CLARIFIER,
        content=clarifier_content,
        message_metadata={
            "agent": "clarifier",
            "topic": state.get("topic"),
            "reason": state.get("clarifier_reason"),
            "chat_request_id": str(runtime.chat_request_id),
        },
    )
    runtime.db.add(clarifier_msg)
    runtime.new_messages.append(clarifier_msg)

    runtime.chat_request.clarifier_round = state.get("clarifier_round", 0) + 1
    runtime.chat_request.status = ChatRequestStatus.COMPLETED
    runtime.chat_request.total_tokens = state.get("total_tokens", 0)
    runtime.chat_request.finished_at = runtime.utcnow()
    await runtime.db.commit()

    for message in runtime.new_messages:
        await runtime.db.refresh(message)
    return clarifier_msg


def _citations_from_state(state: AgentGraphState) -> list[CitationRead]:
    raw = state.get("citations") or []
    return [CitationRead.model_validate(item) for item in raw]


async def create_agent_graph_request(
    db: AsyncSession,
    *,
    chat_session: ChatSession,
    user: User,
    user_message: str,
    force_answer: bool = False,
    settings: Settings | None = None,
) -> GraphRuntime:
    cfg = settings or get_settings()
    clarifier_round = await _seed_clarifier_round(db, chat_session.id)

    chat_request = ChatRequest(
        session_id=chat_session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
        llm_model=cfg.openrouter.default_model,
        clarifier_round=clarifier_round,
        force_answer=force_answer,
    )
    db.add(chat_request)
    await db.flush()

    user_msg = ChatMessage(
        session_id=chat_session.id,
        user_id=user.id,
        role=MessageRole.USER,
        content=user_message,
        message_metadata={"chat_request_id": str(chat_request.id)},
    )
    db.add(user_msg)

    if chat_session.title is None:
        chat_session.title = user_message.strip().replace("\n", " ")[:80]

    history = await _load_history(db, chat_session.id, limit=cfg.chat.history_limit)
    attached_upload_ids = await _load_attached_upload_ids(db, chat_session.id)
    await db.commit()
    await db.refresh(chat_request)
    await db.refresh(user_msg)

    return GraphRuntime(
        db=db,
        settings=cfg,
        client=get_openrouter_client(),
        user=user,
        chat_session=chat_session,
        chat_request=chat_request,
        history=history,
        user_msg=user_msg,
        attached_upload_ids=attached_upload_ids,
        new_messages=[user_msg],
    )


def _initial_state(runtime: GraphRuntime) -> AgentGraphState:
    return {
        "chat_request_id": str(runtime.chat_request.id),
        "session_id": str(runtime.chat_session.id),
        "user_id": str(runtime.user.id),
        "user_message": runtime.user_msg.content,
        "attached_upload_ids": runtime.attached_upload_ids,
        "clarifier_round": runtime.chat_request.clarifier_round,
        "force_answer": runtime.chat_request.force_answer,
        "stated_assumptions": runtime.chat_request.stated_assumptions or [],
        "regeneration_count": 0,
        "total_tokens": 0,
        "max_validator_retries": runtime.settings.chat.max_validator_retries,
        "weak_retrieval": False,
        "top_rerank_score": 0.0,
    }


async def _load_runtime_for_request(
    db: AsyncSession,
    chat_request_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    emitter: ProgressEmitter | None = None,
) -> GraphRuntime:
    cfg = settings or get_settings()
    result = await db.execute(select(ChatRequest).where(ChatRequest.id == chat_request_id))
    chat_request = result.scalar_one()

    session_result = await db.execute(
        select(ChatSession).where(ChatSession.id == chat_request.session_id)
    )
    chat_session = session_result.scalar_one()

    user_result = await db.execute(select(User).where(User.id == chat_request.user_id))
    user = user_result.scalar_one()

    messages_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == chat_session.id,
            ChatMessage.role == MessageRole.USER,
        )
        .order_by(ChatMessage.created_at.desc())
    )
    user_msg = next(
        (
            message
            for message in messages_result.scalars().all()
            if (message.message_metadata or {}).get("chat_request_id") == str(chat_request.id)
        ),
        None,
    )
    if user_msg is None:
        raise ValueError(f"User message not found for chat request {chat_request.id}")

    history = await _load_history(db, chat_session.id, limit=cfg.chat.history_limit)
    attached_upload_ids = await _load_attached_upload_ids(db, chat_session.id)

    return GraphRuntime(
        db=db,
        settings=cfg,
        client=get_openrouter_client(),
        user=user,
        chat_session=chat_session,
        chat_request=chat_request,
        history=history,
        user_msg=user_msg,
        attached_upload_ids=attached_upload_ids,
        new_messages=[user_msg],
        emitter=emitter,
    )


async def run_agent_graph_for_request(
    db: AsyncSession,
    chat_request_id: uuid.UUID,
    *,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
    checkpointer=None,
    interrupt_after: list[str] | None = None,
) -> ChatPipelineResult:
    cfg = settings or get_settings()
    emitter = ProgressEmitter(db, chat_request_id, settings=cfg)
    runtime = await _load_runtime_for_request(db, chat_request_id, settings=cfg, emitter=emitter)
    if client is not None:
        runtime.client = client

    started = time.monotonic()
    initial_state = _initial_state(runtime)

    saver = checkpointer if checkpointer is not None else await get_checkpointer(cfg)
    graph = build_agent_graph(checkpointer=saver)

    run_config: RunnableConfig = {
        "configurable": {
            "thread_id": str(chat_request_id),
            "runtime": runtime,
        },
    }

    try:
        runtime.chat_request.status = ChatRequestStatus.RUNNING
        await db.commit()

        if interrupt_after:
            final_state = await graph.ainvoke(
                initial_state,
                run_config,
                interrupt_after=interrupt_after,
            )
        else:
            final_state = await graph.ainvoke(initial_state, run_config)

        if final_state.get("needs_clarification") and final_state.get("followup_questions"):
            clarifier_msg = await _persist_clarifier_return(runtime, final_state)
            if runtime.emitter is not None:
                await runtime.emitter.emit_done(
                    message_id=clarifier_msg.id,
                    status=ChatRequestStatus.COMPLETED,
                )
            return ChatPipelineResult(
                chat_request_id=runtime.chat_request.id,
                status=ChatRequestStatus.COMPLETED,
                needs_clarification=True,
                followup_questions=final_state.get("followup_questions") or [],
                taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
                new_messages=[ChatMessageRead.model_validate(message) for message in runtime.new_messages],
            )

        if final_state.get("blocked"):
            error_message = final_state.get("block_reason") or "Request blocked"
            await _mark_request_failed(db, runtime.chat_request, error_message=error_message)
            if runtime.emitter is not None:
                await runtime.emitter.emit_error(code="INPUT_BLOCKED", message=error_message)
                await runtime.emitter.emit_done(
                    message_id=None,
                    status=ChatRequestStatus.FAILED,
                )
            return ChatPipelineResult(
                chat_request_id=runtime.chat_request.id,
                status=ChatRequestStatus.FAILED,
                needs_clarification=False,
                error_message=error_message,
                taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
                new_messages=[ChatMessageRead.model_validate(runtime.user_msg)],
            )

        await db.commit()

        assistant_msg = next(
            (message for message in runtime.new_messages if message.role == MessageRole.ASSISTANT),
            None,
        )
        if runtime.emitter is not None:
            await runtime.emitter.emit_done(
                message_id=assistant_msg.id if assistant_msg is not None else None,
                status=ChatRequestStatus.COMPLETED,
            )

        return ChatPipelineResult(
            chat_request_id=runtime.chat_request.id,
            status=ChatRequestStatus.COMPLETED,
            needs_clarification=False,
            answer=final_state.get("final_answer"),
            citations=_citations_from_state(final_state),
            final_warning=final_state.get("final_warning"),
            taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
            new_messages=[ChatMessageRead.model_validate(message) for message in runtime.new_messages],
        )

    except OpenRouterError as exc:
        logger.error(
            "agent_graph_openrouter_error",
            chat_request_id=str(chat_request_id),
            error=exc.message,
        )
        await _mark_request_failed(db, runtime.chat_request, error_message=exc.message)
        if runtime.emitter is not None:
            await runtime.emitter.emit_error(code="LLM_ERROR", message=exc.message)
            await runtime.emitter.emit_done(message_id=None, status=ChatRequestStatus.FAILED)
        return ChatPipelineResult(
            chat_request_id=runtime.chat_request.id,
            status=ChatRequestStatus.FAILED,
            needs_clarification=False,
            error_message=exc.message,
            taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
            new_messages=[ChatMessageRead.model_validate(runtime.user_msg)],
        )
    except Exception:
        logger.exception("agent_graph_error", chat_request_id=str(chat_request_id))
        await _mark_request_failed(db, runtime.chat_request, error_message="Internal error")
        if runtime.emitter is not None:
            await runtime.emitter.emit_error(code="INTERNAL_ERROR", message="Internal error")
            await runtime.emitter.emit_done(message_id=None, status=ChatRequestStatus.FAILED)
        raise
    finally:
        await emitter.close()


async def run_agent_graph_sync(
    db: AsyncSession,
    *,
    chat_session: ChatSession,
    user: User,
    user_message: str,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
    checkpointer=None,
    interrupt_after: list[str] | None = None,
) -> ChatPipelineResult:
    runtime = await create_agent_graph_request(
        db,
        chat_session=chat_session,
        user=user,
        user_message=user_message,
        settings=settings,
    )
    if client is not None:
        runtime.client = client
    return await run_agent_graph_for_request(
        db,
        runtime.chat_request.id,
        settings=settings,
        client=client,
        checkpointer=checkpointer,
        interrupt_after=interrupt_after,
    )
