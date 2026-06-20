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
from dharmiq.config.settings import Settings, get_settings
from dharmiq.core.errors import OpenRouterError
from dharmiq.core.logging import get_logger
from dharmiq.db.models.chats import (
    ChatMessage,
    ChatRequest,
    ChatRequestStatus,
    ChatSession,
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
) -> None:
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


def _citations_from_state(state: AgentGraphState) -> list[CitationRead]:
    raw = state.get("citations") or []
    return [CitationRead.model_validate(item) for item in raw]


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
    cfg = settings or get_settings()
    llm = client or get_openrouter_client()
    started = time.monotonic()
    model_name = cfg.openrouter.default_model

    clarifier_round = await _seed_clarifier_round(db, chat_session.id)

    chat_request = ChatRequest(
        session_id=chat_session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
        llm_model=model_name,
        clarifier_round=clarifier_round,
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

    runtime = GraphRuntime(
        db=db,
        settings=cfg,
        client=llm,
        user=user,
        chat_session=chat_session,
        chat_request=chat_request,
        history=history,
        user_msg=user_msg,
        new_messages=[user_msg],
        started=started,
    )

    initial_state: AgentGraphState = {
        "chat_request_id": str(chat_request.id),
        "session_id": str(chat_session.id),
        "user_id": str(user.id),
        "user_message": user_message,
        "attached_upload_ids": [],
        "clarifier_round": clarifier_round,
        "force_answer": chat_request.force_answer,
        "stated_assumptions": chat_request.stated_assumptions or [],
        "regeneration_count": 0,
        "total_tokens": 0,
        "max_validator_retries": cfg.chat.max_validator_retries,
    }

    saver = checkpointer if checkpointer is not None else await get_checkpointer(cfg)
    graph = build_agent_graph(checkpointer=saver)

    run_config: RunnableConfig = {
        "configurable": {
            "thread_id": str(chat_request.id),
            "runtime": runtime,
        },
    }

    try:
        chat_request.status = ChatRequestStatus.RUNNING
        await db.flush()

        if interrupt_after:
            final_state = await graph.ainvoke(
                initial_state,
                run_config,
                interrupt_after=interrupt_after,
            )
        else:
            final_state = await graph.ainvoke(initial_state, run_config)

        if final_state.get("needs_clarification") and final_state.get("followup_questions"):
            await _persist_clarifier_return(runtime, final_state)
            return ChatPipelineResult(
                chat_request_id=chat_request.id,
                status=ChatRequestStatus.COMPLETED,
                needs_clarification=True,
                followup_questions=final_state.get("followup_questions") or [],
                taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
                new_messages=[ChatMessageRead.model_validate(message) for message in runtime.new_messages],
            )

        if final_state.get("blocked"):
            error_message = final_state.get("block_reason") or "Request blocked"
            await _mark_request_failed(db, chat_request, error_message=error_message)
            return ChatPipelineResult(
                chat_request_id=chat_request.id,
                status=ChatRequestStatus.FAILED,
                needs_clarification=False,
                error_message=error_message,
                taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
                new_messages=[ChatMessageRead.model_validate(user_msg)],
            )

        await db.commit()
        for message in runtime.new_messages:
            await db.refresh(message)

        return ChatPipelineResult(
            chat_request_id=chat_request.id,
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
            chat_request_id=str(chat_request.id),
            error=exc.message,
        )
        await _mark_request_failed(db, chat_request, error_message=exc.message)
        return ChatPipelineResult(
            chat_request_id=chat_request.id,
            status=ChatRequestStatus.FAILED,
            needs_clarification=False,
            error_message=exc.message,
            taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
            new_messages=[ChatMessageRead.model_validate(user_msg)],
        )
    except Exception:
        logger.exception(
            "agent_graph_error",
            chat_request_id=str(chat_request.id),
        )
        await _mark_request_failed(db, chat_request, error_message="Internal error")
        raise
