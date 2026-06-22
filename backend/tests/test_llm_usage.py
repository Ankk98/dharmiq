from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dharmiq.config.settings import get_settings
from dharmiq.core.errors import UsageLimitExceededError
from dharmiq.db.models.chats import ChatRequest, ChatRequestStatus, ChatSession
from dharmiq.db.models.llm_usage import LlmUsageEvent
from dharmiq.db.models.users import User
from dharmiq.llm.usage import check_usage_limits, record_llm_usage
from tests.litellm_helpers import chat_response_dict


def _mock_response(*, prompt_tokens: int = 100, completion_tokens: int = 50) -> dict:
    return chat_response_dict(
        "ok",
        total_tokens=prompt_tokens + completion_tokens,
    ) | {
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "model": "openrouter/deepseek/deepseek-v4-flash",
    }


async def _create_user_session(db: AsyncSession) -> tuple[User, ChatSession]:
    user = User(
        email=f"usage-{uuid.uuid4()}@example.com",
        hashed_password="hash",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    session = ChatSession(user_id=user.id, title="Usage test")
    db.add(session)
    await db.flush()
    return user, session


@pytest.mark.asyncio
async def test_records_usage_on_completion(db: AsyncSession) -> None:
    user, session = await _create_user_session(db)
    chat_request = ChatRequest(
        session_id=session.id,
        user_id=user.id,
        status=ChatRequestStatus.PENDING,
    )
    db.add(chat_request)
    await db.flush()

    response = _mock_response()
    with patch("dharmiq.llm.usage.completion_cost", return_value=0.0025):
        cost = await record_llm_usage(
            db,
            user_id=user.id,
            chat_request_id=chat_request.id,
            session_id=session.id,
            agent_role="clarifier",
            model="openrouter/deepseek/deepseek-v4-flash",
            response=response,
        )

    assert cost == Decimal("0.0025")

    events = (
        await db.execute(
            select(LlmUsageEvent).where(LlmUsageEvent.chat_request_id == chat_request.id)
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].agent_role == "clarifier"
    assert events[0].prompt_tokens == 100
    assert events[0].completion_tokens == 50
    assert events[0].cost_usd == Decimal("0.0025")

    await db.refresh(chat_request)
    assert chat_request.cost_usd == Decimal("0.0025")


@pytest.mark.asyncio
async def test_session_cap_blocks(db: AsyncSession) -> None:
    settings = get_settings()
    user, session = await _create_user_session(db)
    db.add(
        ChatRequest(
            session_id=session.id,
            user_id=user.id,
            status=ChatRequestStatus.COMPLETED,
            cost_usd=Decimal("1.00"),
        )
    )
    await db.flush()

    capped_settings = settings.model_copy(
        update={
            "cost_limits": settings.cost_limits.model_copy(
                update={"enforce": True, "per_session_usd": 1.0}
            )
        }
    )

    with pytest.raises(UsageLimitExceededError) as exc_info:
        await check_usage_limits(db, user.id, session.id, capped_settings)

    assert exc_info.value.limit == "conversation"


@pytest.mark.asyncio
async def test_monthly_cap_blocks(db: AsyncSession) -> None:
    settings = get_settings()
    user, session = await _create_user_session(db)
    db.add(
        LlmUsageEvent(
            user_id=user.id,
            session_id=session.id,
            agent_role="answerer",
            model="test-model",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=Decimal("10.00"),
        )
    )
    await db.flush()

    capped_settings = settings.model_copy(
        update={
            "cost_limits": settings.cost_limits.model_copy(
                update={"enforce": True, "per_account_monthly_usd": 10.0}
            )
        }
    )

    with pytest.raises(UsageLimitExceededError) as exc_info:
        await check_usage_limits(db, user.id, session.id, capped_settings)

    assert exc_info.value.limit == "account_monthly"


@pytest.mark.asyncio
async def test_enforce_false_allows(db: AsyncSession) -> None:
    settings = get_settings()
    user, session = await _create_user_session(db)
    db.add(
        ChatRequest(
            session_id=session.id,
            user_id=user.id,
            status=ChatRequestStatus.COMPLETED,
            cost_usd=Decimal("5.00"),
        )
    )
    db.add(
        LlmUsageEvent(
            user_id=user.id,
            session_id=session.id,
            agent_role="answerer",
            model="test-model",
            prompt_tokens=1000,
            completion_tokens=500,
            cost_usd=Decimal("20.00"),
        )
    )
    await db.flush()

    relaxed_settings = settings.model_copy(
        update={"cost_limits": settings.cost_limits.model_copy(update={"enforce": False})}
    )

    await check_usage_limits(db, user.id, session.id, relaxed_settings)
