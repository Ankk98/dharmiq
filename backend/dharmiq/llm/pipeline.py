from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from dharmiq.llm.agents.answerer import run_answerer
from dharmiq.llm.agents.base import extract_user_facts
from dharmiq.llm.agents.clarifier import run_clarifier
from dharmiq.llm.agents.query_rewriter import run_query_rewriter
from dharmiq.llm.agents.validator import run_validator
from dharmiq.llm.openrouter_client import OpenRouterClient, get_openrouter_client
from dharmiq.llm.retrieval import CitationRead, chunks_to_citations, retrieve_multi_query
from dharmiq.observability.metrics import record_llm_tokens
from dharmiq.schemas.chat import ChatMessageRead

logger = get_logger(__name__)


@dataclass
class ChatPipelineResult:
    chat_request_id: uuid.UUID
    status: ChatRequestStatus
    needs_clarification: bool
    followup_questions: list[str] = field(default_factory=list)
    answer: str | None = None
    citations: list[CitationRead] = field(default_factory=list)
    final_warning: str | None = None
    taking_longer_than_expected: bool = False
    new_messages: list[ChatMessageRead] = field(default_factory=list)
    error_message: str | None = None


async def _load_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    *,
    limit: int,
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = list(result.scalars().all())
    return messages[-limit:]


async def _mark_request_failed(
    db: AsyncSession,
    chat_request: ChatRequest,
    *,
    error_message: str,
) -> None:
    chat_request.status = ChatRequestStatus.FAILED
    chat_request.finished_at = datetime.now(UTC)
    chat_request.error_message = error_message
    await db.commit()


async def run_chat_pipeline(
    db: AsyncSession,
    *,
    chat_session: ChatSession,
    user: User,
    user_message: str,
    settings: Settings | None = None,
    client: OpenRouterClient | None = None,
) -> ChatPipelineResult:
    cfg = settings or get_settings()
    llm = client or get_openrouter_client()
    started = time.monotonic()
    total_tokens = 0
    model_name = cfg.openrouter.default_model

    chat_request = ChatRequest(
        session_id=chat_session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
        llm_model=model_name,
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
    new_messages: list[ChatMessage] = [user_msg]

    try:
        clarifier = await run_clarifier(
            llm,
            user_question=user_message,
            history=history[:-1],
            history_limit=cfg.chat.history_limit,
        )
        total_tokens += clarifier.tokens_used
        record_llm_tokens(model=model_name, agent="clarifier", tokens=clarifier.tokens_used)

        if clarifier.needs_more_info and clarifier.followup_questions:
            clarifier_content = "\n".join(f"- {question}" for question in clarifier.followup_questions)
            clarifier_msg = ChatMessage(
                session_id=chat_session.id,
                user_id=user.id,
                role=MessageRole.CLARIFIER,
                content=clarifier_content,
                message_metadata={
                    "agent": "clarifier",
                    "topic": clarifier.topic,
                    "reason": clarifier.reason,
                    "chat_request_id": str(chat_request.id),
                    "followup_items": [
                        {
                            "question": item.question,
                            "why": item.why,
                            "options": item.options,
                        }
                        for item in clarifier.followup_items
                    ],
                },
            )
            db.add(clarifier_msg)
            new_messages.append(clarifier_msg)

            chat_request.status = ChatRequestStatus.COMPLETED
            chat_request.total_tokens = total_tokens
            chat_request.finished_at = datetime.now(UTC)
            await db.commit()

            for message in new_messages:
                await db.refresh(message)

            return ChatPipelineResult(
                chat_request_id=chat_request.id,
                status=ChatRequestStatus.COMPLETED,
                needs_clarification=True,
                followup_questions=clarifier.followup_questions,
                taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
                new_messages=[ChatMessageRead.model_validate(message) for message in new_messages],
            )

        chat_request.status = ChatRequestStatus.RUNNING
        await db.flush()

        facts = extract_user_facts(history + [user_msg])
        rewriter = await run_query_rewriter(
            llm,
            user_question=user_message,
            topic=clarifier.topic,
            facts=facts,
        )
        total_tokens += rewriter.tokens_used
        record_llm_tokens(model=model_name, agent="query_rewriter", tokens=rewriter.tokens_used)

        retrieved = (
            await retrieve_multi_query(
                db,
                rewriter.queries,
                user.id,
                rerank_query=user_message,
                top_k=cfg.retrieval.multi_query_top_k,
            )
        ).chunks

        draft_answer = await run_answerer(
            llm,
            user_question=user_message,
            facts=facts,
            retrieved_chunks=retrieved,
        )
        total_tokens += draft_answer.tokens_used
        record_llm_tokens(model=model_name, agent="answerer", tokens=draft_answer.tokens_used)
        answer_text = draft_answer.answer
        final_warning: str | None = None

        for attempt in range(cfg.chat.max_validator_retries):
            validator = await run_validator(
                llm,
                user_question=user_message,
                retrieved_chunks=retrieved,
                draft_answer=answer_text,
            )
            total_tokens += validator.tokens_used
            record_llm_tokens(model=model_name, agent="validator", tokens=validator.tokens_used)

            if not validator.must_regenerate:
                final_warning = validator.final_warning or None
                break

            if attempt + 1 >= cfg.chat.max_validator_retries:
                final_warning = (
                    validator.final_warning
                    or "This answer may still contain issues. Please consult a qualified lawyer."
                )
                break

            regenerated = await run_answerer(
                llm,
                user_question=user_message,
                facts=facts,
                retrieved_chunks=retrieved,
                regeneration_instructions=validator.regeneration_instructions,
            )
            total_tokens += regenerated.tokens_used
            record_llm_tokens(model=model_name, agent="answerer", tokens=regenerated.tokens_used)
            answer_text = regenerated.answer

        if final_warning and final_warning not in answer_text:
            answer_text = f"{answer_text.rstrip()}\n\n> {final_warning}"

        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            user_id=user.id,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            message_metadata={
                "agent": "answerer",
                "topic": clarifier.topic,
                "citations": [citation.model_dump(mode="json") for citation in chunks_to_citations(retrieved)],
                "chat_request_id": str(chat_request.id),
            },
        )
        db.add(assistant_msg)
        new_messages.append(assistant_msg)

        chat_request.status = ChatRequestStatus.COMPLETED
        chat_request.total_tokens = total_tokens
        chat_request.finished_at = datetime.now(UTC)
        await db.commit()

        for message in new_messages:
            await db.refresh(message)

        return ChatPipelineResult(
            chat_request_id=chat_request.id,
            status=ChatRequestStatus.COMPLETED,
            needs_clarification=False,
            answer=answer_text,
            citations=chunks_to_citations(retrieved),
            final_warning=final_warning,
            taking_longer_than_expected=_elapsed_over_threshold(started, cfg),
            new_messages=[ChatMessageRead.model_validate(message) for message in new_messages],
        )

    except OpenRouterError as exc:
        logger.error(
            "chat_pipeline_openrouter_error",
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
    except Exception as exc:
        logger.exception(
            "chat_pipeline_error",
            chat_request_id=str(chat_request.id),
        )
        await _mark_request_failed(db, chat_request, error_message=str(exc))
        raise


def _elapsed_over_threshold(started: float, settings: Settings) -> bool:
    return (time.monotonic() - started) >= settings.chat.slow_threshold_seconds
